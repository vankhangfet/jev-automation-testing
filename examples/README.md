# Examples

Two runnable examples, one per mode of the framework:

| Folder | Mode | Needs a device? | Needs API keys? |
|---|---|---|---|
| [`screenshot-folder/`](screenshot-folder/) | **Mode 1** — check a folder of existing screenshots with natural-language rules | no | yes (JEV + vision model) |
| [`android-appium/`](android-appium/) | **Mode 2** — drive an Android app with Appium and judge each screen on the way | yes (emulator or device) | yes, plus a demo APK |

Start with `screenshot-folder/` — it is fully offline on the check side (5
synthetic login screens with 4 planted defects), so you only need API keys.

`android-appium/` shows the full UI-automation loop: launch a real app, walk
through screens, capture screenshot + UI tree at each checkpoint, and get
verdicts with confidence and evidence. If you don't have an emulator yet, the
same pipeline runs offline with the fake driver:

```bash
uv run python -m jev_ui_agent run --flow flows/demo_fake.yaml \
  --driver fake --policy config/policy.fake.yaml --fixtures-dir tests/fixtures/fake_run
```
