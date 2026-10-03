from __future__ import annotations

import base64
import json
import re
import threading
import time
from pathlib import Path

from anthropic import Anthropic

# Model id pin — tham khảo claude-api skill khi nâng cấp
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

OBSERVE_PROMPT = (
    "You are a mobile UI test observer. Look at the screenshot and report ONLY what is "
    "visually verifiable. Be terse and factual, no speculation. "
    "Return a single JSON object with exactly these keys: "
    '"blank_areas": description of large blank/unrendered areas or "none", '
    '"broken_images": description of broken/missing images or rendering artifacts or "none", '
    '"text_cut": description of any text that appears clipped/truncated or "none", '
    '"summary": one-sentence overall visual summary.'
)

OBS_KEY = ("blank_areas", "broken_images", "text_cut", "summary")

DETAILED_OBSERVE_PROMPT = (
    "You are a mobile UI test observer. Look at the screenshot and report ONLY what is "
    "visually verifiable. Be terse and factual, no speculation. "
    "Return a single JSON object with exactly these keys: "
    '"screen_type": your best-guess name for this kind of screen, '
    '"layout": array of {"region": short-area-name, "contents": what is in it}, '
    '"texts": array of the exact visible texts (cap 30, most prominent first), '
    '"images_icons": description of imagery/photos/icons present, '
    '"colors_style": dominant colors, light/dark theme, notable styling, '
    '"error_indicators": any error messages, crash dialogs, empty-state or loading indicators, or "none", '
    '"notable": anything unusual such as clipping, overlapping elements, placeholder or garbled text, or "none".'
)

OBS_DETAIL_KEYS = ("screen_type", "layout", "texts", "images_icons", "colors_style",
                   "error_indicators", "notable")

# Key normalize về list rỗng thay vì "none" khi model bỏ sót
_LIST_KEYS = ("layout", "texts")

_MAGIC = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"))

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _sniff_media_type(data: bytes) -> str:
    for magic, media in _MAGIC:
        if data.startswith(magic):
            return media
    return "image/png"  # default


class VisionUnavailable(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    m = _FENCE_RE.search(text)
    return json.loads(m.group(1) if m else text)


def _normalize_obs(obs: dict, keys: tuple[str, ...]) -> dict:
    """Fill đủ keys: list-keys → [], còn lại 'none'."""
    return {k: obs.get(k, [] if k in _LIST_KEYS else "none") for k in keys}


class VisionBridge:
    """Gọi Claude trả observation JSON có cấu trúc cho JEV phán xét."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL,
                 retries: int = 1, max_tokens: int = 1024):
        self._client = Anthropic(api_key=api_key)  # đọc ANTHROPIC_API_KEY từ env
        self.model = model
        self.retries = retries
        self.max_tokens = max_tokens
        self.calls = 0
        self._lock = threading.Lock()

    def observe(self, image_path: str) -> dict:
        return self._observe(image_path, prompt=OBSERVE_PROMPT, keys=OBS_KEY)

    def observe_detailed(self, image_path: str) -> dict:
        return self._observe(image_path, prompt=DETAILED_OBSERVE_PROMPT,
                             keys=OBS_DETAIL_KEYS)

    def _observe(self, image_path: str, *, prompt: str,
                 keys: tuple[str, ...]) -> dict:
        try:
            raw = Path(image_path).read_bytes()
        except OSError as e:
            raise VisionUnavailable(f"cannot read screenshot {image_path}: {e}") from e
        media_type = _sniff_media_type(raw)
        data = base64.b64encode(raw).decode()
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            text = ""
            try:
                msg = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image",
                             "source": {"type": "base64", "media_type": media_type,
                                        "data": data}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
                with self._lock:
                    self.calls += 1
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
                obs = _extract_json(text)
                if not isinstance(obs, dict):
                    raise ValueError(f"observation is not a JSON object: {text[:200]!r}")
                return _normalize_obs(obs, keys)
            except Exception as e:  # noqa: BLE001 — layer boundary
                if text:
                    last_err = ValueError(f"unparseable observation: {text[:200]!r}")
                else:
                    last_err = e
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        raise VisionUnavailable(str(last_err)) from last_err
