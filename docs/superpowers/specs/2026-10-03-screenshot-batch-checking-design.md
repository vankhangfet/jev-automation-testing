# Screenshot Batch Checking — Design Doc (Phase 2a)

- **Ngày:** 2026-10-03
- **Trạng thái:** Approved (user chọn "thiết kế + triển khai luôn")
- **Branch:** `feat/screenshot-batch-mode`
- **Spec gốc:** `2026-10-02-jev-ui-checking-agent-design.md` (Phase 1)

## 1. Mục tiêu

Cho phép kiểm tra **folder screenshot tĩnh** (không cần thiết bị/driver/flow) theo **bộ rule do người dùng định nghĩa bằng ngôn ngữ tự nhiên (prompt-like)**:

```
folder ảnh (≥ 2.000 ảnh)  +  rules.yaml  →  verdict pass/fail/needs_review từng ảnh × từng rule  →  report HTML/JSON
```

### Mục tiêu cụ thể

- Rule 2 kiểu: `noul` (pass/fail) và `score` (rubric 0-4 + ngưỡng pass).
- Chi phí: **1 vision call + 1 JEV call / ảnh** bất kể số rule (fan-out JEV).
- Scale ≥ 2.000 ảnh: dedup theo hash, song song (`--workers`), `--limit`, **resume** sau gián đoạn, retry ảnh lỗi khi resume.
- Reuse tối đa: CheckResult/Verdict/confidence gate/composite/report renderers/CLI pattern.

### Non-goals (v1)

- So sánh 2 ảnh với nhau (baseline diff).
- Rule gắn vùng toạ độ (region-of-interest) — chỉ rule mô tả bằng lời.
- OCR riêng — vision model tự đọc text trong ảnh.
- UI web/dashboard — vẫn là CLI + HTML tĩnh.

## 2. Rules file schema (`*.yaml`)

```yaml
name: checkout_screen_rules      # required, string
description: Optional context    # optional
rules:                           # required, non-empty
  - id: login_button_present     # required, unique, slug ^[a-z0-9][a-z0-9_.-]*$
    instruction: "A login button labeled 'Sign in' is visible and not overlapped"
                                 # required, English (JEV English-primary)
    type: noul                   # noul | score, default noul
  - id: visual_polish
    instruction: "Rate the overall visual polish and consistency of this screen"
    type: score
    criteria:                    # optional, score only — đúng 5 mức
      - "Broken layout, misaligned or overlapping elements"
      - "Multiple prominent visual defects"
      - "A few minor inconsistencies"
      - "Mostly clean with tiny imperfections"
      - "Fully polished and consistent"
    pass_at: 0.75                # optional, score only, default 0.75 (normalized 0-1)
```

Validation (giống flows.py): sai type/id trùng/thiếu instruction/criteria ≠ 5 mức → `RulesError(ValueError)`.

## 3. Luồng xử lý

```
[1] scan: quét --dir (*.png/jpg/jpeg, --recursive) → sort theo tên
[2] dedup: sha256/ảnh — ảnh trùng reuse kết quả ảnh đầu (evidence ghi "duplicate of <name>")
[3] nếu --resume <run_dir>: nạp checkpoint.jsonl → bỏ qua ảnh done, RETRY ảnh error
[4] mỗi ảnh (ThreadPoolExecutor, --workers, default 4):
      a. VisionBridge.observe_detailed(path) → observation JSON toàn diện (1 call)
      b. payload = {"image": <tên file>, "screen_observation": observation}
      c. questions = build_questions(rules) — MỌI rule 1 question → 1 system_one call
      d. map verdict: noul >= 0.5 → PASS (câu hỏi là "requirement satisfied?" — value cao = thỏa);
         score: v/4 >= pass_at; confidence gate (0.75)
      e. append 1 dòng checkpoint.jsonl (kể cả error) — flush ngay
[5] report: summary-first HTML + JSON đầy đủ; cost log
```

### Observation schema (vision prompt v2 — `observe_detailed`)

```json
{
  "screen_type": "best-guess screen name",
  "layout": [{"region": "top bar", "contents": "..."}],
  "texts": ["exact visible texts, cap ~30"],
  "images_icons": "imagery/icons present",
  "colors_style": "dominant colors, light/dark, notable styling",
  "error_indicators": "error/crash/empty indicators or 'none'",
  "notable": "clipping/overlap/placeholder/garbled text or 'none'"
}
```

