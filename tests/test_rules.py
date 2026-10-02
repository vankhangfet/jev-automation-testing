from jev_ui_agent.checks.rules import functional_checks, layout_checks
from jev_ui_agent.models import Bounds, ScreenState, UIElement, Verdict

POLICY = {
    "functional_expectations": [
        {"checkpoint": "home", "element": "res-id:login_btn", "expect_text": "Sign in"},
        {"checkpoint": "home", "element": "res-id:missing_btn", "expect_text": None},
        {"checkpoint": "other", "element": "res-id:x", "expect_text": None},
    ],
    "layout": {"overlap_min_ratio": 0.10, "offscreen_tolerance_px": 2,
               "truncation_char_width_ratio": 0.025},
}


def make_state(els, checkpoint="home"):
    return ScreenState(run_id="r", checkpoint=checkpoint, platform="android",
                       app="a", viewport={"width": 1080, "height": 2400}, elements=els)


def test_functional_pass_fail():
    els = [UIElement(id="com.example:id/login_btn", text="Sign in", type="Button")]
    results = functional_checks(make_state(els), POLICY)
    by_id = {r.check_id: r for r in results}
    assert by_id["functional/element:res-id:login_btn"].verdict is Verdict.PASS
    assert by_id["functional/element:res-id:missing_btn"].verdict is Verdict.FAIL


def test_functional_text_mismatch():
    els = [UIElement(id="com.example:id/login_btn", text="Sign In!", type="Button")]
    results = functional_checks(make_state(els), POLICY)
    r = next(r for r in results if r.check_id.endswith("login_btn"))
    assert r.verdict is Verdict.FAIL
    assert r.evidence["expected"] == "Sign in"


def test_functional_no_expectations_skipped():
    results = functional_checks(make_state([], checkpoint="nowhere"), POLICY)
    assert results[0].verdict is Verdict.SKIPPED


def test_functional_missing_element_key_error():
    policy = {"functional_expectations": [
        {"checkpoint": "home", "expect_text": "x"},  # thiếu key "element"
    ]}
    results = functional_checks(make_state([], checkpoint="home"), policy)
    assert results[0].verdict is Verdict.ERROR
    assert results[0].check_id == "functional/element:invalid"


def test_functional_bad_selector_error():
    policy = {"functional_expectations": [
        {"checkpoint": "home", "element": "no-prefix"},
    ]}
    results = functional_checks(make_state([], checkpoint="home"), policy)
    assert results[0].verdict is Verdict.ERROR


def test_layout_overlap_detected():
    els = [
        UIElement(id="a", text="Hello", bounds=Bounds(0, 0, 200, 100)),
        UIElement(id="b", text="World", bounds=Bounds(50, 0, 250, 100)),
    ]
    results = layout_checks(make_state(els), POLICY)
    overlaps = [r for r in results if r.check_id.startswith("layout/overlap")]
    assert overlaps[0].verdict is Verdict.FAIL


def test_overlap_text_over_image_not_flagged():
    # content_desc-only element chồng chữ là pattern text-over-image bình thường
    els = [
        UIElement(id="img", content_desc="Hero banner image",
                  bounds=Bounds(0, 0, 1080, 400)),
        UIElement(id="txt", text="Breaking News", bounds=Bounds(40, 100, 800, 160)),
    ]
    results = layout_checks(make_state(els), POLICY)
    assert all(r.verdict is not Verdict.FAIL
               for r in results if r.check_id.startswith("layout/overlap"))


def test_layout_clean_pass():
    els = [
        UIElement(id="a", text="Hello", bounds=Bounds(0, 0, 200, 100)),
        UIElement(id="b", text="World", bounds=Bounds(0, 200, 200, 300)),
    ]
    results = layout_checks(make_state(els), POLICY)
    assert all(r.verdict is Verdict.PASS for r in results)


def test_layout_offscreen_fail():
    # chỉ ~14% hiển thị ((1082-900)*100 / (1300*100)) → FAIL
    els = [UIElement(id="a", text="Far", bounds=Bounds(900, 0, 2200, 100))]
    results = layout_checks(make_state(els), POLICY)
    off = [r for r in results if r.check_id.startswith("layout/offscreen")]
    assert off[0].verdict is Verdict.FAIL


def test_offscreen_partial_clip_passes():
    # 77% hiển thị → row bị cắt nhẹ ở mép scroll là bình thường → PASS
    els = [UIElement(id="a", text="Header", bounds=Bounds(0, -30, 1080, 100))]
    results = layout_checks(make_state(els), POLICY)
    off = [r for r in results if r.check_id.startswith("layout/offscreen")]
    assert off[0].verdict is Verdict.PASS


def test_offscreen_fully_outside_fails():
    els = [UIElement(id="a", text="Ghost", bounds=Bounds(0, -500, 1080, -300))]
    results = layout_checks(make_state(els), POLICY)
    off = [r for r in results if r.check_id.startswith("layout/offscreen")]
    assert off[0].verdict is Verdict.FAIL


def test_empty_screen_layout_skipped():
    results = layout_checks(make_state([]), POLICY)
    ids = {r.check_id: r for r in results}
    assert set(ids) == {"layout/overlap", "layout/offscreen",
                        "layout/truncation_candidates"}
    assert all(r.verdict is Verdict.SKIPPED for r in results)


def test_layout_truncation_candidates_needs_review():
    # 40 ký tự * (1080*0.025=27px) = 1080px > width 300
    els = [UIElement(id="a", text="x" * 40, bounds=Bounds(0, 0, 300, 100))]
    results = layout_checks(make_state(els), POLICY)
    tr = next(r for r in results if r.check_id == "layout/truncation_candidates")
    assert tr.verdict is Verdict.NEEDS_REVIEW
    assert "x" * 40 in tr.evidence["candidates"]
