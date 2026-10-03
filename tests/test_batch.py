import json
from pathlib import Path

import pytest

from jev_ui_agent.batch import _cp_from_record, _image_status, run_batch, scan_images
from jev_ui_agent.models import Verdict

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def img_dir(tmp_path):
    d = tmp_path / "shots"
    d.mkdir()
    (d / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nAAA")
    (d / "b.png").write_bytes(b"\x89PNG\r\n\x1a\nBBB")
    (d / "c.jpg").write_bytes(b"\xff\xd8\xffCCC")
    (d / "ignored.txt").write_text("not an image")
    (d / "sub").mkdir()
    (d / "sub" / "d.png").write_bytes(b"\x89PNG\r\n\x1a\nDDD")
    return d


class FakeVision:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on or set()
        self.calls = 0

    def observe_detailed(self, path):
        from jev_ui_agent.vision.claude_bridge import VisionUnavailable
        self.calls += 1
        if Path(path).name in self.fail_on:
            raise VisionUnavailable("api down")
        return {k: ("none" if k != "texts" else ["Sign in"]) for k in
                ("screen_type", "texts", "images_icons", "colors_style",
                 "error_indicators", "notable")}


class FakeJev:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on or set()
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def judge(self, state, questions):
        from jev_ui_agent.jev.client import JevError
        self.usage["calls"] += 1
        if state["image"] in self.fail_on:
            raise JevError("api down")
        out = {}
        for rid in questions:
            if rid.endswith("_polish"):
                out[rid] = {"value": 4.0, "confidence": 0.95, "probabilities": {}}
            else:
                out[rid] = {"value": 0.9, "confidence": 0.95, "probabilities": {}}
        return out


RULES = """
name: t
rules:
  - id: login_visible
    instruction: "A 'Sign in' button is visible"
  - id: overall_polish
    instruction: "Rate the polish"
    type: score
"""


def _rules_file(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text(RULES, encoding="utf-8")
    return p


def test_scan_images(img_dir):
    assert [p.name for p in scan_images(img_dir)] == ["a.png", "b.png", "c.jpg"]
    assert len(scan_images(img_dir, recursive=True)) == 4


def test_sha256_dedup(img_dir, tmp_path):
    (img_dir / "b.png").write_bytes((img_dir / "a.png").read_bytes())
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=FakeJev(), vision=FakeVision())
    assert report.summary["total_images"] == 4
    assert report.summary["duplicates"] == 1
    # duplicate không tốn thêm call: chỉ a, c, sub/d được phán xét
    assert report.costs["jev"]["calls"] == 3
    assert report.costs["vision"] == {"calls": 3}
    by_name = {cp.checkpoint: cp for cp in report.checkpoints}
    assert by_name["b.png"].results[0].evidence.get("duplicate_of") == "a.png"
    # image gốc không bị dính nhãn duplicate_of của chính nó
    assert "duplicate_of" not in by_name["a.png"].results[0].evidence


def test_run_batch_pass_and_costs(img_dir, tmp_path):
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=FakeJev(), vision=FakeVision())
    s = report.summary
    assert s["total_images"] == 4 and s["passed"] == 4 and s["failed"] == 0
    assert s["needs_review"] == 0 and s["errors"] == 0
    assert report.costs["jev"]["calls"] == 4  # a, b, c, sub/d (không có duplicate)
    assert report.costs["vision"] == {"calls": 4}
    run_dir = tmp_path / "r" / report.run_id
    data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert data["summary"]["total_images"] == 4
    lines = (run_dir / "checkpoint.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and all(json.loads(l)["status"] == "done" for l in lines)


def test_fail_verdict_and_gate(img_dir, tmp_path):
    class PickyJev(FakeJev):
        def judge(self, state, questions):
            out = super().judge(state, questions)
            if state["image"] == "a.png":
                out["login_visible"] = {"value": 0.1, "confidence": 0.95, "probabilities": {}}
                out["overall_polish"] = {"value": 1.0, "confidence": 0.95, "probabilities": {}}
            if state["image"] == "c.jpg":
                out["login_visible"] = {"value": 0.9, "confidence": 0.4, "probabilities": {}}
            return out

    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=PickyJev(), vision=FakeVision())
    s = report.summary
    assert s["failed"] == 1 and s["needs_review"] == 1 and s["passed"] == 2
    assert report.checkpoints[0].checkpoint == "a.png"   # fail-first
    assert report.checkpoints[1].checkpoint == "c.jpg"
    by_name = {cp.checkpoint: cp for cp in report.checkpoints}
    fails = [r.check_id for r in by_name["a.png"].results if r.verdict is Verdict.FAIL]
    assert "rule/login_visible" in fails and "rule/overall_polish" in fails
    nr = next(r for r in by_name["c.jpg"].results if r.check_id == "rule/login_visible")
    assert nr.verdict is Verdict.NEEDS_REVIEW and nr.evidence["pre_gate_verdict"] == "pass"


def test_error_images_recorded(img_dir, tmp_path):
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=FakeJev(fail_on={"a.png"}), vision=FakeVision(fail_on={"c.jpg"}))
    s = report.summary
    assert s["errors"] == 2 and s["passed"] == 2 and s["duplicates"] == 0


def test_limit(img_dir, tmp_path):
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       limit=1, jev=FakeJev(), vision=FakeVision())
    assert report.summary["total_images"] == 1


def test_resume_skips_done_and_retries_errors(img_dir, tmp_path):
    first = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                      policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                      jev=FakeJev(fail_on={"a.png"}), vision=FakeVision())
    run_dir = tmp_path / "r" / first.run_id
    jev2 = FakeJev()
    second = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       resume_dir=run_dir, jev=jev2, vision=FakeVision())
    assert second.run_id == first.run_id
    assert second.summary["errors"] == 0 and second.summary["passed"] == 4
    assert jev2.usage["calls"] == 1  # chỉ retry a.png; b/c/d dùng lại checkpoint done


def test_cp_from_record_roundtrip():
    rec = {"image": "x.png", "hash": "h", "status": "done",
           "report": {"checkpoint": "x.png", "screen_score": 1.0, "screenshot": "x.png",
                      "error": "",
                      "results": [{"check_id": "rule/r1", "group": "rules", "path": "vision+jev",
                                   "verdict": "pass", "score": None, "confidence": 0.9,
                                   "probabilities": {}, "evidence": {"noul": 0.9}, "error": ""}]}}
    cp = _cp_from_record(rec)
    assert cp.checkpoint == "x.png" and cp.results[0].verdict is Verdict.PASS
    assert _image_status(cp) == "passed"
