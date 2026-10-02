from __future__ import annotations

from jev_ui_agent.checks.composite import apply_confidence_gate
from jev_ui_agent.checks.rules import functional_checks, layout_checks
from jev_ui_agent.jev.client import JevClient, JevError
from jev_ui_agent.jev.questions import core_questions, visual_questions
from jev_ui_agent.models import CheckResult, ScreenState, Verdict
from jev_ui_agent.vision.claude_bridge import VisionBridge, VisionUnavailable

_JEV_GROUP_BY_KEY = {
    "screen_class": "error_anomaly",
    "has_raw_i18n_key": "content_quality",
    "has_dev_text": "content_quality",
    "typo_severity": "content_quality",
}
_JEV_CHECK_ID = {
    "screen_class": "error_anomaly/screen_class",
    "has_raw_i18n_key": "content_quality/raw_i18n_key",
    "has_dev_text": "content_quality/dev_text",
    "typo_severity": "content_quality/typo",
}
_VISUAL_IDS = ["visual/blank", "visual/broken_images", "visual/text_cut"]


def _state_payload(state: ScreenState) -> dict:
    return {
        "checkpoint": state.checkpoint,
        "platform": state.platform,
        "app": state.app,
        "viewport": state.viewport,
        "elements": [
            {
                "id": e.id, "type": e.type, "label": e.label, "text": e.text,
                "content_desc": e.content_desc,
                "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                "clickable": e.clickable,
            }
            for e in state.elements
        ],
    }


def _noul_result(check_id: str, group: str, path: str, ans: dict, gate: float,
                 threshold: float = 0.5) -> CheckResult:
    bad = (ans.get("value") or 0.0) >= threshold
    r = CheckResult(check_id, group, path, Verdict.FAIL if bad else Verdict.PASS,
                    confidence=ans.get("confidence"), evidence={"noul": ans.get("value")})
    return apply_confidence_gate(r, gate)


def _jev_checks(state: ScreenState, policy: dict, jev: JevClient) -> list[CheckResult]:
    gate = float(policy.get("confidence_gate", 0.75))
    toggles = policy.get("check_toggles", {})
    questions = core_questions(content_quality=toggles.get("content_quality", True),
                               error_anomaly=toggles.get("error_anomaly", True))
    if not questions:
        return []
    try:
        answers = jev.judge(_state_payload(state), questions)
    except JevError as e:
        return [CheckResult(_JEV_CHECK_ID[k], _JEV_GROUP_BY_KEY[k], "jev", Verdict.ERROR,
                            error=str(e))
                for k in questions if k in _JEV_CHECK_ID]

    out: list[CheckResult] = []
    if "screen_class" in answers:
        a = answers["screen_class"]
        verdict = Verdict.PASS if a["value"] == "normal" else Verdict.FAIL
        r = CheckResult(_JEV_CHECK_ID["screen_class"], "error_anomaly", "jev", verdict,
                        score=a["probabilities"].get("normal"),
                        confidence=a["confidence"], probabilities=a["probabilities"],
                        evidence={"classified": a["value"]})
        out.append(apply_confidence_gate(r, gate))
    if "has_raw_i18n_key" in answers:
        out.append(_noul_result(_JEV_CHECK_ID["has_raw_i18n_key"], "content_quality", "jev",
                                answers["has_raw_i18n_key"], gate))
    if "has_dev_text" in answers:
        out.append(_noul_result(_JEV_CHECK_ID["has_dev_text"], "content_quality", "jev",
                                answers["has_dev_text"], gate))
    if "typo_severity" in answers:
        a = answers["typo_severity"]
        norm = (a["value"] or 0.0) / 4.0
        threshold = float(policy.get("content_quality", {}).get("typo_pass_score", 0.75))
        r = CheckResult(_JEV_CHECK_ID["typo_severity"], "content_quality", "jev",
                        Verdict.PASS if norm >= threshold else Verdict.FAIL,
                        score=norm, confidence=a["confidence"],
                        evidence={"raw_score": a["value"], "threshold": threshold})
        out.append(apply_confidence_gate(r, gate))
    return out


def _visual_checks(state: ScreenState, policy: dict, jev: JevClient,
                   vision: VisionBridge) -> list[CheckResult]:
    gate = float(policy.get("confidence_gate", 0.75))
    try:
        observation = vision.observe(state.screenshot)
    except VisionUnavailable as e:
        return [CheckResult(i, "visual", "vision+jev", Verdict.SKIPPED, error=str(e))
                for i in _VISUAL_IDS]
    payload = {"screen": _state_payload(state), "visual_observation": observation}
    try:
        answers = jev.judge(payload, visual_questions())
    except JevError as e:
        return [CheckResult(i, "visual", "vision+jev", Verdict.ERROR, error=str(e))
                for i in _VISUAL_IDS]
    return [
        _noul_result("visual/blank", "visual", "vision+jev", answers["visual_blank"], gate),
        _noul_result("visual/broken_images", "visual", "vision+jev",
                     answers["visual_broken"], gate),
        _noul_result("visual/text_cut", "visual", "vision+jev",
                     answers["visual_text_cut"], gate),
    ]


def run_checks(state: ScreenState, policy: dict, jev: JevClient | None,
               vision: VisionBridge | None) -> list[CheckResult]:
    """Routing theo nguyên tắc: rule rẻ nhất → JEV trực tiếp → vision+JEV."""
    toggles = policy.get("check_toggles", {})
    results: list[CheckResult] = []

    if toggles.get("functional", True):
        results += functional_checks(state, policy)
    if toggles.get("layout", True):
        results += layout_checks(state, policy)

    jev_groups = [g for g in ("content_quality", "error_anomaly")
                  if toggles.get(g, True)]
    if jev_groups:
        if jev is None:
            results += [CheckResult(_JEV_CHECK_ID[k], _JEV_GROUP_BY_KEY[k], "jev",
                                    Verdict.SKIPPED, error="jev client unavailable")
                        for k in _JEV_CHECK_ID
                        if _JEV_GROUP_BY_KEY[k] in jev_groups]
        else:
            results += _jev_checks(state, policy, jev)

    if toggles.get("visual", True):
        if jev is None or vision is None:
            results += [CheckResult(i, "visual", "vision+jev", Verdict.SKIPPED,
                                    error="jev/vision client unavailable")
                        for i in _VISUAL_IDS]
        else:
            results += _visual_checks(state, policy, jev, vision)
    return results
