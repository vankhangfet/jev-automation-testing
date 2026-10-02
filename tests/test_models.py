from jev_ui_agent.models import Bounds, CheckResult, Verdict


def test_bounds_props():
    b = Bounds(10, 20, 110, 270)
    assert b.width == 100
    assert b.height == 250
    assert b.area == 25000


def test_bounds_intersection():
    a = Bounds(0, 0, 100, 100)
    b = Bounds(50, 50, 150, 150)
    inter = a.intersection(b)
    assert inter == Bounds(50, 50, 100, 100)
    assert a.intersection(Bounds(200, 200, 300, 300)) is None


def test_bounds_area_clamps_inverted():
    assert Bounds(100, 100, 0, 0).area == 0
    assert Bounds(0, 0, -50, -50).area == 0


def test_verdict_values():
    assert Verdict.PASS.value == "pass"
    assert Verdict.NEEDS_REVIEW.value == "needs_review"
    r = CheckResult("x", "layout", "rule", Verdict.PASS)
    assert r.probabilities == {}
    assert r.evidence == {}
