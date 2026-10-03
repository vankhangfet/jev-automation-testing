# JEV Automation Testing

![Tests](https://img.shields.io/badge/tests-154%2F154%20passing-brightgreen) ![Python](https://img.shields.io/badge/python-3.12-blue) ![Driver](https://img.shields.io/badge/platform-Android%20%7C%20Fake-orange)

**A mobile UI testing agent that uses [JEV](https://docs.typesafe.ai/) (TypeSafe's judgment engine) as its decision-making brain.**

Instead of relying only on rigid selector matching, JEV scores each screen against structured rubrics (content quality, error/anomaly classification, …) and returns **confidence** and **probability distributions** — producing test reports where humans can read the *reasoning* behind every pass/fail, not just red and green marks.

The design follows the **"code in control"** philosophy (TypeSafe's official recommendation): the agent is a deterministic pipeline, no LLM decides the next step. Every judgment is atomic, backed by evidence in the report, and 100% reproducible across runs.

## Two ways to use this project

| | **Use case 1 — Existing screenshot folders** | **Use case 2 — Live UI automation** |
|---|---|---|
| You have… | a folder of captured screenshots (from a previous run, a manual session, another team's dump) | a running app on an emulator/device |
| You write… | natural-language rules (`rules/*.yaml`) | a navigation flow (`flows/*.yaml`) + expectations in `config/policy.yaml` |
| Command | `check-screenshots --dir … --rules …` | `run --flow … --driver android` |
| Device needed | ❌ none | ✅ Android emulator/device + Appium |
| Verdicts | each image × each rule → pass / fail / needs-review | each checkpoint × 5 check groups → weighted screen score |
| Cost per screen | 1 vision call + 1 JEV call (per unique image) | cheapest path first: many checks are free rules |

Both modes share the same judgment core, confidence gate (0.75), HTML/JSON reports and cost log.

## Architecture

```
Screenshots + UI state ──► Hybrid Check Router ──► Composite scoring ──► Report
                          "each check takes the cheapest path that can answer it"
                          ┌───────────────────────────────────────────┐
                          │ 1. RULES (plain code, zero AI cost)       │
                          │    element presence, overlap, off-screen  │
                          │ 2. JEV (one fan-out call / checkpoint)    │
                          │    raw i18n keys, typos, screen class     │
                          │ 3. VISION + JEV (most expensive, on demand)│
                          │    vision model extracts an observation   │
                          │    → JEV renders the verdict              │
                          └───────────────────────────────────────────┘
```

**Confidence gate**: any result with confidence below 0.75 is downgraded to `NEEDS_REVIEW` instead of a wrong pass/fail — the system's primary false-positive defense. `loading_stuck` and `empty_state` classifications also map to `NEEDS_REVIEW`, because a static snapshot cannot prove they are actual bugs.

## Getting started

```bash
git clone https://github.com/vankhangfet/jev-automation-testing.git
cd jev-automation-testing
uv sync          # Python 3.12 (pinned via .python-version)
uv run pytest    # 154 tests — fully offline, no device or API key required
```

API keys (see [Environment variables](#environment-variables) for all options):

```bash
export TYPESAFE_API_KEY=...    # JEV judgment engine — required for both modes
export ANTHROPIC_API_KEY=...   # vision source — OR set LLM_URL + MODEL_NAME
```

---

# Use case 1 — Check a folder of existing screenshots

No device, no UI tree, no flow file. Point the agent at a folder of PNG/JPG screenshots and a YAML file of natural-language rules; every image × rule pair gets a verdict in one HTML report.

## 1. Organize your folders

Group screenshots by feature — each folder gets its own rule set:

```
project/
├── screens/
│   ├── login/          login_01.png, login_error.png, login_empty.png ...
│   ├── onboarding/     onb_step1.png, onb_step2.png, onb_final.png ...
│   └── checkout/       cart.png, payment.png, confirm.png ...
└── rules/
    ├── login.yaml
    ├── onboarding.yaml
    └── checkout.yaml
```

> Tip: keep filenames unique across folders — the report lists images by filename.

## 2. Write the rules

`noul` rules get a plain yes/no judgment; `score` rules get a 5-level rubric (`criteria` / `pass_at` optional, defaults shown below).

`rules/login.yaml`:

```yaml
name: login_screens
rules:
  - id: login_form_visible
    instruction: "Email and password fields plus a login button are visible"
  - id: no_error_banner
    instruction: "No red error banner or error dialog is visible"
  - id: forgot_password_link
    instruction: "A 'Forgot password' link is visible near the login form"
  - id: form_polish
    type: score
    instruction: "Form alignment and spacing look consistent"
    pass_at: 0.75        # default; normalized 0-1 threshold on the 5-level rubric
```

`rules/onboarding.yaml`:

```yaml
name: onboarding_screens
rules:
  - id: progress_indicator
    instruction: "A step progress indicator is visible at the top"
  - id: next_button_visible
    instruction: "A 'Next' or 'Continue' button is visible and not disabled"
  - id: illustration_loaded
    instruction: "The illustration area is rendered, not blank or broken"
  - id: text_quality
    type: score
    instruction: "Onboarding texts are clear and well-written"
    criteria: [very poor, poor, acceptable, good, excellent]   # optional custom rubric
    pass_at: 0.6
```

**Rule-writing tips** (the JEV model only sees what the vision model observes):
- Describe things **visually verifiable on the screen** — visible elements, texts, states.
- The more specific, the fewer `NEEDS_REVIEW`: `"labeled 'Sign in'"` beats `"a login button"`.
- The instruction text is sent to JEV as the requirement — English gives the best accuracy.

## 3. Run

**One folder with its own rules:**

```bash
uv run python -m jev_ui_agent check-screenshots \
  --dir screens/login --rules rules/login.yaml --out reports/login
```

**All folders in one go (Git Bash) — each with its own rules:**

```bash
for s in login onboarding checkout; do
  uv run python -m jev_ui_agent check-screenshots \
    --dir "screens/$s" --rules "rules/$s.yaml" --out "reports/$s" || exit 1
done
```

PowerShell equivalent:

```powershell
foreach ($s in @("login","onboarding","checkout")) {
  uv run python -m jev_ui_agent check-screenshots `
    --dir "screens/$s" --rules "rules/$s.yaml" --out "reports/$s"
  if ($LASTEXITCODE -ne 0) { break }
}
```

**One shared rule set for every subfolder** (recursive by default):

```bash
uv run python -m jev_ui_agent check-screenshots --dir screens --rules rules/common.yaml
```

Useful flags: `--workers 4` (parallel images), `--limit 50` (smoke-test a subset), `--no-recursive` (top-level folder only), `--resume reports/login/check-...` (continue an interrupted run).

## 4. Read the results

Each command produces its own run dir `reports/<suite>/check-<timestamp>/`:

- `report.html` — **Batch summary** on top (total / passed / failed / needs review / errors / duplicates / missing), failing images first, then one card per image: screenshot + per-rule verdicts with confidence and evidence.
- `report.json` — the same, machine-readable (for CI tooling).
- `checkpoint.jsonl` — per-image progress log.

Exit codes: `0` = every image passes, `1` = any failed check or errored image (the loops above stop at the first failing suite), `2` = configuration problem (missing API keys, invalid `LLM_STYLE`).

**Interrupted run?** Re-run the same command with `--resume <run-dir>`: finished images are not re-billed, errored images are retried, and images deleted since the last run are kept in the report marked `missing`.

**Cost**: 1 vision call + 1 JEV call per **unique image** regardless of rule count (duplicate images are deduplicated by SHA-256). ~2,000 images ≈ $6–15 of Haiku-class vision calls, plus cheap JEV.

---

# Use case 2 — Live UI automation (Appium)

The agent drives the app through a flow you define, captures a screenshot + UI tree at each **checkpoint**, and runs all check groups (rules → JEV → vision) automatically.

## 1. Write the flow

`flows/my_flow.yaml` — actions navigate, checkpoints capture & analyze:

```yaml
name: login_smoke
app: com.example.app          # your app's package
platform: android
steps:
  - action: launch
  - checkpoint: home
  - action: tap
    target: "acc-id:Sign in"
  - checkpoint: login_form
  - action: input
    target: "acc-id:Email"
    value: "demo@example.com"
  - action: tap
    target: "acc-id:Submit"
  - checkpoint: after_submit
```

Selector prefixes: `res-id:` (resource-id), `acc-id:` (accessibility label / content-desc), `text:` (visible text), `xpath:` (escape hatch). Actions: `launch`, `tap`, `input`, `swipe` (x1/y1/x2/y2).

## 2. (Optional) Add functional expectations

In `config/policy.yaml`, assert that specific elements exist with the right text at each checkpoint:

```yaml
functional_expectations:
  - checkpoint: login_form
    element: "acc-id:Submit"
    expect_text: "Submit"
```

Everything else runs out of the box: layout heuristics (overlap / off-screen / truncation), JEV content-quality and screen-classification checks, visual checks via the vision bridge.

## 3. Configure the device & run

`config/devices.yaml` holds the Appium capabilities:

```yaml
android:
  capabilities:
    platformName: Android
    automationName: UiAutomator2
    deviceName: emulator-5554
    app: ./apps/your-app.apk     # resolved relative to the Appium server's cwd
    udid: emulator-5554          # recommended when several devices are attached
  viewport: {width: 1080, height: 2400}
```

Start the Appium server, then run the flow:

```bash
appium &                                                        # terminal 1
uv run python -m jev_ui_agent run --flow flows/my_flow.yaml --driver android   # terminal 2
```

Find the real selectors for your app with **Appium Inspector** (connect it to the same server and capabilities). Full environment setup — Appium, JDK 17, Android SDK/emulator, building the Now in Android sample APK — is in the [runbook](scripts/setup_android.md).

## 4. Try it offline first (fake driver)

No device yet? The bundled fake driver replays UI-tree fixtures end-to-end:

```bash
uv run python -m jev_ui_agent run --flow flows/demo_fake.yaml \
  --driver fake --policy config/policy.fake.yaml \
  --fixtures-dir tests/fixtures/fake_run
# → Run run-...: 3 checkpoints, 0 failed checks — open reports/run-*/report.html
```

The fixtures include a deliberately planted `login.title` i18n-key bug, so you can see a real finding in the report. Exit codes match `check-screenshots` (`0` / `1`, plus `2` on invalid vision configuration).

---

## Configuration reference

| File | Purpose |
|---|---|
| `flows/*.yaml` | UI-automation scenarios: actions + checkpoints |
| `rules/*.yaml` | natural-language rule sets for `check-screenshots` |
| `config/policy.yaml` | composite weights, confidence gate, per-group toggles, functional expectations |
| `config/policy.fake.yaml` | same, for the offline fake demo |
| `config/devices.yaml` | Appium capabilities + viewport per platform (Android/iOS) |
| `src/jev_ui_agent/jev/questions.py` | the JEV question bank — a **single file** humans can read and tune (a TypeSafe best practice) |

### Environment variables

Read from the shell (no automatic `.env` loading; see `.env.example`):

| Variable | Purpose |
|---|---|
| `TYPESAFE_API_KEY` | JEV judgment engine — from [console.typesafe.ai](https://console.typesafe.ai/keys). Missing → JEV checks are automatically `SKIPPED`. |
| `LLM_URL` | Base URL of any OpenAI- or Anthropic-style vision endpoint, e.g. `http://localhost:11434/v1` (Ollama) or `https://openrouter.ai/api/v1`. |
| `MODEL_NAME` | Vision model at that endpoint, e.g. `qwen2.5-vl`, `gpt-4o-mini`, `claude-haiku-4-5`. |
| `LLM_API_KEY` | Optional API key for `LLM_URL` — local servers (Ollama/vLLM) need none; hosted gateways do. |
| `LLM_STYLE` | Optional protocol hint: `openai` \| `anthropic`. Auto-detected from the URL by default (contains `/v1/messages` → anthropic). |
| `ANTHROPIC_API_KEY` | Fallback vision source: the Anthropic SDK with pinned Claude Haiku. |

**Vision source priority**: `LLM_URL` + `MODEL_NAME` (generic bridge) → `ANTHROPIC_API_KEY` (Claude bridge) → vision checks `SKIPPED`.

```bash
# OpenRouter (hosted, needs a key)
export LLM_URL=https://openrouter.ai/api/v1
export MODEL_NAME=qwen/qwen2.5-vl-72b-instruct
export LLM_API_KEY=sk-or-...

# Ollama (local, no key needed)
export LLM_URL=http://localhost:11434/v1
export MODEL_NAME=qwen2.5-vl

# Anthropic-style gateway: set LLM_STYLE=anthropic, or rely on auto-detect
# when the URL already ends in /v1/messages
export LLM_URL=https://gateway.internal/v1/messages
export MODEL_NAME=claude-haiku-4-5
export LLM_API_KEY=...
export LLM_STYLE=anthropic
```

**The model must be multimodal** (able to read images). A text-only model fails every observation — in `check-screenshots` every image is recorded as an error, while in `run` mode the visual checks come back `SKIPPED`. Either way the report makes the misconfigured `MODEL_NAME` visible.

## Project layout

```
src/jev_ui_agent/
├── __main__.py        # CLI: run | check-screenshots
├── pipeline.py        # run-mode orchestrator: flow → capture → checks → report
├── batch.py           # check-screenshots orchestrator: scan → dedup → parallel judge → report
├── driver/            # BaseDriver + FakeDriver + AndroidDriver (Appium)
├── extract/           # UI tree XML → normalized ScreenState (Android + iOS)
├── checks/            # rule checks, router (rules→JEV→vision), composite score
├── jev/               # JEV client (retry/usage tracking) + question bank + rule-question builder
├── rules.py           # natural-language rules loader (check-screenshots)
├── vision/            # vision bridges — Claude Haiku + generic LLM (screenshot → observation JSON)
└── report/            # JSON + HTML renderers
config/                # policy, devices, policy.fake
flows/                 # UI-automation flow YAML files
tests/                 # 154 tests + fixtures (UI tree XML for both platforms)
docs/superpowers/      # design specs + implementation plans (TDD, with hardening notes)
scripts/               # setup_android.md (E2E runbook), verify_typesafe_sdk.py
```

## Tech stack

| Component | Technology |
|---|---|
| Language | Python 3.12 (uv) |
| Judgment engine | JEV `jev-latest` ([typesafe-sdk](https://docs.typesafe.ai/)) |
| Vision bridge | any multimodal LLM via `LLM_URL` + `MODEL_NAME` (OpenAI- or Anthropic-style); default Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| UI automation | Appium 2 (`appium-python-client` 6.x, UiAutomator2) |
| Testing | pytest — 154 tests, every API boundary mocked |

## Roadmap

- ✅ **Phase 1**: full hybrid pipeline (rules + JEV + vision), HTML/JSON reports with cost tracking, fake-driver demo, Appium Android infrastructure, offline test suite
- ✅ **Phase 2a**: batch screenshot checking with natural-language rules, plus any-LLM vision bridge
- 🔜 **Phase 2b**: iOS driver (XCUITest) — the extractor already parses XCUI trees; **Figma design comparison** (Figma API → JSON → JEV cross-checked against the UI tree)
- 🔮 **Phase 3**: exploratory mode (the agent explores the app on its own)

Technical details and known risks (iOS nested coordinates, container noise, …) are recorded in the hardening notes at the end of [`docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md`](docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md).

## Documentation

- [Design specs](docs/superpowers/specs/) — Phase 1 architecture & JEV constraints; batch checking; multi-LLM vision
- [Implementation plans](docs/superpowers/plans/) — TDD task breakdowns with hardening notes
- [Android E2E runbook](scripts/setup_android.md)
