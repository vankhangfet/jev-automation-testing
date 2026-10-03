from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from jev_ui_agent.checks.composite import score_checkpoint
from jev_ui_agent.checks.router import run_checks
from jev_ui_agent.driver.base import BaseDriver
from jev_ui_agent.extract.normalize import build_state
from jev_ui_agent.flows import load_flow
from jev_ui_agent.jev.client import JevClient
from jev_ui_agent.models import CheckpointReport, RunReport
from jev_ui_agent.report.html import render_html
from jev_ui_agent.report.json_report import render_json
from jev_ui_agent.vision.claude_bridge import VisionBridge


def load_yaml(path: Path | str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def make_driver(driver_kind: str, device_cfg: dict, out_dir: Path,
                fixtures_dir: Path | None) -> BaseDriver:
    if driver_kind == "fake":
        from jev_ui_agent.driver.fake import FakeDriver
        return FakeDriver(fixtures_dir or Path("tests/fixtures/fake_run"), out_dir)
    if driver_kind == "android":
        from jev_ui_agent.driver.android import AndroidDriver
        return AndroidDriver(device_cfg, out_dir)
    raise ValueError(f"Unknown driver kind: {driver_kind!r}")


def _do_action(driver: BaseDriver, step: dict) -> None:
    action = step["action"]
    if action == "launch":
        driver.launch()
    elif action == "tap":
        driver.tap(step["target"])
    elif action == "input":
        driver.input_text(step["target"], step["value"])
    elif action == "swipe":
        driver.swipe(int(step["x1"]), int(step["y1"]), int(step["x2"]), int(step["y2"]),
                     int(step.get("duration", 500)))


def _try_action(driver: BaseDriver, step: dict, retries: int = 1) -> str | None:
    """Thành công → None; thất bại → chuỗi lý do của lần thử cuối."""
    last_err: Exception | None = None
    for _ in range(retries + 1):
        try:
            _do_action(driver, step)
            return None
        except Exception as e:  # noqa: BLE001 — action failure là dữ liệu, không phải crash
            last_err = e
            continue
    return f"{type(last_err).__name__}: {last_err}"


def run_flow(*, flow_path: Path | str, policy_path: Path | str,
             devices_path: Path | str, driver_kind: str, out_root: Path | str,
             fixtures_dir: Path | None = None, jev: JevClient | None = None,
             vision: VisionBridge | None = None) -> RunReport:
    flow = load_flow(flow_path)
    policy = load_yaml(policy_path)
    devices = load_yaml(devices_path)

    base_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = Path(out_root) / base_id
    suffix = 1
    while out_dir.exists():  # chống đè report khi 2 run cùng giây
        out_dir = Path(out_root) / f"{base_id}-{suffix}"
        suffix += 1
    run_id = out_dir.name
    (out_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    platform = flow.get("platform", "android")
    device_cfg = devices.get(platform)
    if device_cfg is None:
        raise ValueError(f"devices.yaml không có cấu hình cho platform {platform!r}")

    driver = make_driver(driver_kind, device_cfg, out_dir, fixtures_dir)
    report = RunReport(run_id=run_id, flow_name=flow["name"],
                       started_at=datetime.now().isoformat(timespec="seconds"))

    try:
        driver.connect()  # trong try để connect fail vẫn quit() session nếu có
        for step in flow["steps"]:
            if step["kind"] == "checkpoint":
                cp = CheckpointReport(checkpoint=step["name"])
                try:
                    artifact = driver.capture(step["name"])
                    state = build_state(artifact, run_id=run_id, platform=platform,
                                        app=flow["app"], viewport=device_cfg["viewport"])
                    # report dùng path tương đối posix để <img src> hoạt động;
                    # state.screenshot (tuyệt đối) vẫn dùng cho vision bridge
                    cp.screenshot = "artifacts/" + Path(artifact.screenshot_path).name
                    cp.results = run_checks(state, policy, jev, vision)
                    cp.screen_score = score_checkpoint(cp.results, policy.get("weights", {}))
                except Exception as e:  # noqa: BLE001 — bao gồm ET.ParseError và policy lỗi
                    cp.error = f"{type(e).__name__}: {e}"
                report.checkpoints.append(cp)
            else:
                err = _try_action(driver, step)
                if err is not None:
                    report.failed_steps.append(
                        f"{step['action']} {step.get('target', '')}".strip() + f": {err}")
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass

    if jev is not None:
        report.costs["jev"] = dict(jev.usage)
    if vision is not None:
        report.costs["vision"] = {"calls": vision.calls}

    (out_dir / "report.json").write_text(render_json(report), encoding="utf-8")
    (out_dir / "report.html").write_text(render_html(report), encoding="utf-8")
    return report
