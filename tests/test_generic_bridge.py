from types import SimpleNamespace

import pytest

import jev_ui_agent.vision.generic_bridge as gb_mod
from jev_ui_agent.vision.generic_bridge import GenericVisionBridge
from jev_ui_agent.vision.claude_bridge import VisionUnavailable


def _ok_openai(body_text):
    return SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: {"choices": [{"message": {"content": body_text}}]},
    )


def test_openai_payload_and_parse(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nAAA")
    seen = {}

    def post(url, headers=None, json=None):
        seen.update(url=url, headers=headers, json=json)
        return _ok_openai('```json\n{"blank_areas": "none", "broken_images": "none",'
                          ' "text_cut": "none", "summary": "ok"}\n```')

    fake = SimpleNamespace(post=post)
    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: fake)
    bridge = GenericVisionBridge(base_url="http://localhost:11434/v1", model="qwen",
                                 api_key=None, style="openai")
    obs = bridge.observe(str(img))
    assert obs["summary"] == "ok"
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert "Authorization" not in seen["headers"]
    content = seen["json"]["messages"][0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert seen["json"]["model"] == "qwen" and seen["json"]["max_tokens"] == 1024
    assert "mobile UI test observer" in seen["json"]["messages"][0]["content"][1]["text"]
    assert bridge.calls == 1


def test_openai_bearer_key_and_url_suffix(monkeypatch, tmp_path):
    img = tmp_path / "shot.jpg"
    img.write_bytes(b"\xff\xd8\xff jpeg")
    seen = {}

    def post(url, headers=None, json=None):
        seen.update(url=url, headers=headers)
        return _ok_openai('{"blank_areas": "none", "broken_images": "none",'
                          ' "text_cut": "none", "summary": "k"}')

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="https://openrouter.ai/api/v1/chat/completions",
                                 model="m", api_key="sk-x", style="openai")
    bridge.observe(str(img))
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"  # không nối đôi
    assert seen["headers"]["Authorization"] == "Bearer sk-x"


def test_anthropic_style_request(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")
    seen = {}

    def post(url, headers=None, json=None):
        seen.update(url=url, headers=headers, json=json)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {
            "content": [{"type": "text", "text": '{"blank_areas": "none", "broken_images": "none",'
                                                 ' "text_cut": "none", "summary": "a"}'}]})

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="https://gw/v1", model="claude-x",
                                 api_key="k2", style="anthropic")
    obs = bridge.observe(str(img))
    assert obs["summary"] == "a"
    assert seen["url"] == "https://gw/v1/messages"
    assert seen["headers"]["x-api-key"] == "k2"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["json"]["model"] == "claude-x"
    assert seen["json"]["messages"][0]["content"][0]["type"] == "image"


def test_http_error_retries_then_unavailable(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")
    calls = {"n": 0}

    def post(url, headers=None, json=None):
        calls["n"] += 1
        raise gb_mod.httpx.HTTPError("boom")

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="http://x/v1", model="m", style="openai", retries=1)
    bridge._sleep = lambda s: None
    with pytest.raises(VisionUnavailable):
        bridge.observe(str(img))
    assert calls["n"] == 2
    assert bridge.calls == 0  # attempt fail không đếm — calls là billing events


def _err_response(status, body):
    return SimpleNamespace(status_code=status, text=body, json=lambda: (_ for _ in ()).throw(ValueError(body)))


