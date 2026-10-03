from __future__ import annotations

import os


def make_vision_bridge(max_tokens: int = 2048):
    """Chọn vision bridge theo env: LLM_URL+MODEL_NAME ưu tiên, fallback ANTHROPIC_API_KEY."""
    url = os.environ.get("LLM_URL")
    model = os.environ.get("MODEL_NAME")
    api_key = os.environ.get("LLM_API_KEY")
    if url and model:
        style = os.environ.get("LLM_STYLE", "").strip().lower() or \
            ("anthropic" if "/v1/messages" in url else "openai")
        if style not in ("openai", "anthropic"):
            raise ValueError(f"LLM_STYLE phải là 'openai' hoặc 'anthropic', got {style!r}")
        from jev_ui_agent.vision.generic_bridge import GenericVisionBridge
        return GenericVisionBridge(base_url=url, model=model, api_key=api_key or None,
                                   style=style, max_tokens=max_tokens)
    if os.environ.get("ANTHROPIC_API_KEY"):
        from jev_ui_agent.vision.claude_bridge import VisionBridge
        return VisionBridge(max_tokens=max_tokens)
    return None
