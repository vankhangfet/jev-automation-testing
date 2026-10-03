from pathlib import Path

import pytest

from jev_ui_agent.rules import DEFAULT_SCORE_CRITERIA, RulesError, load_rules

VALID = """
name: demo_rules
rules:
  - id: login_button_present
    instruction: "A login button labeled 'Sign in' is visible"
  - id: no_error_banner
    instruction: "No red error banner is visible"
    type: noul
  - id: visual_polish
    instruction: "Rate the visual polish"
    type: score
    pass_at: 0.8
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid(tmp_path):
    r = load_rules(_write(tmp_path, VALID))
    assert r["name"] == "demo_rules"
    assert len(r["rules"]) == 3
    assert r["rules"][0] == {"id": "login_button_present",
                             "instruction": "A login button labeled 'Sign in' is visible",
                             "type": "noul"}
    assert r["rules"][2]["pass_at"] == 0.8
    assert "criteria" not in r["rules"][0]


def test_score_default_criteria(tmp_path):
    r = load_rules(_write(tmp_path, "name: x\nrules:\n  - id: s1\n    instruction: Rate it\n    type: score\n"))
    assert r["rules"][0]["criteria"] == DEFAULT_SCORE_CRITERIA
    assert len(DEFAULT_SCORE_CRITERIA) == 5


@pytest.mark.parametrize("bad", [
    "rules:\n  - id: x\n    instruction: hi\n",        # thiếu name
    "name: x\nrules: []\n",                            # rules rỗng
    "name: x\nrules:\n  - id: BAD_ID\n    instruction: hi\n",   # id không slug
    "name: x\nrules:\n  - id: a\n    instruction: hi\n  - id: a\n    instruction: hi2\n",  # trùng id
    "name: x\nrules:\n  - id: a\n",                    # thiếu instruction
    "name: x\nrules:\n  - id: a\n    instruction: hi\n    type: dance\n",  # type lạ
    "name: x\nrules:\n  - id: a\n    instruction: hi\n    type: score\n    criteria: [a, b]\n",  # criteria != 5
    "name: x\nrules:\n  - id: a\n    instruction: hi\n    type: score\n    pass_at: 1.5\n",  # pass_at ngoài [0,1]
])
def test_invalid_rules(tmp_path, bad):
    with pytest.raises(RulesError):
        load_rules(_write(tmp_path, bad))


def test_missing_file():
    with pytest.raises(RulesError):
        load_rules(Path("nope.yaml"))
