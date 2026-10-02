from jev_ui_agent.checks.router import run_checks
from jev_ui_agent.jev.client import JevError
from jev_ui_agent.models import Bounds, ScreenState, UIElement, Verdict
from jev_ui_agent.vision.claude_bridge import VisionUnavailable

POLICY = {
    "confidence_gate": 0.75,
    "check_toggles": {"functional": True, "layout": True, "content_quality": True,
                      "error_anomaly": True, "visual": True},
    "layout": {"overlap_min_ratio": 0.1, "offscreen_tolerance_px": 2,
               "truncation_char_width_ratio": 0.025},
    "content_quality": {"typo_pass_score": 0.75},
}


def make_state():
    return ScreenState(run_id="r", checkpoint="home", platform="android", app="a",
                       viewport={"width": 1080, "height": 2400},
                       elements=[UIElement(id="com.a:id/t", text="login.title",
                                           bounds=Bounds(0, 0, 200, 50))],
                       screenshot="shot.png")


class FakeJev:
    def __init__(self, answers=None, error=None):
        self.answers = answers or {}
        self.error = error
        self.states = []
        self.seen_questions = []

    def judge(self, state, questions):
        if self.error:
            raise JevError(self.error)
        self.states.append(state)
        self.seen_questions.append(questions)
        return self.answers


class FakeVision:
    def __init__(self, observation=None, error=None):
        self.observation = observation or {"blank_areas": "none", "broken_images": "none",
                                           "text_cut": "none", "summary": "ok"}
        self.error = error
        self.calls = 0

    def observe(self, path):
        self.calls += 1
        if self.error:
            raise VisionUnavailable(self.error)
        return self.observation


def core_answers(noul=0.0, choice="normal", score=4.0, conf=0.95):
    return {
        "screen_class": {"value": choice, "confidence": conf,
                         "probabilities": {"normal": 1.0}},
        "has_raw_i18n_key": {"value": noul, "confidence": conf, "probabilities": {}},
        "has_dev_text": {"value": 0.0, "confidence": conf, "probabilities": {}},
        "typo_severity": {"value": score, "confidence": conf, "probabilities": {}},
    }


def test_rule_groups_run_without_jev():
    results = run_checks(make_state(), POLICY, jev=None, vision=None)
    ids = {r.check_id for r in results}
    assert "layout/overlap" in ids
    # các nhóm jev/vision đánh dấu skipped khi thiếu client
    assert all(r.verdict is Verdict.SKIPPED for r in results if r.path in ("jev", "vision+jev"))


def test_jev_i18n_bug_detected():
    jev = FakeJev(answers=core_answers(noul=0.9))  # i18n key gần chắc chắn
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "content_quality/raw_i18n_key")
    assert r.verdict is Verdict.FAIL
    assert r.evidence["noul"] == 0.9


def test_jev_error_screen_classified():
    jev = FakeJev(answers=core_answers(choice="error_screen"))
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "error_anomaly/screen_class")
    assert r.verdict is Verdict.FAIL
    assert r.evidence["classified"] == "error_screen"


def test_jev_empty_state_needs_review():
    jev = FakeJev(answers=core_answers(choice="empty_state"))
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "error_anomaly/screen_class")
    assert r.verdict is Verdict.NEEDS_REVIEW
    assert r.evidence["classified"] == "empty_state"


def test_confidence_gate_flips_to_needs_review():
    jev = FakeJev(answers=core_answers(noul=0.9, conf=0.5))
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "content_quality/raw_i18n_key")
    assert r.verdict is Verdict.NEEDS_REVIEW
    assert r.evidence["pre_gate_verdict"] == "fail"


def test_typo_score_normalized():
    jev = FakeJev(answers=core_answers(score=3.0))  # 3/4 = 0.75 → pass ở ngưỡng 0.75
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "content_quality/typo")
    assert r.verdict is Verdict.PASS and r.score == 0.75


def test_typo_score_fail_direction():
    jev = FakeJev(answers=core_answers(score=1.0))  # 1/4 = 0.25 < 0.75 → fail
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "content_quality/typo")
    assert r.verdict is Verdict.FAIL and r.score == 0.25


def test_visual_path_with_observation():
    jev = FakeJev(answers={
        "visual_blank": {"value": 0.9, "confidence": 0.95, "probabilities": {}},
        "visual_broken": {"value": 0.0, "confidence": 0.95, "probabilities": {}},
        "visual_text_cut": {"value": 0.0, "confidence": 0.95, "probabilities": {}},
    })
    vision = FakeVision()
    results = run_checks(make_state(), POLICY, jev=jev, vision=vision)
    assert vision.calls == 1
    assert len(jev.states) == 2  # fan-out đúng 2 call: core + visual
    r = next(r for r in results if r.check_id == "visual/blank")
    assert r.verdict is Verdict.FAIL and r.path == "vision+jev"
    # state thứ 2 (visual) phải chứa visual_observation
    assert "visual_observation" in jev.states[1]


def test_visual_unavailable_marks_skipped():
    jev = FakeJev(answers={})
    vision = FakeVision(error="api down")
    results = run_checks(make_state(), POLICY, jev=jev, vision=vision)
    vis = [r for r in results if r.group == "visual"]
    assert vis and all(r.verdict is Verdict.SKIPPED for r in vis)


def test_visual_jev_error_marks_error():
    jev = FakeJev(error="api down")
    vision = FakeVision()
    results = run_checks(make_state(), POLICY, jev=jev, vision=vision)
    vis = [r for r in results if r.group == "visual"]
    assert len(vis) == 3
    assert all(r.verdict is Verdict.ERROR and r.path == "vision+jev" for r in vis)
    assert vision.calls == 1  # observe đã chạy trước khi jev fail


def test_jev_error_marks_error():
    jev = FakeJev(error="api down")
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    errs = [r for r in results if r.verdict is Verdict.ERROR]
    assert errs and all(r.path == "jev" for r in errs)


def test_toggles_disable_groups():
    policy = dict(POLICY, check_toggles={"functional": False, "layout": False,
                                         "content_quality": True, "error_anomaly": True,
                                         "visual": False})
    results = run_checks(make_state(), policy, jev=FakeJev(answers=core_answers()),
                         vision=FakeVision())
    assert results, "jev groups vẫn chạy"
    assert all(r.group in ("content_quality", "error_anomaly") for r in results)


def test_partial_toggle_asks_and_emits_only_enabled_groups():
    # FakeJev trả đủ 4 answers bất kể câu hỏi — router phải lọc theo questions đã hỏi
    policy = dict(POLICY, check_toggles=dict(POLICY["check_toggles"],
                                             content_quality=False))
    jev = FakeJev(answers=core_answers())
    results = run_checks(make_state(), policy, jev=jev, vision=None)
    assert not [r for r in results if r.check_id.startswith("content_quality/")]
    assert "screen_class" in jev.seen_questions[0]
    assert not any(k in jev.seen_questions[0] for k in
                   ("has_raw_i18n_key", "has_dev_text", "typo_severity"))
