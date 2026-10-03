from pathlib import Path

import pytest
import yaml

from jev_ui_agent.__main__ import main

FIX = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch):
    """CLI test chạy offline: không key → JEV/vision client là None."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _flow(tmp_path: Path, checkpoints: tuple[str, ...]) -> Path:
    steps = [{"action": "launch"}] + [{"checkpoint": c} for c in checkpoints]
    flow = {"name": "cli-demo", "app": "com.example", "platform": "android",
            "steps": steps}
    p = tmp_path / "flow.yaml"
    p.write_text(yaml.safe_dump(flow), encoding="utf-8")
    return p


def _run(tmp_path: Path, flow: Path) -> int:
    return main(["run", "--flow", str(flow),
                 "--driver", "fake",
                 "--policy", str(REPO_ROOT / "config" / "policy.fake.yaml"),
                 "--devices", str(REPO_ROOT / "config" / "devices.yaml"),
                 "--out", str(tmp_path / "reports"),
                 "--fixtures-dir", str(FIX / "fake_run")])


def test_exit_0_when_all_checks_pass(tmp_path, capsys):
    code = _run(tmp_path, _flow(tmp_path, ("home", "topics", "settings")))
    assert code == 0
    out = capsys.readouterr().out
    assert "3 checkpoints" in out
    assert "0 failed checks" in out


def test_exit_1_when_checkpoint_errors(tmp_path, capsys):
    # checkpoint không có fixture → capture raise → cp.error → exit 1
    code = _run(tmp_path, _flow(tmp_path, ("nonexistent",)))
    assert code == 1
    out = capsys.readouterr().out
    assert "1 checkpoints" in out


def test_exit_1_when_check_fails(tmp_path, capsys):
    # expectation sai lệch fixture → 1 check FAIL → exit 1
    flow = {"name": "bad", "app": "com.example", "platform": "android", "steps": [
        {"checkpoint": "home"},
    ]}
    p = tmp_path / "flow.yaml"
    p.write_text(yaml.safe_dump(flow), encoding="utf-8")
    policy = yaml.safe_load((REPO_ROOT / "config" / "policy.fake.yaml")
                            .read_text(encoding="utf-8"))
    policy["functional_expectations"] = [
        {"checkpoint": "home", "element": "res-id:login_btn", "expect_text": "Logout"}]
    bad = tmp_path / "policy.bad.yaml"
    bad.write_text(yaml.safe_dump(policy), encoding="utf-8")
    code = main(["run", "--flow", str(p), "--driver", "fake", "--policy", str(bad),
                 "--devices", str(REPO_ROOT / "config" / "devices.yaml"),
                 "--out", str(tmp_path / "reports"),
                 "--fixtures-dir", str(FIX / "fake_run")])
    assert code == 1
    assert "1 failed checks" in capsys.readouterr().out
