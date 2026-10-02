from types import SimpleNamespace

import pytest

import jev_ui_agent.jev.client as client_mod
from jev_ui_agent.jev.client import JevClient, JevError

_QK = {"is_urgent": object(), "frustration": object(), "topic": object()}


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
    seen = {}

    def sysone(**kw):
        seen.update(kw)
        return _fake_resp()

    fake = SimpleNamespace(system_one=sysone)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient()
    out = jc.judge("state", _QK)
    assert seen["model"] == "jev-latest"
    assert out["is_urgent"] == {"value": 1.0, "confidence": 1.0, "probabilities": {}}
    assert out["frustration"]["value"] == 2.0
    assert out["frustration"]["confidence"] == 0.9
    assert out["frustration"]["probabilities"] == {"0": 0.1, "1": 0.2, "2": 0.7}
    assert out["topic"]["value"] == "technical"
    assert out["topic"]["confidence"] == 0.78
    assert jc.usage == {"calls": 1, "input_tokens": 392, "output_tokens": 65}


def test_judge_derives_noul_confidence(monkeypatch):
    resp = SimpleNamespace(
        answers={
            "a": SimpleNamespace(noul=0.55, confidence=None, probabilities=None),
            "b": SimpleNamespace(noul=0.98, confidence=None, probabilities=None),
        },
        usage=None,
    )
    fake = SimpleNamespace(system_one=lambda **kw: resp)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient()
    out = jc.judge("state", {"a": object(), "b": object()})
    assert out["a"]["confidence"] == pytest.approx(0.1)
    assert out["b"]["confidence"] == pytest.approx(0.96)


def test_judge_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def boom(**kw):
        calls["n"] += 1
        raise RuntimeError("api down")

    fake = SimpleNamespace(system_one=boom)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient(retries=2)
    sleeps = []
    jc._sleep = sleeps.append  # bỏ delay khi test
    with pytest.raises(JevError) as ei:
        jc.judge("state", {"q": object()})
    assert calls["n"] == 3  # 1 lần đầu + 2 retry
    assert len(sleeps) == 2  # không sleep sau lần thử cuối
    assert isinstance(ei.value.__cause__, RuntimeError)


def test_judge_missing_answer_retries_then_raises(monkeypatch):
    calls = {"n": 0}
    resp = SimpleNamespace(
        answers={"present": SimpleNamespace(noul=1.0, confidence=None, probabilities=None)},
        usage=None,
    )

    def sysone(**kw):
        calls["n"] += 1
        return resp

    fake = SimpleNamespace(system_one=sysone)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient(retries=1)
    jc._sleep = lambda s: None
    with pytest.raises(JevError) as ei:
        jc.judge("state", {"present": object(), "missing": object()})
    assert calls["n"] == 2  # answer thiếu → ValueError → retry 1 lần rồi raise
    assert isinstance(ei.value.__cause__, ValueError)


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
    out = jc.judge("state", _QK)
    assert out["topic"]["value"] == "technical"
