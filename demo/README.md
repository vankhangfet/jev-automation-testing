# Demo: check a folder of login screenshots

This demo shows **Mode 1 (screenshot folder checking)** end-to-end, without any
device. `screens/login/` holds 5 synthetic mobile login screens: one correct,
four with a planted defect each. `rules/login.yaml` is written to catch exactly
those defects.

## The screens

| File | Planted defect |
|---|---|
| `01_login_ok.png` | none — should pass every rule |
| `02_login_layout_broken.png` | title overlaps the email field; **Sign in button hangs off the right edge** |
| `03_login_i18n_keys.png` | raw i18n keys (`login.title`, `auth.subtitle.hint`) rendered instead of human text |
| `04_login_error_banner.png` | red error banner ("Oops! Something went wrong.") over the form |
| `05_login_blank.png` | blank screen with only a loading dot |

Regenerate them at any time (requires the dev dependency Pillow):

```bash
uv run python scripts/make_demo_screens.py
```

## The rules

`rules/login.yaml` maps one rule to each defect (plus a rubric score as a
catch-all):

| Rule id | Type | Catches |
|---|---|---|
| `login_form_visible` | pass/fail | blank screen (05) |
| `no_cut_off_elements` | pass/fail | button off-screen (02) |
| `no_overlapping_elements` | pass/fail | title over the email field (02) |
| `heading_is_human_text` | pass/fail | i18n keys (03) |
| `no_error_banner` | pass/fail | red banner (04) |
| `layout_polish` | score ≥ 0.75 | general polish |

## Set up environment variables

The run needs two API sources — a JEV key and a vision model (see the root
[README](../README.md#configuration) for details):

| Variable | Purpose |
|---|---|
| `TYPESAFE_API_KEY` | JEV judgment engine (from [console.typesafe.ai](https://console.typesafe.ai)) |
| `LLM_URL` + `MODEL_NAME` | Any multimodal endpoint (Ollama, vLLM, OpenRouter, OpenAI/Anthropic-compatible) — takes priority over Option B |
| `LLM_API_KEY` | Key for that endpoint — leave empty for local servers |
| `ANTHROPIC_API_KEY` | Fallback vision source (Claude Haiku) if `LLM_URL`/`MODEL_NAME` are not set |

Copy the template and fill in your keys:

```bash
cp demo/.env.example demo/.env      # bash
copy demo\.env.example demo\.env    # PowerShell
```

`.env` is git-ignored, so your keys never reach the repo.

**`MODEL_NAME` must be multimodal** (accept image input). If it isn't, every
image fails — but now with the endpoint's own explanation, e.g.:

- `vision endpoint HTTP 400: ... "Unknown Model, please check the model code."` — the model name doesn't exist at `LLM_URL`
- `vision endpoint HTTP 400: ... "messages.content.type is invalid, allowed values: ['text']"` — the model is text-only, pick a vision model
- `vision model returned empty content — ... try a higher max_tokens or another model` — the model spent its token budget on reasoning

Worked example (Z.ai GLM coding endpoint): `LLM_URL=https://api.z.ai/api/coding/paas/v4`, `MODEL_NAME=glm-4.5v` (the glm-5.x family also accepts images; glm-4.5 / glm-4.5-air / glm-4.6 are text-only).

## Run it

The runner scripts load `.env` automatically (they also pick up a `.env` at the
repo root), so a filled-in file is all you need:

```bash
./demo/run.sh               # bash
.\demo\run.ps1              # PowerShell
```

Equivalent to:

```bash
export TYPESAFE_API_KEY=...        # JEV
export LLM_URL=... MODEL_NAME=...  # any multimodal vision model
# (or export ANTHROPIC_API_KEY=... to use Claude Haiku)

uv run python -m jev_ui_agent check-screenshots \
  --dir demo/screens/login --rules demo/rules/login.yaml --out demo/reports
```

Any extra flags pass through, e.g. `./demo/run.sh --workers 8 --limit 2`.

## Results

The run writes everything into `demo/reports/check-<timestamp>/`:

- `report.html` — open this; failing screens first, each with confidence + evidence
- `report.json` — same data for CI
- `checkpoint.jsonl` — per-image progress (pass to `--resume` to continue an interrupted run without paying again)

`demo/reports/` is git-ignored — results stay on your machine.

## Expected results

| Image | Verdict | Failing rule(s) |
|---|---|---|
| `01_login_ok.png` | ✅ passed | — |
| `02_login_layout_broken.png` | ❌ failed | `no_cut_off_elements` (and likely `no_overlapping_elements`, low `layout_polish`) |
| `03_login_i18n_keys.png` | ❌ failed | `heading_is_human_text` |
| `04_login_error_banner.png` | ❌ failed | `no_error_banner` |
| `05_login_blank.png` | ❌ failed | `login_form_visible` (and low `layout_polish`) |

The command exits `1` (defects found — that is the point of the demo). Open
`demo/reports/check-*/report.html`: failing screens are listed first, each with
confidence and evidence explaining *why* it failed.

> Exact verdicts can vary slightly per run (a low-confidence answer lands in
> `NEEDS_REVIEW` instead of pass/fail) — that is the confidence gate at work,
> not a bug.
