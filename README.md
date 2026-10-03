# JEV Automation Testing

![Tests](https://img.shields.io/badge/tests-154%2F154%20passing-brightgreen) ![Python](https://img.shields.io/badge/python-3.12-blue) ![Driver](https://img.shields.io/badge/platform-Android%20%7C%20Fake-orange)

**A mobile UI testing agent that uses [JEV](https://docs.typesafe.ai/) (TypeSafe's judgment engine) as its decision-making brain.**

Instead of relying only on rigid selector matching, JEV scores each screen against structured rubrics (content quality, error/anomaly classification, …) and returns **confidence** and **probability distributions** — producing test reports where humans can read the *reasoning* behind every pass/fail, not just red and green marks.

The design follows the **"code in control"** philosophy (TypeSafe's official recommendation): the agent is a deterministic pipeline, no LLM decides the next step. Every judgment is atomic, backed by evidence in the report, and 100% reproducible across runs.

## Architecture

```
Mobile App → UI Automation (Appium/Fake) → Screenshot + UI Tree
                                                    ↓
                              ┌─────────────────────┴─────────────────────┐
                              │            Hybrid Check Router            │
                              │   "each check takes the cheapest path     │
                              │              that can answer it"          │
                              ├───────────────────────────────────────────┤
                              │ 1. RULES (plain code, zero AI cost)       │
                              │    element presence, overlap, off-screen  │
                              │ 2. JEV (one fan-out call / checkpoint)    │
                              │    raw i18n keys, typos, screen class     │
                              │ 3. VISION + JEV (most expensive, on demand)│
                              │    Claude extracts observation → JEV      │
                              │    renders the verdict                    │
                              └─────────────────────┬─────────────────────┘
                                                    ↓
                       Composite scoring + Confidence gate (0.75)
                                                    ↓
                       HTML/JSON report + Cost log (JEV tokens, vision calls)
```

## The 5 check groups

| Group | Path | Examples |
|---|---|---|
| **Functional** | rules + JEV | element exists, text matches, placeholder "Lorem ipsum"? |
| **Layout heuristics** | rules | occluding overlap, off-screen overflow, truncation candidates |
| **Content quality** | JEV direct | raw i18n keys (`login.title`), TODO/FIXME leftovers, typo severity on a 5-level rubric |
| **Error/anomaly** | JEV direct | screen classification: normal / error_screen / crash_dialog / empty_state / loading_stuck |
| **Visual** | vision → JEV | blank screens, broken images, clipped text (via a structured Claude Haiku observation) |

**Confidence gate**: any result with confidence below 0.75 is downgraded to `NEEDS_REVIEW` instead of a wrong pass/fail — the system's primary false-positive defense. `loading_stuck` and `empty_state` classifications also map to `NEEDS_REVIEW`, because a static snapshot cannot prove they are actual bugs.

## Getting started

```bash
git clone https://github.com/vankhangfet/jev-automation-testing.git
cd jev-automation-testing
uv sync          # Python 3.12 (pinned via .python-version)
uv run pytest    # 154 tests — fully offline, no device or API key required
```

## Offline demo (60 seconds, nothing else needed)

The fake driver runs against pre-built UI tree XML fixtures (`tests/fixtures/fake_run/` — three screens, one with a deliberately planted `login.title` i18n bug to prove the agent catches it):

```bash
uv run python -m jev_ui_agent run --flow flows/demo_fake.yaml \
  --driver fake --policy config/policy.fake.yaml \
  --fixtures-dir tests/fixtures/fake_run
```

Output:

```
Run run-20261003-085216: 3 checkpoints, 0 failed checks
Report: reports\run-20261003-085216\report.html
```

Open `reports/run-*/report.html`: each checkpoint shows its screenshot, the checks table (verdict / score / confidence), the weighted screen score, and a cost table (JEV/vision calls + tokens). Exit code `0` = all green, `1` = failed check / errored checkpoint / failed step — CI-ready out of the box.

## Running on a real Android device (Appium)

The Appium UiAutomator2 driver is fully wired. Follow the runbook at [`scripts/setup_android.md`](scripts/setup_android.md) (Appium server, emulator, building the Now in Android APK — *note: the NIA repo does not publish APKs in its Releases; build from source or install from the Play Store*), then:

```bash
appium &                                          # terminal 1 — server at 127.0.0.1:4723
uv run python -m jev_ui_agent run \
  --flow flows/login_smoke.yaml --driver android  # terminal 2
```

## Batch screenshot checking (rules-based)

Already have a folder of screenshots (from a previous run, a manual capture session, another team's dump)? `check-screenshots` judges every image against your own **natural-language rules** — no device, no UI tree, no flow file needed. Each screenshot × rule pair gets a pass/fail/needs-review verdict in a single HTML report.

Write the rules in YAML — `noul` rules get a plain yes/no judgment, `score` rules get a 5-level rubric (`criteria`/`pass_at` are optional):

```yaml
name: login-screens-regression
rules:
  - id: no-loading-stuck
    instruction: The screen must not be stuck on a loading spinner
  - id: no-blank-areas
    instruction: No large blank/empty region covers more than a third of the screen
  - id: readability
    type: score
    instruction: "Text is readable: sufficient contrast, no clipping, consistent sizing"
    criteria: [very poor, poor, acceptable, good, excellent]
    pass_at: 0.6
```

Then point the agent at the folder (PNG and JPG are both supported):

```bash
uv run python -m jev_ui_agent check-screenshots \
  --dir ./screens --rules rules.yaml \
  [--workers 4] [--limit 50] [--no-recursive] [--resume reports/check-...]
```

How it works: each image gets **one vision call** (the vision model extracts a comprehensive observation of the screen) and **one JEV call** that fans out every rule — a JEV answer with confidence below 0.75 is downgraded to `NEEDS_REVIEW`, same gate as the live pipeline.

It scales to thousands of images: duplicate images are deduplicated by SHA-256, images run in parallel across `--workers`, and every result is appended to `checkpoint.jsonl` — after an interruption, `--resume <run-dir>` picks up where you left off (finished images are not re-run, errored images are retried).

**Cost**: ~2,000 images ≈ $6–15 of Haiku vision calls (other models vary), plus JEV (cheap). This mode requires a vision source — `LLM_URL` + `MODEL_NAME` **or** `ANTHROPIC_API_KEY` — **and** `TYPESAFE_API_KEY`; the CLI exits with code `2` if a source is missing (unlike `run`, there is no partial offline mode since every rule needs vision + JEV). Exit `0` = all pass, `1` = any failed check or errored image.

## Configuration

| File | Purpose |
|---|---|
| `flows/*.yaml` | test scenarios: actions (launch/tap/input/swipe) + checkpoints (where the agent captures & analyzes) |
| `config/policy.yaml` | composite weights, confidence gate, per-group toggles, functional expectations (tuned for the real NIA app) |
| `config/policy.fake.yaml` | same, for the offline demo |
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

**Vision source priority**: `LLM_URL` + `MODEL_NAME` (generic bridge) → `ANTHROPIC_API_KEY` (Claude bridge) → vision checks `SKIPPED`. The vision model comes from `MODEL_NAME` (generic bridge) or the pinned Claude Haiku default (`ANTHROPIC_API_KEY` path) — `policy.yaml` no longer controls the vision model.

Examples:

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

**The model must be multimodal** (able to read images). A text-only model fails every observation — in `check-screenshots` every image is recorded as an error, while in `run` mode the visual checks come back `SKIPPED` (a failed observation maps to `VisionUnavailable` → skip, not error). Either way the report makes the misconfigured `MODEL_NAME` visible.

## Project layout

```
src/jev_ui_agent/
├── __main__.py        # CLI: run --flow ... --driver fake|android
├── pipeline.py        # orchestrator: flow → capture → checks → report
├── driver/            # BaseDriver + FakeDriver + AndroidDriver (Appium)
├── extract/           # UI tree XML → normalized ScreenState (Android + iOS)
├── checks/            # rule checks, router (rules→JEV→vision), composite score
├── jev/               # JEV client (retry/usage tracking) + question bank
├── vision/            # vision bridges — Claude Haiku + generic LLM (screenshot → observation JSON)
└── report/            # JSON + HTML renderers
config/                # policy, devices, policy.fake
flows/                 # test flow YAML files
tests/                 # 154 tests + fixtures (UI tree XML for both platforms)
docs/superpowers/      # design spec + implementation plan (13 TDD tasks)
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
- 🔜 **Phase 2**: iOS driver (XCUITest) — the extractor already parses XCUI trees; **Figma design comparison** (Figma API → JSON → JEV cross-checked against the UI tree)
- 🔮 **Phase 3**: exploratory mode (the agent explores the app on its own)

Technical details and known risks (iOS nested coordinates, container noise, …) are recorded in the hardening notes at the end of [`docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md`](docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md).

## Documentation

- [Design spec](docs/superpowers/specs/2026-10-02-jev-ui-checking-agent-design.md) — architecture decisions & JEV platform constraints
- [Implementation plan](docs/superpowers/plans/2026-10-02-jev-ui-checking-agent.md) — 13 TDD tasks with hardening notes
- [Android E2E runbook](scripts/setup_android.md)
