from __future__ import annotations

from typesafe_sdk import Noul, Score

from jev_ui_agent.rules import DEFAULT_SCORE_CRITERIA


def build_questions(rules: list[dict]) -> dict:
    """Sinh câu hỏi JEV từ rules do người dùng định nghĩa (mỗi rule 1 câu hỏi)."""
    q: dict = {}
    for rule in rules:
        instruction = rule["instruction"]
        if rule["type"] == "noul":
            q[rule["id"]] = Noul(
                instructions=(
                    "Using the screen_observation, is this requirement satisfied? "
                    f'Requirement: "{instruction}" '
                    "If the observation lacks enough detail to decide, answer near 0.5 (uncertain)."
                ),
                criteria={
                    "true": "The observation clearly shows the requirement is satisfied.",
                    "false": "The observation clearly shows the requirement is violated "
                             "or the expected content is absent.",
                },
            )
        else:
            q[rule["id"]] = Score(
                instructions=f'Rate the screen against this requirement: "{instruction}"',
                criteria=rule.get("criteria") or DEFAULT_SCORE_CRITERIA,
            )
    return q
