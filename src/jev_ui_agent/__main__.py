from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from jev_ui_agent.batch import run_batch
from jev_ui_agent.jev.client import JevClient
from jev_ui_agent.pipeline import run_flow
from jev_ui_agent.vision.claude_bridge import DEFAULT_MODEL, VisionBridge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jev-ui-agent",
                                     description="JEV mobile UI checking agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="Chạy một flow test")
    run_p.add_argument("--flow", required=True)
    run_p.add_argument("--driver", choices=["fake", "android"], default="fake")
    run_p.add_argument("--policy", default="config/policy.yaml")
    run_p.add_argument("--devices", default="config/devices.yaml")
    run_p.add_argument("--out", default="reports")
    run_p.add_argument("--fixtures-dir", default="tests/fixtures/fake_run")
    cs = sub.add_parser("check-screenshots",
                        help="Batch check a folder of screenshots against natural-language rules")
    cs.add_argument("--dir", required=True)
    cs.add_argument("--rules", required=True)
    cs.add_argument("--policy", default="config/policy.yaml")
    cs.add_argument("--out", default="reports")
    cs.add_argument("--workers", type=int, default=4)
    cs.add_argument("--limit", type=int, default=None)
    cs.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True,
                    help="Quét đệ quy thư mục (mặc định bật; --no-recursive để tắt)")
    cs.add_argument("--resume", default=None, help="Tiếp tục run trước (đường dẫn run dir)")
    args = parser.parse_args(argv)

    if args.command == "run":
        policy = yaml.safe_load(Path(args.policy).read_text(encoding="utf-8"))
        vision_cfg = (policy.get("vision") or {}) if isinstance(policy, dict) else {}
        jev = JevClient() if os.environ.get("TYPESAFE_API_KEY") else None
        vision = (VisionBridge(model=str(vision_cfg.get("model") or DEFAULT_MODEL))
                  if os.environ.get("ANTHROPIC_API_KEY") else None)
        report = run_flow(
            flow_path=args.flow, policy_path=args.policy, devices_path=args.devices,
            driver_kind=args.driver, out_root=args.out,
            fixtures_dir=Path(args.fixtures_dir) if args.driver == "fake" else None,
            jev=jev, vision=vision,
        )
        failed = sum(1 for cp in report.checkpoints
                     for r in cp.results if r.verdict.value == "fail")
        errored = sum(1 for cp in report.checkpoints if cp.error)
        print(f"Run {report.run_id}: {len(report.checkpoints)} checkpoints, {failed} failed checks")
        print(f"Report: {Path(args.out) / report.run_id / 'report.html'}")
        return 1 if (failed or errored or report.failed_steps) else 0

    if args.command == "check-screenshots":
        if not (os.environ.get("TYPESAFE_API_KEY") and os.environ.get("ANTHROPIC_API_KEY")):
            print("check-screenshots requires both TYPESAFE_API_KEY and ANTHROPIC_API_KEY "
                  "(every rule goes through vision + JEV).", file=sys.stderr)
            return 2
        rules_preview = None
        try:
            from jev_ui_agent.rules import load_rules
            rules_preview = load_rules(args.rules)
        except Exception:  # noqa: BLE001 — lỗi sẽ surface ở run_batch với ngữ cảnh đầy đủ
            pass
        if rules_preview and len(rules_preview["rules"]) > 50:
            print(f"WARNING: {len(rules_preview['rules'])} rules trong 1 fan-out call — "
                  "JEV trả thiếu 1 answer sẽ làm mất cả bộ; cân nhắc tách rules file.",
                  file=sys.stderr)
        jev = JevClient()
        vision = VisionBridge(max_tokens=2048)  # observation chi tiết cần headroom
        report = run_batch(images_dir=args.dir, rules_path=args.rules,
                           policy_path=args.policy, out_root=args.out,
                           workers=max(1, args.workers), limit=args.limit,
                           recursive=args.recursive, resume_dir=args.resume,
                           jev=jev, vision=vision)
        s = report.summary
        print(f"Run {report.run_id}: {s.get('total_images', 0)} images - "
              f"{s.get('passed', 0)} pass, {s.get('failed', 0)} fail, "
              f"{s.get('needs_review', 0)} review, {s.get('errors', 0)} error")
        print(f"Report: {Path(args.out) / report.run_id / 'report.html'}")
        return 1 if (s.get("failed") or s.get("errors")) else 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
