# JEV Mobile UI Checking Agent — Design Doc

- **Ngày:** 2026-10-02
- **Trạng thái:** Approved (brainstorming xong)
- **Project:** `jev-agent-ui-checking`

## 1. Mục tiêu

Xây dựng một agent kiểm tra UI cho mobile app, dùng **JEV (TypeSafe, `jev-latest`)** làm judgment engine:

```
Mobile App → UI Automation → Screenshot/UI Tree → JEV Agent → Visual/Rule Analysis → Report
```

Thử nghiệm để trả lời câu hỏi cốt lõi: *JEV — một judgment model có cấu trúc, nhanh, rẻ — có đủ "common sense" để thay thế/vượt mặt rule-checking cứng nhắc và LLM prompt-parse truyền thống trong UI testing không?*

### Mục tiêu cụ thể (Phase 1)

- Chạy được flow test 3–5 checkpoint trên app mẫu Android emulator, repeatable 100%.
- Đủ 5 nhóm check: functional, layout heuristics, visual, error/anomaly, content quality.
- Report HTML + JSON kèm confidence, probabilities, chi phí mỗi run.
- Đo được chi phí JEV/vision mỗi run và độ chính xác verdict.

### Non-goals (Phase 1)

- So sánh với Figma design (Phase 2/3).
- Chạy iOS thật trên máy Windows (cần Mac) — kiến trúc hỗ trợ sẵn, thực thi để Phase 2.
- Tích hợp CI/CD, chạy song song nhiều device.
- Agent exploratory tự khám phá app (Phase 3).

## 2. Ràng buộc nền tảng then chốt (từ docs JEV)

1. **JEV chỉ nhận TEXT** — ảnh/screenshot chưa hỗ trợ. Screenshot muốn được "phán xét" phải qua vision model trích observation text trước.
2. **Triết lý JEV: code in control** — orchestration là code deterministic; model chỉ trả lời các phán đoán nguyên tử (atomic judgments). Không agent while-loop.
3. Ba primitive: `choice` (chọn 1 trong N + probabilities + confidence), `score` (chấm theo rubric + confidence), `noul` (đúng/sai 0–1).
4. Nhiều câu hỏi độc lập **gộp 1 call** (fan-out, ~100ms).
5. Confidence được calibrate (RLCD) — dùng để gate "needs human review".
6. Tiếng Anh là ngôn ngữ chính của JEV; ngôn ngữ khác độ chính xác thấp hơn → app mẫu tiếng Anh.
7. Composite scoring: chấm từng chiều riêng rồi cộng trọng số trong code (pattern chính thức).

## 3. Lựa chọn kiến trúc (đã chốt)

**Phương án A: Pipeline deterministic + JEV judgment engine** (so với B: Maestro offline analyzer — trích UI tree lóng tay, không judgment giữa flow; C: LLM agent tự lái — không deterministic, mâu thuẫn triết lý JEV, để Phase 3 exploratory).

Nguyên tắc routing: **mỗi check đi con đường rẻ nhất trả lời được**

```
Rule thuần (bounds, tồn tại element)   →  0 đồng AI
     ↓ không đủ
JEV trực tiếp trên ScreenState (text)  →  1 call fan-out nhiều câu hỏi
     ↓ cần thông tin thị giác
Vision bridge (Claude Haiku → JSON)    →  observation text → JEV judge
```

## 4. Cấu trúc project

```
jev-agent-ui-checking/
├── pyproject.toml              # Python 3.11+, uv
├── config/
│   ├── devices.yaml            # Appium capabilities Android/iOS
│   └── policy.yaml             # trọng số composite, ngưỡng confidence, bật/tắt nhóm check
├── flows/                      # kịch bản YAML
├── src/jev_ui_agent/
│   ├── driver/                 # base.py, android.py, ios.py
│   ├── extract/                # XML → ScreenState
│   ├── checks/                 # catalog 5 nhóm + router
│   ├── jev/                    # client.py, questions.py (question bank 1 file)
│   ├── vision/                 # claude_bridge.py
│   ├── report/                 # html.py, json_report.py
│   └── pipeline.py             # orchestrator
├── tests/
│   ├── fixtures/               # XML UI tree mẫu, screenshot mẫu, mock JEV responses
│   └── ...
└── reports/                    # artifacts + report theo run
```

## 5. Thành phần

### 5.1 Driver layer (Appium)

