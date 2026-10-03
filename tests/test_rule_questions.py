from typesafe_sdk import Noul, Score

from jev_ui_agent.jev.rule_questions import build_questions
from jev_ui_agent.rules import DEFAULT_SCORE_CRITERIA

RULES = [
    {"id": "login_visible", "instruction": "A 'Sign in' button is visible", "type": "noul"},
    {"id": "polish", "instruction": "Rate the polish", "type": "score",
     "criteria": DEFAULT_SCORE_CRITERIA, "pass_at": 0.75},
    {"id": "polish_default", "instruction": "Rate it", "type": "score"},
]


def test_build_questions_types():
    q = build_questions(RULES)
    assert sorted(q) == ["login_visible", "polish", "polish_default"]
    assert isinstance(q["login_visible"], Noul)
    assert isinstance(q["polish"], Score)
    assert list(q["polish"].criteria) == DEFAULT_SCORE_CRITERIA
    assert list(q["polish_default"].criteria) == DEFAULT_SCORE_CRITERIA


def test_build_questions_content():
    q = build_questions(RULES)
    assert "Sign in" in q["login_visible"].instructions
    assert "near 0.5" in q["login_visible"].instructions
    assert "true" in q["login_visible"].criteria and "false" in q["login_visible"].criteria
    assert "Rate the polish" in q["polish"].instructions
