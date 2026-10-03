# jev-ui-agent

Agent kiểm tra UI mobile dùng **JEV** (judgment engine của Typesafe) làm bộ não phán đoán: thay vì chỉ so khớp selector cứng, JEV chấm điểm từng màn hình theo rubric (content quality, error/anomaly) kèm confidence. Kiến trúc **hybrid 3 lớp** — rule rẻ và deterministic → JEV trực tiếp trên UI state text → vision model (Claude) quan sát screenshot rồi để JEV phán xét — giúp giảm tối đa lời gọi API đắt đỏ. Triết lý **"code in control"**: agent là pipeline deterministic, mọi phán đoán đều có evidence (score, confidence, probabilities) trong report, không có bước tự quyết ngoài flow.

## Cài đặt

```bash
uv sync          # Python 3.12 pin sẵn qua .python-version
```

## Chạy test

```bash
uv run pytest    # 97 test, hoàn toàn offline
```

## Demo offline (không cần thiết bị hay API key)

Dùng fake driver với UI tree XML dựng sẵn trong `tests/fixtures/fake_run/` (3 màn home/topics/settings, có cài bug i18n `login.title` để JEV bắt khi có key):

```bash
uv run python -m jev_ui_agent run --flow flows/demo_fake.yaml \
  --driver fake --policy config/policy.fake.yaml \
  --fixtures-dir tests/fixtures/fake_run
```

Exit code `0` = mọi check pass; mở `reports/run-*/report.html` để xem điểm từng checkpoint, bảng checks và artifact. Muốn viết flow riêng, xem `flows/demo_fake.yaml` làm mẫu.

## Cấu trúc project

```
src/jev_ui_agent/
├── __main__.py        # CLI: jev-ui-agent run --flow ... --driver fake|android
├── pipeline.py        # orchestrator: flow → capture → checks → report
├── driver/            # BaseDriver + FakeDriver (fixture) + AndroidDriver (Appium)
├── extract/           # UI tree XML → ScreenState chuẩn hóa
├── checks/            # rule checks, router (rule → JEV → vision), composite score
├── jev/               # JEV client + question bank
├── vision/            # Claude vision bridge (screenshot → observation JSON)
└── report/            # JSON + HTML renderer
config/                # policy.yaml (NIA thật), policy.fake.yaml (demo), devices.yaml
flows/                 # định nghĩa flow test (yaml)
docs/superpowers/      # spec + plan của project
```

## Live E2E Android

Chạy thật trên Android emulator + Appium (UiAutomator2) với app Now in Android: xem runbook `scripts/setup_android.md` (cài Appium, emulator, build/lấy APK NIA) rồi:

```bash
uv run python -m jev_ui_agent run --flow flows/login_smoke.yaml --driver android
```

## Biến môi trường

Đọc từ môi trường shell (không dùng file `.env` tự động; xem mẫu `.env.example`):

- `TYPESAFE_API_KEY` — lấy từ console.typesafe.ai. Không có → các check JEV tự `SKIPPED`.
- `ANTHROPIC_API_KEY` — cho vision bridge. Không có → các check visual tự `SKIPPED`.

## Status

**Phase 1 hoàn tất**: Android offline (fake driver, rule + JEV + vision pipeline, report HTML/JSON, exit code CI-friendly) + hạ tầng live E2E Android. **Phase 2**: iOS driver và kiểm tra từ Figma design — xem `docs/superpowers/specs/`.
