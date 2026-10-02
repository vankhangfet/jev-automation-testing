import json
from pathlib import Path

import yaml

from jev_ui_agent.pipeline import run_flow

FIX = Path(__file__).parent / "fixtures"
# tests/ nằm ngay dưới repo root → parents[1] là repo root (chứa config/devices.yaml)
REPO_ROOT = Path(__file__).resolve().parents[1]


def _flow(tmp_path: Path) -> Path:
    flow = {"name": "demo", "app": "com.example", "platform": "android", "steps": [
        {"action": "launch"},
        {"checkpoint": "home"},
        {"checkpoint": "topics"},
        {"checkpoint": "settings"},
    ]}
    p = tmp_path / "flow.yaml"
    p.write_text(yaml.safe_dump(flow), encoding="utf-8")
    return p


def test_fake_run_writes_reports(tmp_path):
    report = run_flow(
        flow_path=_flow(tmp_path), policy_path=FIX / "policy_test.yaml",
        devices_path=REPO_ROOT / "config" / "devices.yaml", driver_kind="fake",
        out_root=tmp_path / "reports", fixtures_dir=FIX / "fake_run",
        jev=None, vision=None,
    )
    assert [c.checkpoint for c in report.checkpoints] == ["home", "topics", "settings"]
    assert all(c.error == "" for c in report.checkpoints)
    assert report.checkpoints[0].screenshot == "artifacts/home.png"  # relative posix
    assert all(c.screen_score is not None for c in report.checkpoints)  # rule groups chấm được
    run_dir = tmp_path / "reports" / report.run_id
    assert (run_dir / "report.json").exists() and (run_dir / "report.html").exists()
    data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert data["run_id"] == report.run_id
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert 'src="artifacts/home.png"' in html


def test_missing_fixture_records_error(tmp_path):
    flow = {"name": "demo", "app": "com.example", "platform": "android", "steps": [
        {"checkpoint": "nonexistent"}]}
    p = tmp_path / "flow.yaml"
    p.write_text(yaml.safe_dump(flow), encoding="utf-8")
    report = run_flow(flow_path=p, policy_path=FIX / "policy_test.yaml",
                      devices_path=REPO_ROOT / "config" / "devices.yaml",
                      driver_kind="fake", out_root=tmp_path / "reports",
                      fixtures_dir=FIX / "fake_run", jev=None, vision=None)
    assert report.checkpoints[0].error != ""       # capture lỗi được ghi lại
    assert report.checkpoints[0].results == []      # nhưng pipeline không chết


def test_try_action_retries_then_records(tmp_path):
    from jev_ui_agent.pipeline import _try_action

    class Flaky:
        def __init__(self):
            self.n = 0

        def tap(self, target):
            self.n += 1
            if self.n < 2:
                raise RuntimeError("flaky")
            return None

    assert _try_action(Flaky(), {"action": "tap", "target": "x"}) is True

    class Dead:
        def tap(self, target):
            raise RuntimeError("dead")

    assert _try_action(Dead(), {"action": "tap", "target": "x"}) is False
