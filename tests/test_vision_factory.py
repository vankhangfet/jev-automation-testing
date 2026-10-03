import pytest

import jev_ui_agent.vision as vision_pkg
from jev_ui_agent.vision.claude_bridge import VisionBridge
from jev_ui_agent.vision.generic_bridge import GenericVisionBridge


def test_factory_prefers_llm_env(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("MODEL_NAME", "qwen2.5-vl")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_STYLE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    vb = vision_pkg.make_vision_bridge()
    assert isinstance(vb, GenericVisionBridge)
    assert vb.model == "qwen2.5-vl"
    assert vb.style == "openai"          # auto: URL không chứa /v1/messages


def test_factory_anthropic_style_autodetect(monkeypatch):
    monkeypatch.setenv("LLM_URL", "https://gw.internal/anthropic/v1/messages")
    monkeypatch.setenv("MODEL_NAME", "claude-haiku-4-5")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("LLM_STYLE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    vb = vision_pkg.make_vision_bridge()
    assert vb.style == "anthropic"


def test_factory_style_override(monkeypatch):
    monkeypatch.setenv("LLM_URL", "https://gw.internal/api")
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setenv("LLM_STYLE", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert vision_pkg.make_vision_bridge().style == "anthropic"


def test_factory_falls_back_to_anthropic(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "m")  # thiếu LLM_URL → bỏ qua LLM_*
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    assert isinstance(vision_pkg.make_vision_bridge(), VisionBridge)


def test_factory_none_when_nothing(monkeypatch):
    for var in ("LLM_URL", "MODEL_NAME", "LLM_API_KEY", "LLM_STYLE", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert vision_pkg.make_vision_bridge() is None


def test_factory_bad_style_raises(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://x/v1")
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setenv("LLM_STYLE", "bogus")
    with pytest.raises(ValueError):
        vision_pkg.make_vision_bridge()
