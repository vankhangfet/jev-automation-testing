import pytest

from jev_ui_agent.checks.composite import VERDICT_VALUE, apply_confidence_gate, score_checkpoint
from jev_ui_agent.models import CheckResult, Verdict


def r(group, verdict):
    return CheckResult(f"c-{group}", group, "rule", verdict)


def test_score_weighted_average():
    results = [r("functional", Verdict.PASS),          # 1.0
               r("layout", Verdict.FAIL),               # 0.0
               r("layout", Verdict.PASS),               # layout mean = 0.5
               r("visual", Verdict.NEEDS_REVIEW)]       # 0.5
    weights = {"functional": 0.35, "layout": 0.20, "visual": 0.10}
    # (0.35*1.0 + 0.20*0.5 + 0.10*0.5) / 0.65 → num=0.35+0.10+0.05=0.50
    assert score_checkpoint(results, weights) == round(0.50 / 0.65, 4)


def test_score_ignores_error_and_skipped():
    results = [r("functional", Verdict.PASS), r("functional", Verdict.ERROR),
               r("visual", Verdict.SKIPPED)]
    assert score_checkpoint(results, {"functional": 0.35, "visual": 0.10}) == 1.0


def test_score_none_when_no_scorable():
    assert score_checkpoint([r("visual", Verdict.SKIPPED)], {"visual": 0.1}) is None


def test_gate_flips_low_confidence():
    res = CheckResult("c", "visual", "vision+jev", Verdict.FAIL, confidence=0.6)
    gated = apply_confidence_gate(res, gate=0.75)
    assert gated.verdict is Verdict.NEEDS_REVIEW
    assert gated.evidence["pre_gate_verdict"] == "fail"


def test_gate_keeps_high_confidence():
    res = CheckResult("c", "visual", "jev", Verdict.PASS, confidence=0.9)
    assert apply_confidence_gate(res, 0.75).verdict is Verdict.PASS


def test_gate_ignores_none_confidence():
    res = CheckResult("c", "content_quality", "jev", Verdict.PASS, confidence=None)
    assert apply_confidence_gate(res, 0.75).verdict is Verdict.PASS


def test_verdict_value_map():
    assert VERDICT_VALUE[Verdict.NEEDS_REVIEW] == 0.5


def test_score_rejects_negative_weight():
    with pytest.raises(ValueError):
        score_checkpoint([r("a", Verdict.PASS)], {"a": -0.5})


def test_gate_idempotent():
    res = CheckResult("c", "visual", "vision+jev", Verdict.FAIL, confidence=0.6)
    apply_confidence_gate(res, gate=0.75)
    # Lần 2 không được ghi đè pre_gate_verdict của lần đầu
    gated_twice = apply_confidence_gate(res, gate=0.75)
    assert gated_twice.verdict is Verdict.NEEDS_REVIEW
    assert gated_twice.evidence["pre_gate_verdict"] == "fail"


def test_gate_ignores_error_and_skipped():
    err = CheckResult("c", "visual", "vision+jev", Verdict.ERROR, confidence=0.1)
    assert apply_confidence_gate(err, 0.75).verdict is Verdict.ERROR
    skip = CheckResult("c", "visual", "vision+jev", Verdict.SKIPPED, confidence=0.1)
    assert apply_confidence_gate(skip, 0.75).verdict is Verdict.SKIPPED