- `BaseDriver` interface: `connect()`, `tap(target)`, `input(target, value)`, `swipe(...)`, `capture(checkpoint_name) -> StepArtifact`, `quit()`.
- Android: Appium **UiAutomator2**; iOS: **XCUITest**. Pipeline không biết khác biệt nền tảng.
- Target selector dạng chuỗi chuẩn hóa: `"res-id:login_btn"`, `"acc-id:Sign in"`, `"text:Sign in"`, `"xpath:..."`.
- Flow YAML khai báo action tuần tự + **checkpoint** (nơi capture artifacts):

```yaml
name: login_smoke
app: now_in_android
steps:
  - action: launch
  - checkpoint: home
  - action: tap
    target: "acc-id:Sign in"
  - checkpoint: login_form
  - action: input
    target: "acc-id:Email field"
    value: "demo@example.com"
  - action: tap
    target: "acc-id:Submit"
  - checkpoint: after_submit
```

### 5.2 Extractor

- Parse `page_source` XML (Android) / XCUIElement tree (iOS) → `ScreenState` JSON chuẩn hóa (cùng schema 2 nền tảng).
- Lọc element vô hình/không ý nghĩa; giới hạn số element (anti context-rot).
- `StepArtifact = {screenshot_png, source_xml, screen_name, timestamp, activity}`.

```json
{
  "run_id": "run-20261002-1",
  "checkpoint": "login_form",
  "platform": "android",
  "app": "com.google.samples.apps.nowinandroid",
  "viewport": {"width": 1080, "height": 2400},
  "elements": [
    {"id": "login_btn", "type": "button", "text": "Sign in",
     "bounds": [10, 800, 350, 848], "clickable": true}
  ],
  "screenshot": "reports/run-20261002-1/artifacts/login_form.png"
}
```

### 5.3 Check engine + Router

| Nhóm | Path | Chi tiết |
|---|---|---|
| Functional | code + JEV (semantic) | Code: element tồn tại, text khớp, clickable. JEV: "text này có phải placeholder/lorem ipsum?", "label này có mô tả đúng chức năng button?" |
| Layout heuristics | code + JEV (confirm) | Code: overlap bounds, off-screen, text-dài-trong-bounds-hẹp. JEV noul: "overlap này có thực sự che khuất nội dung không?" (phân biệt overlap tiền định như badge trên avatar) |
| Content quality | JEV trực tiếp | noul: i18n key thô, text dev (TODO/FIXME/debug), placeholder; score: mức độ typo |
| Error/anomaly | JEV trực tiếp | choice: phân loại màn `normal/error_screen/crash_dialog/empty_state/loading_stuck` |
| Visual | vision → JEV | Claude Haiku trích observation JSON (tỉ lệ vùng trống, ảnh broken, render lỗi) → JEV noul/score phán |

Router quyết định path theo nhóm check + config policy. Toàn bộ câu hỏi JEV của 1 checkpoint gộp **1 call** `client.system_one(state=screen_state, questions=...)`.

### 5.4 Judgment layer

- `jev/questions.py`: question bank là **constants trong 1 file** (best practice TypeSafe — người review chỉ đọc 1 file).
- `jev/client.py`: wrap `TypeSafeClient` (`typesafe-sdk`), model `jev-latest`, ghi usage tokens.
- Composite scoring per checkpoint: `screen_score = Σ wᵢ × normalizedᵢ` — trọng số đọc từ `policy.yaml`.
- **Confidence gate**: `confidence < 0.75` → verdict `needs_human_review` (ngưỡng chỉnh được trong policy).

### 5.5 Vision bridge

- Anthropic SDK, model Haiku, prompt ép trả JSON schema chặt (observation: các vùng nội dung, chỗ nghi lỗi thị giác, không bình luận lan man).
- Chỉ gọi với checkpoint có check visual bật; observation text nhét vào state trước khi hỏi JEV.
- Fail/timeout → check downgrade `skipped`, pipeline tiếp tục.

### 5.6 Report

- **HTML**: mỗi checkpoint — thumbnail screenshot, bảng checks (verdict, score, confidence, probabilities rút gọn), tổng điểm checkpoint/flow, mục nổi bật "Needs review", bảng chi phí (JEV tokens, vision calls).
- **JSON**: cùng dữ liệu machine-readable cho CI về sau.
- Layout đặt trong `reports/run-<id>/`.

## 6. Luồng dữ liệu chính (pipeline.py)

