from pathlib import Path

from jev_ui_agent.extract.normalize import build_state, parse_android, parse_bounds_str, parse_ios
from jev_ui_agent.models import StepArtifact

FIX = Path(__file__).parent / "fixtures"


def test_parse_bounds_negative_coords():
    b = parse_bounds_str("[-315,1560][0,2400]")
    assert (b.x1, b.y1, b.x2, b.y2) == (-315, 1560, 0, 2400)
    b2 = parse_bounds_str("[0,-100][1080,200]")
    assert (b2.x1, b2.y1, b2.x2, b2.y2) == (0, -100, 1080, 200)


def test_parse_android():
    els = parse_android((FIX / "android_home.xml").read_text(encoding="utf-8"))
    labels = {e.label for e in els}
    assert "Sign in" in labels and "login.title" in labels
    assert "Hidden" not in labels  # ghost bị lọc
    assert all(e.displayed for e in els)
    btn = next(e for e in els if e.label == "Sign in")
    assert btn.id == "com.example:id/login_btn"
    assert btn.type == "Button"
    assert (btn.bounds.x1, btn.bounds.y1, btn.bounds.x2, btn.bounds.y2) == (100, 800, 980, 880)


def test_parse_ios():
    els = parse_ios((FIX / "ios_login.xml").read_text(encoding="utf-8"))
    btn = next(e for e in els if e.type == "Button")
    assert btn.content_desc == "Sign in"
    assert btn.id == "signin_btn"
    assert btn.clickable
    tf = next(e for e in els if e.type == "TextField")
    assert tf.text == "demo@example.com"
    assert "Ghost" not in {e.content_desc for e in els}  # Ghost visible=false bị lọc
    assert all(e.id != "hidden_lbl" for e in els)
    assert all(e.displayed for e in els)


def test_build_state_and_find():
    artifact = StepArtifact(
        checkpoint="home",
        screenshot_path="/tmp/x.png",
        source_xml=(FIX / "android_home.xml").read_text(encoding="utf-8"),
        activity=".MainActivity",
    )
    state = build_state(artifact, run_id="run-1", platform="android",
                        app="com.example", viewport={"width": 1080, "height": 2400})
    assert state.checkpoint == "home"
    found = state.find("res-id:login_btn")
    assert found is not None and found.label == "Sign in"
    assert state.find("acc-id:Hero image").type == "ImageView"


def test_build_state_caps_elements():
    artifact = StepArtifact(checkpoint="c", screenshot_path="",
                            source_xml=(FIX / "android_home.xml").read_text(encoding="utf-8"))
    state = build_state(artifact, run_id="r", platform="android", app="a",
                        viewport={"width": 1080, "height": 2400}, max_elements=2)
    assert len(state.elements) == 2
