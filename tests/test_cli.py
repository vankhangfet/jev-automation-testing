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
    monkeypatch.delenv("LLM_URL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_STYLE", raising=False)


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


def test_check_screenshots_cli_requires_keys(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["check-screenshots", "--dir", str(tmp_path), "--rules", "x.yaml"])
    assert rc == 2


def test_check_screenshots_cli_exit_codes(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    from types import SimpleNamespace
    import jev_ui_agent.__main__ as main_mod

    def fake_batch_fail(**kw):
        return SimpleNamespace(run_id="check-x",
                               summary={"total_images": 3, "passed": 2, "failed": 1,
                                        "needs_review": 0, "errors": 0},
                               checkpoints=[], costs={})

    monkeypatch.setattr(main_mod, "run_batch", fake_batch_fail)
    assert main(["check-screenshots", "--dir", str(tmp_path), "--rules", "r.yaml"]) == 1

    def fake_batch_pass(**kw):
        return SimpleNamespace(run_id="check-y",
                               summary={"total_images": 3, "passed": 3, "failed": 0,
                                        "needs_review": 0, "errors": 0},
                               checkpoints=[], costs={})

    monkeypatch.setattr(main_mod, "run_batch", fake_batch_pass)
    assert main(["check-screenshots", "--dir", str(tmp_path), "--rules", "r.yaml"]) == 0


def test_check_screenshots_accepts_llm_env(monkeypatch, tmp_path):
    """LLM_URL+MODEL_NAME là nguồn vision hợp lệ — không cần ANTHROPIC_API_KEY."""
    from types import SimpleNamespace
    import jev_ui_agent.__main__ as main_mod

    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("MODEL_NAME", "qwen2.5-vl")

    def fake_batch(**kw):
        assert kw["vision"] is not None  # factory tạo được bridge từ LLM_* env
        return SimpleNamespace(run_id="check-z",
                               summary={"total_images": 1, "passed": 1, "failed": 0,
                                        "needs_review": 0, "errors": 0},
                               checkpoints=[], costs={})

    monkeypatch.setattr(main_mod, "run_batch", fake_batch)
    assert main(["check-screenshots", "--dir", str(tmp_path), "--rules", "r.yaml"]) == 0


def test_check_screenshots_rejects_when_no_vision_source(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_URL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    rc = main(["check-screenshots", "--dir", str(tmp_path), "--rules", "x.yaml"])
    assert rc == 2
    out = capsys.readouterr().err
    assert "LLM_URL" in out or "ANTHROPIC_API_KEY" in out


def test_run_uses_vision_factory(monkeypatch, tmp_path):
    """run branch cũng qua factory: chỉ LLM_* env (không Anthropic key) vẫn có vision."""
    import jev_ui_agent.__main__ as main_mod
    from jev_ui_agent.models import RunReport

    flow = {"name": "demo", "app": "com.example", "platform": "android", "steps": [
        {"checkpoint": "home"}]}
    fp = tmp_path / "f.yaml"
    fp.write_text(yaml.safe_dump(flow), encoding="utf-8")

    monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("MODEL_NAME", "qwen2.5-vl")

    seen = {}

    def fake_run_flow(**kw):
        seen.update(kw)
        return RunReport(run_id="run-x", flow_name="demo", started_at="t")

    monkeypatch.setattr(main_mod, "run_flow", fake_run_flow)
    rc = main(["run", "--flow", str(fp), "--driver", "fake",
               "--policy", str(REPO_ROOT / "config" / "policy.fake.yaml"),
               "--devices", str(REPO_ROOT / "config" / "devices.yaml"),
               "--out", str(tmp_path / "r"),
               "--fixtures-dir", str(FIX / "fake_run")])
    assert rc == 0
    assert seen["vision"] is not None and seen["jev"] is None


def test_invalid_llm_style_exits_2_both_commands(monkeypatch, tmp_path, capsys):
    """LLM_STYLE sai → exit 2 graceful ở cả check-screenshots lẫn run (không traceback)."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("MODEL_NAME", "qwen2.5-vl")
    monkeypatch.setenv("LLM_STYLE", "bogus")

    rc = main(["check-screenshots", "--dir", str(tmp_path), "--rules", "r.yaml"])
    assert rc == 2
    assert "Invalid vision configuration" in capsys.readouterr().err

    rc = main(["run", "--flow", str(_flow(tmp_path, ("home",))), "--driver", "fake",
               "--policy", str(REPO_ROOT / "config" / "policy.fake.yaml"),
               "--devices", str(REPO_ROOT / "config" / "devices.yaml"),
               "--out", str(tmp_path / "r"),
               "--fixtures-dir", str(FIX / "fake_run")])
    assert rc == 2
    assert "Invalid vision configuration" in capsys.readouterr().err
