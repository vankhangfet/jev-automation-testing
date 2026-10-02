from __future__ import annotations

from jev_ui_agent.models import CheckResult, Verdict

# Giá trị chuẩn hóa khi tính điểm (error/skipped bị loại khỏi phép tính)
VERDICT_VALUE = {Verdict.PASS: 1.0, Verdict.FAIL: 0.0, Verdict.NEEDS_REVIEW: 0.5}


def score_checkpoint(results: list[CheckResult], weights: dict[str, float]) -> float | None:
    """Điểm tổng checkpoint = trung bình trọng số theo nhóm check (pattern composite scoring)."""
    acc, total = 0.0, 0.0
    for group, weight in weights.items():
        values = [VERDICT_VALUE[r.verdict] for r in results
                  if r.group == group and r.verdict in VERDICT_VALUE]
        if not values:
            continue
        acc += weight * (sum(values) / len(values))
        total += weight
    return round(acc / total, 4) if total > 0 else None


def apply_confidence_gate(result: CheckResult, gate: float) -> CheckResult:
    """Confidence dưới ngưỡng → needs_human_review, giữ verdict gốc trong evidence."""
    if result.confidence is not None and result.confidence < gate:
        result.evidence["pre_gate_verdict"] = result.verdict.value
        result.verdict = Verdict.NEEDS_REVIEW
    return result