def test_http_4xx_surfaces_body_and_does_not_retry(monkeypatch, tmp_path):
    """400 do model sai là lỗi cấu hình — phải hiện body lỗi của endpoint, không retry."""
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")
    calls = {"n": 0}

    def post(url, headers=None, json=None):
        calls["n"] += 1
        return _err_response(400, '{"error":{"code":"1211","message":"Unknown Model,'
                                  ' please check the model code."}}')

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="http://x/v1", model="glm-5.3v",
                                 style="openai", retries=1)
    bridge._sleep = lambda s: None
    with pytest.raises(VisionUnavailable) as exc_info:
        bridge.observe(str(img))
    assert calls["n"] == 1  # 4xx là lỗi vĩnh viễn — không thử lại
    assert bridge.calls == 0
    assert "HTTP 400" in str(exc_info.value)
    assert "Unknown Model" in str(exc_info.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_transient_errors_still_retry(monkeypatch, tmp_path, status):
    """429/5xx có thể thoáng qua — vẫn retry theo cấu hình."""
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")
    calls = {"n": 0}

    def post(url, headers=None, json=None):
        calls["n"] += 1
        return _err_response(status, "server busy")

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="http://x/v1", model="m", style="openai", retries=1)
    bridge._sleep = lambda s: None
    with pytest.raises(VisionUnavailable) as exc_info:
        bridge.observe(str(img))
    assert calls["n"] == 2
    assert f"HTTP {status}" in str(exc_info.value)


def test_empty_content_gives_reasoning_hint(monkeypatch, tmp_path):
    """Model reasoning (GLM) có thể trả content rỗng — lỗi phải gợi ý tăng max_tokens/đổi model."""
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")
    calls = {"n": 0}

    def post(url, headers=None, json=None):
        calls["n"] += 1
        return _ok_openai("")

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="http://x/v1", model="m", style="openai", retries=1)
    bridge._sleep = lambda s: None
    with pytest.raises(VisionUnavailable) as exc_info:
        bridge.observe(str(img))
    assert calls["n"] == 2 and bridge.calls == 2  # HTTP hoàn tất — billing event
    assert "empty content" in str(exc_info.value)
    assert "max_tokens" in str(exc_info.value)


def test_garbage_text_retries_then_unavailable(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")
    calls = {"n": 0}

    def post(url, headers=None, json=None):
        calls["n"] += 1
        return _ok_openai("totally not json <<<>>> garbage")

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="http://x/v1", model="m", style="openai", retries=1)
    bridge._sleep = lambda s: None
    with pytest.raises(VisionUnavailable) as exc_info:
        bridge.observe(str(img))
    assert calls["n"] == 2
    assert bridge.calls == 2  # HTTP đã hoàn tất — vẫn là billing event (như claude_bridge)
    assert "unparseable observation" in str(exc_info.value)
    assert "totally not json" in str(exc_info.value)


def test_openai_content_list_parts(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")

    def post(url, headers=None, json=None):
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {
            "choices": [{"message": {"content": [
                {"type": "text", "text": '{"blank_areas": "none", '},
                {"type": "text", "text": '"broken_images": "none", "text_cut": "none",'
                                         ' "summary": "split"}'},
            ]}}]})

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="http://x/v1", model="m", style="openai")
    obs = bridge.observe(str(img))
    assert obs["summary"] == "split"


@pytest.mark.parametrize("base,expected", [
    ("https://gw/anthropic/v1/messages", "https://gw/anthropic/v1/messages"),  # giữ nguyên
    ("https://api.anthropic.com", "https://api.anthropic.com/v1/messages"),   # bare → nối
])
def test_anthropic_endpoint_suffix(base, expected, monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")
    seen = {}

    def post(url, headers=None, json=None):
        seen["url"] = url
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {
            "content": [{"type": "text", "text": '{"blank_areas": "none", "broken_images": "none",'
                                                 ' "text_cut": "none", "summary": "e"}'}]})

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url=base, model="m", style="anthropic")
    bridge.observe(str(img))
    assert seen["url"] == expected


def test_observe_detailed_reuses_normalize(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nX")

    def post(url, headers=None, json=None):
        return _ok_openai('{"screen_type": "login", "texts": ["Hi"]}')

    monkeypatch.setattr(gb_mod.httpx, "Client", lambda **kw: SimpleNamespace(post=post))
    bridge = GenericVisionBridge(base_url="http://x/v1", model="m", style="openai")
    obs = bridge.observe_detailed(str(img))
    assert obs["screen_type"] == "login" and obs["layout"] == [] and obs["notable"] == "none"
