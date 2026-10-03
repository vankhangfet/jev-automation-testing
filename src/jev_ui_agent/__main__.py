from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

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
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
