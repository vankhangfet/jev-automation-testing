from __future__ import annotations

from jev_ui_agent.models import CheckResult, Verdict

# Giá trị chuẩn hóa khi tính điểm (error/skipped bị loại khỏi phép tính)
VERDICT_VALUE = {Verdict.PASS: 1.0, Verdict.FAIL: 0.0, Verdict.NEEDS_REVIEW: 0.5}

# Các verdict định lượng đủ điều kiện bị confidence gate
_GATEABLE_VERDICTS = (Verdict.PASS, Verdict.FAIL, Verdict.NEEDS_REVIEW)


def score_checkpoint(results: list[CheckResult], weights: dict[str, float]) -> float | None:
    """Điểm tổng checkpoint = trung bình trọng số theo nhóm check (pattern composite scoring).

    Nhóm có kết quả nhưng không nằm trong ``weights`` bị bỏ qua (không tính điểm).
    Tổng weights không cần bằng 1 — số điểm tự renormalize theo tổng trọng số
    của các group thực sự có kết quả chấm được.
    """
    acc, total = 0.0, 0.0
    for group, weight in weights.items():
        if weight < 0:
            raise ValueError(f"Trọng số âm cho group {group!r}: {weight}")
        values = [VERDICT_VALUE[r.verdict] for r in results
                  if r.group == group and r.verdict in VERDICT_VALUE]
        if not values:
            continue
        acc += weight * (sum(values) / len(values))
        total += weight
    return round(acc / total, 4) if total > 0 else None


def apply_confidence_gate(result: CheckResult, gate: float) -> CheckResult:
    """Confidence dưới ngưỡng → needs_human_review, giữ verdict gốc trong evidence.

    Mutate in-place và trả về cùng object. Idempotent: result đã gate
    (có ``pre_gate_verdict`` trong evidence) không bị gate lần nữa. Chỉ gate
    các verdict định lượng (pass/fail/needs_review) — ERROR/SKIPPED giữ nguyên.
    """
    if "pre_gate_verdict" in result.evidence:
        return result
    if result.verdict not in _GATEABLE_VERDICTS:
        return result
    if result.confidence is not None and result.confidence < gate:
        result.evidence["pre_gate_verdict"] = result.verdict.value
        result.verdict = Verdict.NEEDS_REVIEW
    return result
