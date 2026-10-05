# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Mobile UI testing agent that judges app screens with JEV (typesafe.ai judgment engine). Two modes share one check core:

- **Mode 1 — `check-screenshots`**: batch-judge a folder of existing screenshots against natural-language YAML rules.
- **Mode 2 — `run`**: drive an app through a YAML flow (Appium UiAutomator2 on Android, or the offline `fake` driver), capture screenshot + UI tree at each checkpoint, run 5 check groups into a weighted screen score.

Every verdict carries confidence + evidence; anything below the confidence gate (0.75, from policy YAML) becomes `NEEDS_REVIEW` instead of a wrong pass/fail.

## Commands

```bash
uv sync                                   # install (Python 3.12, hatchling build)
uv run pytest                             # full suite — fully offline, no keys/device needed
uv run pytest tests/test_batch.py -q      # one file
uv run pytest tests/test_batch.py::test_sha256_dedup -q   # one test

# Mode 2 offline demo (fake driver, fixtures under tests/fixtures/fake_run)
uv run python -m jev_ui_agent run --flow flows/demo_fake.yaml \
  --driver fake --policy config/policy.fake.yaml --fixtures-dir tests/fixtures/fake_run

# Mode 1 (needs TYPESAFE_API_KEY + a vision source in env)
uv run python -m jev_ui_agent check-screenshots \
  --dir examples/screenshot-folder/screens/login \
  --rules examples/screenshot-folder/rules/login.yaml \
  --out examples/screenshot-folder/reports

uv run python scripts/make_demo_screens.py   # regenerate example PNGs (dev Pillow)
```

Exit codes: `0` all passed · `1` failures/errors · `2` configuration error.

## Architecture

```
src/jev_ui_agent/
├── __main__.py        CLI: `run` | `check-screenshots`; env checks, exit codes
├── pipeline.py        Mode 2: load flow → driver steps → capture → checks → report
├── batch.py           Mode 1: scan → sha256 dedup → thread pool → _judge_image → resume
├── rules.py           load_rules: YAML validation (ids, types, {language} placeholder guard)
├── langtag.py         filename `-xx` suffix → language name (placeholder substitution)
├── models.py          Verdict / CheckResult / CheckpointReport / RunReport
├── checks/            hybrid router: free geometry rules first, then JEV, then vision+JEV
├── jev/client.py      JevClient.judge(state, questions) — one fan-out call for ALL questions
├── jev/rule_questions.py  build_questions(rules) → typesafe_sdk Noul/Score per rule
├── vision/            observe_detailed(image) → normalized dict observation
│   ├── claude_bridge.py    VisionBridge (Anthropic SDK) + shared helpers/prompts
│   ├── generic_bridge.py   GenericVisionBridge (httpx, openai|anthropic style)
│   └── __init__.py         make_vision_bridge(): LLM_URL+MODEL_NAME → generic,
│                          else ANTHROPIC_API_KEY → claude, else None
└── report/            html.py (Jinja template, failing screens first), json_report.py
```

**Cost model drives design:** JEV fans out — N rules cost the same single call per unique image. Vision `calls` and JEV `usage` counters count **billing events** (incremented only after a successful HTTP response), guarded by thread locks. Duplicate images (sha256) are judged once.

## Non-obvious invariants

- The SDK module is **`typesafe_sdk`**, not `typesafe`.
- `NoulAnswer` has **no confidence** in the wire schema; it is derived as `round(abs(2*(value-0.5)), 4)`.
- Rule instructions may contain the `{language}` placeholder only; any other `{...}` fails at `load_rules`. Substitution happens per image in `batch._judge_image` from the filename suffix (`-en`, `-vi`...). Untagged images get those rules `SKIPPED` (reason in evidence) and they are **not sent to JEV**.
- `check-screenshots` requires a vision source (`LLM_URL`+`MODEL_NAME` or `ANTHROPIC_API_KEY`) → exit 2 without one; `TYPESAFE_API_KEY` missing also exits 2 (all rules need JEV).
- Vision HTTP 4xx (except 408/429) is a permanent config error: raise immediately with the endpoint's error body, never retry. 429/5xx retry once. Blank model content (reasoning models) → error suggesting higher `max_tokens`.
- `checkpoint.jsonl` is flushed after **every** image (kill-safe); resume reuses hashes with later-line-wins and tolerates corrupt/truncated lines (`errors="replace"` + per-line try/except). Missing images keep their old results.
- The fake driver reads fixtures (`tests/fixtures/fake_run`) so Mode 2 runs offline.
- Code comments, docstrings and many error messages are in **Vietnamese** — match that style.

## Testing conventions

All 168 tests run offline: `FakeJev`/`FakeVision` in `tests/test_batch.py` are the canonical fakes (FakeJev.judge must increment `usage["calls"]`; bridge `calls` increments only post-success). Vision bridge tests fake `httpx.Client` with `SimpleNamespace(post=...)`. New features follow TDD — write the failing test first.

## Repo hygiene

- `project-1/` is a **git-ignored local workspace** (private screenshots + keys). Never commit it, never touch `project-1/.env`.
- Also git-ignored: `reports/`, `.env`, `apps/`, `*.apk`.
- Commits end with `Co-Authored-By: Claude Code <noreply@anthropic.com>`; work merges to `main` and pushes to `github.com/vankhangfet/jev-automation-testing`.
- Specs live in `docs/superpowers/specs/`, implementation plans in `docs/superpowers/plans/` (their "hardening notes" sections hold the roadmap).
