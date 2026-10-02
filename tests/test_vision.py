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

    seen = {}

    def create(**kw):
        seen.update(kw)
        return _msg('```json\n{"blank_areas": "none", "broken_images": "none",'
                    ' "text_cut": "none", "summary": "ok"}\n```')

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge()
    obs = vb.observe(str(img))
    assert obs["summary"] == "ok"
    assert vb.calls == 1
    # Wire format lock: đúng model, max_tokens, và image block base64 PNG
    assert seen["model"] == vb.model
    assert "max_tokens" in seen
    first = seen["messages"][0]["content"][0]
    assert first["type"] == "image"
    assert first["source"]["media_type"] == "image/png"
    assert first["source"]["data"]


def test_observe_missing_file_raises_unavailable(monkeypatch, tmp_path):
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: _msg("{}")))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge()
    with pytest.raises(VisionUnavailable):
        vb.observe(str(tmp_path / "nope.png"))


def test_observe_retries_then_unavailable(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")
    calls = {"n": 0}

    def boom(**kw):
        calls["n"] += 1
        raise RuntimeError("api down")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    monkeypatch.setattr(bridge_mod.time, "sleep", lambda s: None)
    vb = VisionBridge(retries=1)
    with pytest.raises(VisionUnavailable):
        vb.observe(str(img))
    assert calls["n"] == 2


def test_observe_garbage_text_retries_then_unavailable(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")
    creates = {"n": 0}

    def create(**kw):
        creates["n"] += 1
        return _msg("the screen looks fine, no issues found")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    monkeypatch.setattr(bridge_mod.time, "sleep", lambda s: None)
    vb = VisionBridge(retries=1)
    with pytest.raises(VisionUnavailable):
        vb.observe(str(img))
    assert creates["n"] == 2
    assert vb.calls == 2


def test_observe_no_final_sleep(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")
    sleeps = []

    def boom(**kw):
        raise RuntimeError("api down")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    monkeypatch.setattr(bridge_mod.time, "sleep", lambda s: sleeps.append(s))
    vb = VisionBridge(retries=1)
    with pytest.raises(VisionUnavailable):
        vb.observe(str(img))
    assert sleeps == [0.5]


def test_observe_normalizes_missing_keys(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")

    fake_client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: _msg('{"summary": "x"}')))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge()
    obs = vb.observe(str(img))
    assert obs == {"blank_areas": "none", "broken_images": "none",
                   "text_cut": "none", "summary": "x"}