```
load flow.yaml + policy.yaml
→ driver.connect()
→ for step in flow:
     action?  → driver.tap/input/swipe/launch
     checkpoint? → StepArtifact = driver.capture()
                  state = extractor.normalize(artifact)
                  checks = router.select(state, policy)
                  results = [rule_check(state) | jev_check(state) | vision_jev_check(state)]
                  verdicts = composite(results, policy)
→ report.render(verdicts)
→ driver.quit()
```

## 7. Error handling

| Sự cố | Xử lý |
|---|---|
| Appium timeout/crash khi action | retry 1 lần → đánh dấu step `failed`, chạy tiếp checkpoint khác |
| App crash giữa flow | capture dialog crash — chính là finding cho nhóm error/anomaly |
| JEV API error / rate limit | check đó verdict `error` (retry 2 lần với backoff), pipeline không chết |
| Vision bridge fail | check downgrade `skipped (vision unavailable)` |
| Element không tìm thấy khi action | đánh dấu step failed + capture artifact để JEV phân tích (có thể là bug thật) |
| State quá lớn | extractor cắt giảm element, ghi cảnh báo vào report |

## 8. Testing strategy (TDD)

- **Unit**: extractor (fixture XML thật của 2 nền tảng → ScreenState), rule checks (bounds math), router (policy → path đúng), composite (mock JEV answers → đúng trọng số/confidence gate), report renderer (snapshot HTML), question bank schema.
- **Integration**: `FakeDriver` trả artifacts từ `tests/fixtures/` + JEV client mock → chạy toàn pipeline không cần thiết bị/API key.
- **E2E smoke** (Phase 1): flow thật trên Android emulator + app mẫu; cần `TYPESAFE_API_KEY` + `ANTHROPIC_API_KEY`.

## 9. App mẫu & môi trường

- **Phase 1 — Android** (trên máy Windows hiện tại): emulator + **Now in Android** (Google chính chủ, Compose, accessibility tree tốt, APK từ GitHub Releases).
- Vì app mẫu không có bug sẵn: một số check cấu hình theo **spec cố ý lệch thực tế** (VD: text kỳ vọng khác với text app hiển thị) hoặc fixture có bug nhân tạo → kiểm chứng agent phát hiện được.
- **Phase 2**: iOS simulator trên Mac + app mẫu iOS (VD: app demo SwiftUI/RN công khai); app thật của user (APK/IPA).
- **Phase 3**: Figma comparison (Figma API → JSON → JEV so UI tree), exploratory agent.

## 10. Success criteria (Phase 1)

1. Pipeline chạy repeatable cùng flow → cùng verdict (JEV self-consistent).
2. ≥ 90% verdict khớp với **expected outcomes được dán nhãn tay** trên bộ demo (kể cả bug nhân tạo được phát hiện).
3. Mọi finding đều kèm confidence; các finding needs-review hợp lý (đúng nhóm borderline).
4. Chi phí mỗi run ghi được trong report (JEV tokens + vision calls) và ở mức hợp lý cho một test run.
5. Thời gian 1 checkpoint (trừ action time) < 5s gồm cả JEV call.

## 11. Risks & mitigations

| Rủi ro | Mitigation |
|---|---|
| Setup Appium trên Windows công phu | pin version Appium/driver; script setup + doctor check |
| Accessibility tree nghèo (Compose/Flutter đôi khi ẩn text) | vision bridge bù phần thiếu; ghi nhận hạn chế (không dùng OCR ở v1) |
| JEV nhạy tiếng Anh, app đa ngôn ngữ | Phase 1 dùng app tiếng Anh; đa ngôn ngữ để sau |
| Giá JEV chưa biết | cost log mỗi run ngay từ đầu |
| False positive cao | confidence gate + tuning questions (iterate theo best practice TypeSafe) |
| iOS không chạy được trên Windows | driver abstraction sẵn; Phase 2 khi có Mac |

## 12. Ngưỡng & hằng số ban đầu (policy.yaml)

```yaml
confidence_gate: 0.75
weights:                    # composite per checkpoint
  functional: 0.35
  layout: 0.20
  content_quality: 0.15
  error_anomaly: 0.20
  visual: 0.10
check_toggles:
  functional: true
  layout: true
  content_quality: true
  error_anomaly: true
  visual: true
vision:
  model: claude-haiku-4-5
  max_calls_per_checkpoint: 1
```