Yêu cầu prompt: terse, factual, no speculation — giữ nguyên tinh thần prompt v1. Keys thiếu → fill `"none"`/`[]` (normalize như vision bridge hiện tại). **Nhận diện định dạng ảnh** PNG/JPG bằng magic bytes (`\x89PNG` / `\xff\xd8`) → `media_type` đúng.

### Question building (factory — thay cho constants)

- `noul`: `Noul(instructions=f"Using the screen_observation, is this requirement satisfied? Requirement: \"{instruction}\" If the observation lacks enough detail to decide, answer near 0.5 (uncertain).", criteria={"true": "...clearly satisfied...", "false": "...clearly violated or the expected content is absent..."})`
- `score`: `Score(instructions=f"Rate the screen against this requirement: \"{instruction}\"", criteria=<5 mức từ rule hoặc default rubric>)`
- Default rubric khi không có criteria: 5 mức generic (`"Completely fails the requirement"` → `"Fully satisfies the requirement"`).

### Verdict & điểm ảnh

- Mỗi rule → `CheckResult(check_id=f"rule/{id}", group="rules", path="vision+jev")`.
- Gate confidence < 0.75 → `NEEDS_REVIEW` (reuse; noul confidence được derive sẵn ở JevClient).
- Ảnh = `CheckpointReport(checkpoint=<tên file>, screen_score=<mean verdict values>, ...)`.
- **Ảnh "pass" ở summary** = không có rule nào FAIL (NEEDS_REVIEW không làm fail).

## 4. Thread-safety

Vision + JEV gọi từ nhiều worker threads:
- `JevClient.usage` và `VisionBridge.calls` hiện dùng `+=` không atomic → thêm `threading.Lock` quanh các mutation đó (thay đổi ~4 dòng, không đổi interface).

## 5. Resume / checkpoint

- Run dir: `reports/check-<ts>/` chứa `checkpoint.jsonl`, `report.json`, `report.html`.
- Mỗi dòng: `{"image": path, "hash": sha256, "status": "done|error", "results": [...], "screen_score": x, "error": str}`.
- `--resume reports/check-X`: đọc jsonl → skip ảnh `done` cùng hash; ảnh `error` được chạy lại; append tiếp vào checkpoint đó; report cuối tổng hợp toàn bộ dòng.
- Ảnh bị xoá/không còn trong folder khi resume → giữ kết quả cũ trong report (ghi nhận `missing`).

## 6. CLI

```
uv run python -m jev_ui_agent check-screenshots \
  --dir ./screens --rules rules.yaml \
  [--workers 4] [--limit N] [--recursive] \
  [--resume reports/check-...] [--out reports] [--policy config/policy.yaml]
```

Exit code: `1` nếu ≥ 1 ảnh có rule FAIL hoặc error; `0` nếu tất cả pass/review.

## 7. Report

- **HTML summary-first**: header stats (tổng ảnh / pass / fail / needs review / errors / cost); bảng "Failing images" (ảnh fail trước, kèm rule vi phạm); mỗi ảnh 1 card thu gọn (`<details>`) với screenshot (đường dẫn gốc, forward slash) + bảng rules.
- JSON: đầy đủ (machine-readable, đúng schema RunReport hiện có — reuse renderers, chỉ thêm section summary).
- Cost: vision calls + JEV tokens đúng thực tế.

## 8. Ước tính chi phí (2.000 ảnh, ~10 rules)

- Vision Haiku: ~2.000 calls ≈ $6-15 (tùy độ phân giải); JEV: 2.000 calls fan-out (rẻ, ~100ms/call).
- Wall-clock với 4 workers: ~20-40 phút. Hiển thị real numbers trong report.

## 9. Testing strategy (TDD, mọi API boundary mock)

- Rules loader: valid/invalid cases.
- observe_detailed: prompt chứa keys; sniff png/jpg; non-dict normalize; thread-safety lock (calls counter).
- Question builder: noul/score/default rubric/pass_at.
- Batch core (mock clients): dedup reuse, verdict mapping, gate, checkpoint append/skip/error-retry, workers>1 không chết, limit.
- CLI: exit codes, resume flag.
- Report: summary markers, fail-first ordering.

## 10. Success criteria

1. Folder 2.000+ ảnh: resume hoạt động sau kill giữa chừng (không re-run ảnh done).
2. Dedup: ảnh trùng không tốn call thứ hai.
3. Report hiển thị đúng pass/fail/review từng ảnh × rule + tổng chi phí.
4. Toàn bộ test offline pass; không thay đổi hành vi Phase 1 (97 tests cũ xanh nguyên vẹn).
