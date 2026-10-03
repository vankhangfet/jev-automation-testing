# JEV Automation Testing

![Tests](https://img.shields.io/badge/tests-97%2F97%20passing-brightgreen) ![Python](https://img.shields.io/badge/python-3.12-blue) ![Driver](https://img.shields.io/badge/platform-Android%20%7C%20Fake-orange)

**Agent kiểm tra UI mobile dùng [JEV](https://docs.typesafe.ai/) (judgment engine của TypeSafe) làm bộ não phán đoán.**

Thay vì chỉ so khớp selector cứng nhắc, JEV chấm điểm từng màn hình theo rubric có cấu trúc (content quality, error/anomaly…) kèm **confidence** và **probabilities** — kết quả là báo cáo test mà con người đọc được *lý do* đằng sau mỗi pass/fail, không chỉ con số xanh đỏ.

Triết lý **"code in control"** (theo khuyến cáo chính thức của TypeSafe): agent là một pipeline deterministic, không có LLM tự quyết định bước tiếp theo. Mọi phán đoán đều nguyên tử (atomic), có evidence trong report, và có thể chạy lại 100% giống nhau.

## Kiến trúc

```
Mobile App → UI Automation (Appium/Fake) → Screenshot + UI Tree
                                                    ↓
                              ┌─────────────────────┴─────────────────────┐
                              │            Hybrid Check Router            │
                              │  "mỗi check đi con đường rẻ nhất có thể"  │
                              ├───────────────────────────────────────────┤
                              │ 1. RULE (code thuần, 0đ AI)               │
                              │    element tồn tại, overlap, off-screen   │
                              │ 2. JEV (1 call fan-out / checkpoint)      │
                              │    i18n key thô, typo, phân loại màn hình │
                              │ 3. VISION + JEV (đắt nhất, chỉ khi cần)   │
                              │    Claude trích observation → JEV phán    │
                              └─────────────────────┬─────────────────────┘
                                                    ↓
                       Composite scoring + Confidence gate (0.75)
                                                    ↓
                       Report HTML/JSON + Cost log (JEV tokens, vision calls)
```

## 5 nhóm kiểm tra

| Nhóm | Đường đi | Ví dụ |
|---|---|---|
| **Functional** | rule + JEV | element tồn tại, text đúng, placeholder "Lorem ipsum"? |
| **Layout heuristics** | rule | overlap che khuất, tràn màn hình, ứng cử viên cắt chữ |
| **Content quality** | JEV trực tiếp | i18n key thô (`login.title`), TODO/FIXME, chấm điểm typo theo rubric 5 mức |
| **Error/anomaly** | JEV trực tiếp | phân loại màn: normal / error_screen / crash_dialog / empty_state / loading_stuck |
| **Visual** | vision → JEV | màn trống, ảnh broken, chữ bị cắt (qua observation JSON của Claude Haiku) |

**Confidence gate**: kết quả có confidence < 0.75 bị hạ xuống `NEEDS_REVIEW` thay vì pass/fail sai — lớp chống false-positive chính của hệ thống. `loading_stuck`/`empty_state` cũng chỉ ra `NEEDS_REVIEW` vì snapshot tĩnh không chứng minh được đó là bug.

## Bắt đầu

```bash
git clone https://github.com/vankhangfet/jev-automation-testing.git
cd jev-automation-testing
uv sync          # Python 3.12 (pin sẵn qua .python-version)
uv run pytest    # 97 tests — hoàn toàn offline, không cần thiết bị hay API key
```

## Demo offline (60 giây, không cần gì thêm)

Fake driver chạy trên UI tree XML dựng sẵn (`tests/fixtures/fake_run/` — 3 màn hình, có cài sẵn bug i18n `login.title` để chứng minh agent phát hiện được):

```bash
uv run python -m jev_ui_agent run --flow flows/demo_fake.yaml \
  --driver fake --policy config/policy.fake.yaml \
  --fixtures-dir tests/fixtures/fake_run
```

Kết quả:

```
Run run-20261003-085216: 3 checkpoints, 0 failed checks
Report: reports\run-20261003-085216\report.html
```

Mở `reports/run-*/report.html`: mỗi checkpoint có screenshot, bảng checks (verdict / score / confidence), tổng điểm màn hình theo trọng số, và bảng chi phí (số call JEV/vision + token). Exit code `0` = pass hết, `1` = có failed check/errored checkpoint/failed step — dùng được cho CI ngay.

## Chạy thật trên Android (Appium)

Hạ tầng driver Appium UiAutomator2 đã sẵn sàng. Xem runbook đầy đủ tại [`scripts/setup_android.md`](scripts/setup_android.md) (Appium server, emulator, build APK Now in Android — *lưu ý: repo NIA không publish APK trong Releases, phải build từ nguồn hoặc cài từ Play Store*), rồi:

```bash
appium &                                        # terminal 1 — server 127.0.0.1:4723
uv run python -m jev_ui_agent run \
  --flow flows/login_smoke.yaml --driver android  # terminal 2
```

## Cấu hình

| File | Vai trò |
|---|---|
| `flows/*.yaml` | kịch bản test: action (launch/tap/input/swipe) + checkpoint (nơi capture & phân tích) |
| `config/policy.yaml` | trọng số composite, ngưỡng confidence, bật/tắt nhóm check, kỳ vọng functional (bản cho app NIA thật) |
| `config/policy.fake.yaml` | bản cho demo offline |
| `config/devices.yaml` | Appium capabilities + viewport mỗi nền tảng (Android/iOS) |
| `src/jev_ui_agent/jev/questions.py` | question bank JEV — **một file duy nhất** để người review đọc/điều chỉnh câu hỏi (best practice TypeSafe) |

### Biến môi trường

Đọc từ shell (không tự load `.env`; xem mẫu `.env.example`):

- `TYPESAFE_API_KEY` — từ [console.typesafe.ai](https://console.typesafe.ai/keys). Thiếu → check JEV tự `SKIPPED`.
- `ANTHROPIC_API_KEY` — cho vision bridge. Thiếu → check visual tự `SKIPPED`.

## Cấu trúc project

```
src/jev_ui_agent/
├── __main__.py        # CLI: run --flow ... --driver fake|android
├── pipeline.py        # orchestrator: flow → capture → checks → report
├── driver/            # BaseDriver + FakeDriver + AndroidDriver (Appium)
├── extract/           # UI tree XML → ScreenState chuẩn hóa (Android + iOS)
├── checks/            # rule checks, router (rule→JEV→vision), composite score
├── jev/               # JEV client (retry/usage) + question bank
├── vision/            # Claude Haiku bridge (screenshot → observation JSON)
└── report/            # JSON + HTML renderer
config/                # policy, devices, policy.fake
flows/                 # flow test YAML
tests/                 # 97 tests + fixtures (UI tree XML 2 nền tảng)
docs/superpowers/      # design spec + implementation plan (13 task, TDD)
scripts/               # setup_android.md (runbook E2E), verify_typesafe_sdk.py
```

## Tech stack

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.12 (uv) |
| Judgment engine | JEV `jev-latest` ([typesafe-sdk](https://docs.typesafe.ai/)) |
| Vision bridge | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| UI automation | Appium 2 (`appium-python-client` 6.x, UiAutomator2) |
| Test | pytest — 97 tests, mock toàn bộ API boundary |

## Lộ trình

- ✅ **Phase 1**: pipeline hybrid đầy đủ (rule + JEV + vision), report HTML/JSON + cost, fake driver demo, hạ tầng Appium Android, 97 tests offline
- 🔜 **Phase 2**: driver iOS (XCUITest) — extractor đã hỗ trợ XCUI tree; so sánh implementation với **Figma design** (Figma API → JSON → JEV đối chiếu UI tree)
- 🔮 **Phase 3**: chế độ exploratory (agent tự khám phá app)

Chi tiết kỹ thuật và các rủi ro đã ghi nhận (iOS nested coordinates, container noise…) nằm trong hardening notes cuối [`docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md`](docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md).

## Tài liệu

- [Design spec](docs/superpowers/specs/2026-10-02-jev-ui-checking-agent-design.md) — quyết định kiến trúc & ràng buộc nền tảng JEV
- [Implementation plan](docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md) — 13 task TDD kèm hardening notes
- [Runbook E2E Android](scripts/setup_android.md)
