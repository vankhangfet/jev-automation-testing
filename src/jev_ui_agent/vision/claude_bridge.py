from __future__ import annotations

import base64
import json
import re
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

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class VisionUnavailable(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    m = _FENCE_RE.search(text)
    return json.loads(m.group(1) if m else text)


class VisionBridge:
    """Gọi Claude trả observation JSON có cấu trúc cho JEV phán xét."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL,
                 retries: int = 1, max_tokens: int = 1024):
        self._client = Anthropic(api_key=api_key)  # đọc ANTHROPIC_API_KEY từ env
        self.model = model
        self.retries = retries
        self.max_tokens = max_tokens
        self.calls = 0

    def observe(self, image_path: str) -> dict:
        data = base64.b64encode(Path(image_path).read_bytes()).decode()
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self.calls += 1
                msg = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image",
                             "source": {"type": "base64", "media_type": "image/png",
                                        "data": data}},
                            {"type": "text", "text": OBSERVE_PROMPT},
                        ],
                    }],
                )
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
                return _extract_json(text)
            except Exception as e:  # noqa: BLE001 — layer boundary
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        raise VisionUnavailable(str(last_err)) from last_err
