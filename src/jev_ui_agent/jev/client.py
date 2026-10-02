from __future__ import annotations

import time
from typing import Any

from typesafe_sdk import TypeSafeClient

DEFAULT_MODEL = "jev-latest"


class JevError(RuntimeError):
    pass


class JevClient:
    """Wrap TypeSafeClient: retry, parse answers về dict phẳng, tích lũy usage."""

    def __init__(self, model: str = DEFAULT_MODEL, retries: int = 2, backoff: float = 0.5):
        self._client = TypeSafeClient()  # đọc TYPESAFE_API_KEY từ env
        self.model = model
        self.retries = retries
        self._backoff = backoff
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def judge(self, state: Any, questions: dict) -> dict[str, dict]:
        """Trả {key: {"value": float|str, "confidence": float|None, "probabilities": dict}}."""
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                try:
                    resp = self._client.system_one(state=state, questions=questions,
                                                   model=self.model)
                except TypeError:
                    # SDK cũ không nhận kwarg model
                    resp = self._client.system_one(state=state, questions=questions)
                self.usage["calls"] += 1
                self._absorb_usage(resp)
                return self._parse_answers(resp)
            except Exception as e:  # noqa: BLE001 — layer boundary
                last_err = e
                self._sleep(self._backoff * (attempt + 1))
        raise JevError(str(last_err))

    def _absorb_usage(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return

        def g(k: str) -> int:
            v = getattr(u, k, None)
            if v is None and isinstance(u, dict):
                v = u.get(k, 0)
            return int(v or 0)

        self.usage["input_tokens"] += g("input_tokens")
        self.usage["output_tokens"] += g("output_tokens")

    def _parse_answers(self, resp: Any) -> dict[str, dict]:
        out: dict[str, dict] = {}
        answers = getattr(resp, "answers", None) or {}
        try:
            items = answers.items()
        except AttributeError:
            items = [(a.get("key"), a) for a in answers if isinstance(a, dict)]
        for key, ans in items:
            entry: dict = {"value": None, "confidence": None, "probabilities": {}}
            for attr in ("noul", "score", "choice"):
                if getattr(ans, attr, None) is not None:
                    entry["value"] = getattr(ans, attr)
                    break
            entry["confidence"] = getattr(ans, "confidence", None)
            probs = getattr(ans, "probabilities", None)
            if isinstance(probs, dict):
                entry["probabilities"] = {str(k): float(v) for k, v in probs.items()}
            out[str(key)] = entry
        return out
