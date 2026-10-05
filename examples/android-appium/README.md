# Example 2: Android app with UI automation (Appium)

This example drives a real Android app through a YAML flow. At each
`checkpoint` the agent captures a **screenshot + UI tree**, then runs the 5
check groups (functional, layout, content quality, error/anomaly, visual) into
a weighted screen score — every verdict with confidence and evidence.

The bundled flow uses [Now in Android (NIA)](https://github.com/android/nowinandroid),
Google's reference app: launch → home → topics → settings.

## The flow

```yaml
# flows/login_smoke.yaml
name: login_smoke
app: com.google.samples.apps.nowinandroid
platform: android
steps:
  - action: launch
  - checkpoint: home        # capture + judge this screen
  - action: tap
    target: "acc-id:Topics"
  - checkpoint: topics
  - action: tap
    target: "acc-id:Settings"
  - checkpoint: settings
```

- **Selectors:** `res-id:`, `acc-id:`, `text:`, `xpath:` — find real values
  with [Appium Inspector](https://github.com/appium/appium-inspector).
- **Actions:** `launch`, `tap`, `input`, `swipe`.
- Expectations (which elements each checkpoint should contain) and group
  weights live in `config/policy.yaml`; device capabilities in
  `config/devices.yaml`.

## Prerequisites

1. **Full Android setup** (Android Studio, SDK, AVD emulator, JDK 17, Appium):
   follow [scripts/setup_android.md](../../scripts/setup_android.md) step by step.
2. **The NIA app** on the emulator — build from source
   (`gradlew :app:assembleProdDebug`) or install from the Play Store; NIA has
   no APK in its GitHub Releases.
3. **API keys** (same as Example 1): `TYPESAFE_API_KEY` + a vision source
   (`LLM_URL`/`MODEL_NAME`/`LLM_API_KEY` or `ANTHROPIC_API_KEY`).

## Run it

Terminal 1 — Appium server:

```bash
appium
```

Terminal 2 — the flow (emulator must be running):

```bash
export TYPESAFE_API_KEY=... LLM_URL=... MODEL_NAME=...   # or ANTHROPIC_API_KEY
uv run python -m jev_ui_agent run \
  --flow examples/android-appium/flows/login_smoke.yaml \
  --driver android
```

Open `reports/run-*/report.html` — checkpoints are judged independently; a
step failure is recorded and the flow continues (see "Failed steps" in the
report). Exit codes: `0` all passed · `1` failures · `2` configuration error.

## No emulator yet?

Run the same pipeline offline with the fake driver and bundled fixtures
(includes a planted `login.title` i18n bug for JEV to catch):

```bash
uv run python -m jev_ui_agent run --flow flows/demo_fake.yaml \
  --driver fake --policy config/policy.fake.yaml --fixtures-dir tests/fixtures/fake_run
```

## Writing your own flow

1. Copy `flows/login_smoke.yaml` and change `app` to your package name.
2. Walk your journey manually in Appium Inspector; note a selector per step.
3. Insert a `checkpoint` after every screen you want judged.
4. Tune expectations per checkpoint in `config/policy.yaml`
   (`functional_expectations`).
