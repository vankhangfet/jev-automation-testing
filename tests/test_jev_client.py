from types import SimpleNamespace

import pytest

import jev_ui_agent.jev.client as client_mod
from jev_ui_agent.jev.client import JevClient, JevError


def _fake_resp():
    return SimpleNamespace(
        answers={
            "is_urgent": SimpleNamespace(noul=1.0, confidence=None, probabilities=None),
            "frustration": SimpleNamespace(score=2.0, confidence=0.9,
                                           probabilities={0: 0.1, 1: 0.2, 2: 0.7}),
            "topic": SimpleNamespace(choice="technical", confidence=0.78,
                                     probabilities={"technical": 0.85, "billing": 0.15}),
        },
        usage=SimpleNamespace(input_tokens=392, output_tokens=65),
    )


def test_judge_parses_answers(monkeypatch):
    fake = SimpleNamespace(system_one=lambda **kw: _fake_resp())
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient()
    out = jc.judge("state", {"q": object()})
    assert out["is_urgent"] == {"value": 1.0, "confidence": None, "probabilities": {}}
    assert out["frustration"]["value"] == 2.0
    assert out["frustration"]["probabilities"] == {"0": 0.1, "1": 0.2, "2": 0.7}
    assert out["topic"]["value"] == "technical"
    assert jc.usage == {"calls": 1, "input_tokens": 392, "output_tokens": 65}


def test_judge_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def boom(**kw):
        calls["n"] += 1
        raise RuntimeError("api down")

    fake = SimpleNamespace(system_one=boom)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient(retries=2)
    jc._sleep = lambda s: None  # bỏ delay khi test
    with pytest.raises(JevError):
        jc.judge("state", {"q": object()})
    assert calls["n"] == 3  # 1 lần đầu + 2 retry


def test_judge_model_kwarg_fallback(monkeypatch):
    seen = {}

    def sysone(**kw):
        seen.update(kw)
        if kw.get("model"):
            raise TypeError("unexpected keyword 'model'")
        return _fake_resp()

    fake = SimpleNamespace(system_one=sysone)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient()
    jc._sleep = lambda s: None
    out = jc.judge("state", {"q": object()})
    assert out["topic"]["value"] == "technical"
