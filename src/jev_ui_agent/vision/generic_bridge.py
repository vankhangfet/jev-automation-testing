from __future__ import annotations

import base64
import threading
import time
from pathlib import Path

import httpx

from jev_ui_agent.vision.claude_bridge import (
    DETAILED_OBSERVE_PROMPT, OBS_DETAIL_KEYS, OBS_KEY, OBSERVE_PROMPT,
    VisionUnavailable, _extract_json, _normalize_obs, _sniff_media_type,
)


class _PermanentVisionError(VisionUnavailable):
    """HTTP 4xx (trừ 408/429) — lỗi cấu hình (sai model, sai key...), thử lại không giúp gì."""


class GenericVisionBridge:
    """Vision bridge cho endpoint LLM tùy ý (OpenAI-style hoặc Anthropic-style).

    Cùng interface với VisionBridge: observe / observe_detailed / calls,
    raise VisionUnavailable khi không dùng được.
    """

    def __init__(self, *, base_url: str, model: str, api_key: str | None = None,
                 style: str = "openai", retries: int = 1, max_tokens: int = 1024,
                 timeout: float = 120.0):
        if style not in ("openai", "anthropic"):
            raise ValueError(f"style phải là 'openai' hoặc 'anthropic', got {style!r}")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.style = style
        self.retries = retries
        self.max_tokens = max_tokens
        self._client = httpx.Client(timeout=timeout)
        self._lock = threading.Lock()
        self.calls = 0
        self._sleep = time.sleep

    def _endpoint(self) -> str:
        if self.style == "anthropic":
            if self.base_url.endswith("/messages"):
                return self.base_url
            if self.base_url.endswith("/v1"):
                return self.base_url + "/messages"
            return self.base_url + "/v1/messages"
        return self.base_url if self.base_url.endswith("/chat/completions") \
            else self.base_url + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        if self.style == "anthropic":
            headers = {"anthropic-version": "2023-06-01", "Content-Type": "application/json"}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            return headers
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, prompt: str, media_type: str, data_b64: str) -> str:
        if self.style == "anthropic":
            payload = {"model": self.model, "max_tokens": self.max_tokens,
                       "messages": [{"role": "user", "content": [
                           {"type": "image",
                            "source": {"type": "base64", "media_type": media_type,
                                       "data": data_b64}},
                           {"type": "text", "text": prompt}]}]}
        else:
            payload = {"model": self.model, "max_tokens": self.max_tokens,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{data_b64}"}},
                           {"type": "text", "text": prompt}]}]}
        resp = self._client.post(self._endpoint(), headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            # Giữ lại body lỗi của endpoint (VD "Unknown Model",
            # "messages.content.type is invalid") — raise_for_status() vứt nó đi.
            detail = (resp.text or "").strip()[:300]
            msg = f"vision endpoint HTTP {resp.status_code}: {detail}"
            if 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
                raise _PermanentVisionError(msg)
            raise VisionUnavailable(msg)
        body = resp.json()
        if self.style == "anthropic":
            parts = body.get("content", [])
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        msg = (body.get("choices") or [{}])[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return content or ""

    def _observe(self, image_path: str, *, prompt: str, keys: tuple[str, ...]) -> dict:
        try:
            raw = Path(image_path).read_bytes()
        except OSError as e:
            raise VisionUnavailable(f"cannot read screenshot {image_path}: {e}") from e
        data_b64 = base64.b64encode(raw).decode()
        media = _sniff_media_type(raw)
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                text = self._request(prompt, media, data_b64)
                with self._lock:
                    self.calls += 1
                try:
                    obs = _extract_json(text)
                except ValueError as e:
                    if not text.strip():
                        raise ValueError(
                            "vision model returned empty content — the model may have "
                            "spent the token budget on reasoning; try a higher max_tokens "
                            "or another model") from e
                    raise ValueError(f"unparseable observation: {text[:200]!r}") from e
                if not isinstance(obs, dict):
                    raise ValueError(f"observation không phải JSON object: {text[:200]!r}")
                return _normalize_obs(obs, keys)
            except _PermanentVisionError:
                raise
            except Exception as e:  # noqa: BLE001 — layer boundary
                last_err = e
                if attempt < self.retries:
                    self._sleep(0.5 * (attempt + 1))
        raise VisionUnavailable(str(last_err)) from last_err

    def observe(self, image_path: str) -> dict:
        return self._observe(image_path, prompt=OBSERVE_PROMPT, keys=OBS_KEY)

    def observe_detailed(self, image_path: str) -> dict:
        return self._observe(image_path, prompt=DETAILED_OBSERVE_PROMPT, keys=OBS_DETAIL_KEYS)
