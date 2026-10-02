from __future__ import annotations

from jev_ui_agent.driver.selectors import find_element
from jev_ui_agent.models import CheckResult, ScreenState, Verdict


def functional_checks(state: ScreenState, policy: dict) -> list[CheckResult]:
    exps = [e for e in policy.get("functional_expectations", [])
            if e.get("checkpoint") == state.checkpoint]
    if not exps:
        return [CheckResult("functional/no-expectations", "functional", "rule",
                            Verdict.SKIPPED,
                            evidence={"note": "no expectations configured"})]
    out: list[CheckResult] = []
    for exp in exps:
        sel = exp["element"]
        check_id = f"functional/element:{sel}"
        el = find_element(state.elements, sel)
        if el is None:
            out.append(CheckResult(check_id, "functional", "rule", Verdict.FAIL,
                                   evidence={"missing": sel}))
            continue
        expect_text = exp.get("expect_text")
        if expect_text is not None and el.label.strip() != str(expect_text).strip():
            out.append(CheckResult(check_id, "functional", "rule", Verdict.FAIL,
                                   evidence={"element": sel, "actual": el.label,
                                             "expected": expect_text}))
        else:
            out.append(CheckResult(check_id, "functional", "rule", Verdict.PASS,
                                   evidence={"element": sel, "label": el.label}))
    return out


def layout_checks(state: ScreenState, policy: dict) -> list[CheckResult]:
    cfg = policy.get("layout", {})
    labeled = [e for e in state.elements if e.label]
    results: list[CheckResult] = []

    # 1) Overlap: cặp element có text giao nhau quá ngưỡng
    min_ratio = float(cfg.get("overlap_min_ratio", 0.10))
    overlaps: list[tuple] = []
    for i, a in enumerate(labeled):
        for b in labeled[i + 1:]:
            inter = a.bounds.intersection(b.bounds)
            if inter is None:
                continue
            smaller = min(a.bounds.area, b.bounds.area) or 1
            ratio = inter.area / smaller
            if ratio >= min_ratio:
                overlaps.append((a, b, ratio))
    if overlaps:
        for a, b, ratio in overlaps:
            results.append(CheckResult(
                f"layout/overlap:{a.label}|{b.label}", "layout", "rule", Verdict.FAIL,
                evidence={"a": a.label, "b": b.label, "overlap_ratio": round(ratio, 3)}))
    else:
        results.append(CheckResult("layout/overlap", "layout", "rule", Verdict.PASS,
                                   evidence={"labeled_elements": len(labeled)}))

    # 2) Off-screen: tràn khỏi viewport quá tolerance
    tol = int(cfg.get("offscreen_tolerance_px", 2))
    vw, vh = state.viewport["width"], state.viewport["height"]
    offscreen = [e for e in labeled
                 if e.bounds.x1 < -tol or e.bounds.y1 < -tol
                 or e.bounds.x2 > vw + tol or e.bounds.y2 > vh + tol]
    if offscreen:
        for e in offscreen:
            results.append(CheckResult(
                f"layout/offscreen:{e.label}", "layout", "rule", Verdict.FAIL,
                evidence={"element": e.label,
                          "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                          "viewport": [vw, vh]}))
    else:
        results.append(CheckResult("layout/offscreen", "layout", "rule", Verdict.PASS))

    # 3) Truncation candidates: ước lượng chữ không đủ chỗ — visual check xác nhận sau
    char_w = vw * float(cfg.get("truncation_char_width_ratio", 0.025))
    candidates = [e for e in labeled if len(e.label) * char_w > e.bounds.width]
    if candidates:
        results.append(CheckResult(
            "layout/truncation_candidates", "layout", "rule", Verdict.NEEDS_REVIEW,
            evidence={"candidates": [c.label for c in candidates],
                      "note": "cần xác nhận thị giác qua visual check"}))
    else:
        results.append(CheckResult("layout/truncation_candidates", "layout", "rule",
                                   Verdict.PASS))
    return results
