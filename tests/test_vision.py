from types import SimpleNamespace

import pytest

import jev_ui_agent.vision.claude_bridge as bridge_mod
from jev_ui_agent.vision.claude_bridge import VisionBridge, VisionUnavailable, _extract_json


def _msg(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_extract_json_plain_and_fenced():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('blah ```json\n{"a": 2}\n``` trailing') == {"a": 2}


def test_observe_parses_json(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")

    fake_client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: _msg('```json\n{"blank_areas": "none", "broken_images": "none",'
                                 ' "text_cut": "none", "summary": "ok"}\n```')))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge()
    obs = vb.observe(str(img))
    assert obs["summary"] == "ok"
    assert vb.calls == 1


def test_observe_retries_then_unavailable(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")
    calls = {"n": 0}

    def boom(**kw):
        calls["n"] += 1
        raise RuntimeError("api down")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge(retries=1)
    with pytest.raises(VisionUnavailable):
        vb.observe(str(img))
    assert calls["n"] == 2
