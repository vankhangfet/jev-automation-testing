from __future__ import annotations

from jev_ui_agent.driver.selectors import find_element
from jev_ui_agent.models import Bounds, CheckResult, ScreenState, UIElement, Verdict


def functional_checks(state: ScreenState, policy: dict) -> list[CheckResult]:
    exps = [e for e in policy.get("functional_expectations", [])
            if e.get("checkpoint") == state.checkpoint]
    if not exps:
        return [CheckResult("functional/no-expectations", "functional", "rule",
                            Verdict.SKIPPED,
                            evidence={"note": "no expectations configured"})]
    out: list[CheckResult] = []
    for exp in exps:
        try:
            sel = exp["element"]
            check_id = f"functional/element:{sel}"
            el = find_element(state.elements, sel)
        except (KeyError, ValueError) as e:
            out.append(CheckResult("functional/element:invalid", "functional", "rule",
                                   Verdict.ERROR, error=str(e)))
            continue
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

    # 0) Màn không có element nào có label → SKIPPED (tránh PASS ảo trên màn trắng)
    if not labeled:
        for cid in ("layout/overlap", "layout/offscreen",
                    "layout/truncation_candidates"):
            results.append(CheckResult(cid, "layout", "rule", Verdict.SKIPPED,
                                       evidence={"note": "no labeled elements"}))
        return results

    # Chỉ element có rendered text: overlap/truncation trên content_desc-only là nhiễu
    texted = [e for e in state.elements if e.text]

    # 1) Overlap: cặp element có rendered text giao nhau quá ngưỡng
    min_ratio = float(cfg.get("overlap_min_ratio", 0.10))
    overlaps: list[tuple] = []
    for i, a in enumerate(texted):
        for j in range(i + 1, len(texted)):
            b = texted[j]
            inter = a.bounds.intersection(b.bounds)
            if inter is None:
                continue
            smaller = min(a.bounds.area, b.bounds.area) or 1
            ratio = inter.area / smaller
            if ratio >= min_ratio:
                overlaps.append((i, j, a, b, ratio))
    if overlaps:
        for i, j, a, b, ratio in overlaps:
            results.append(CheckResult(
                f"layout/overlap:{i}:{j}", "layout", "rule", Verdict.FAIL,
                evidence={"a": a.label, "b": b.label, "overlap_ratio": round(ratio, 3)}))
    else:
        results.append(CheckResult("layout/overlap", "layout", "rule", Verdict.PASS,
                                   evidence={"labeled_elements": len(labeled)}))

    # 2) Off-screen: chỉ FAIL khi element < 50% hiển thị trong viewport
    #    (row bị cắt nhẹ ở mép màn scroll là bình thường)
    tol = int(cfg.get("offscreen_tolerance_px", 2))
    vw, vh = state.viewport["width"], state.viewport["height"]
    offscreen: list[tuple[int, UIElement]] = []
    for i, e in enumerate(labeled):
        inter = e.bounds.intersection(Bounds(-tol, -tol, vw + tol, vh + tol))
        if inter is None:
            offscreen.append((i, e))
        elif inter.area / (e.bounds.area or 1) < 0.5:
            offscreen.append((i, e))
    if offscreen:
        for i, e in offscreen:
            results.append(CheckResult(
                f"layout/offscreen:{i}", "layout", "rule", Verdict.FAIL,
                evidence={"element": e.label,
                          "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                          "viewport": [vw, vh]}))
    else:
        results.append(CheckResult("layout/offscreen", "layout", "rule", Verdict.PASS))

    # 3) Truncation candidates: ước lượng chữ không đủ chỗ — visual check xác nhận sau
    char_w = vw * float(cfg.get("truncation_char_width_ratio", 0.025))
    candidates = [e for e in texted if len(e.text) * char_w > e.bounds.width]
    if candidates:
        results.append(CheckResult(
            "layout/truncation_candidates", "layout", "rule", Verdict.NEEDS_REVIEW,
            evidence={"candidates": [c.label for c in candidates],
                      "note": "cần xác nhận thị giác qua visual check"}))
    else:
        results.append(CheckResult("layout/truncation_candidates", "layout", "rule",
                                   Verdict.PASS))
    return results
