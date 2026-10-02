# JEV Mobile UI Checking Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng pipeline Python kiểm tra UI mobile (Android trước, iOS kiến trúc sẵn) dùng JEV làm judgment engine, hybrid rule/JEV/vision, xuất report HTML+JSON kèm confidence và chi phí.

**Architecture:** Orchestrator deterministic (`pipeline.py`) chạy flow YAML qua driver (Appium/Fake), mỗi checkpoint capture artifacts → extractor chuẩn hóa thành `ScreenState` → router chọn đường check rẻ nhất (rule thuần → JEV trực tiếp → vision+JEV) → composite scoring với confidence gate → report. Triết lý "code in control, JEV chỉ phán đoán nguyên tử" theo docs TypeSafe.

**Tech Stack:** Python 3.11+ (uv), Appium (`appium-python-client` v5, UiAutomator2/XCUITest), `typesafe-sdk` (JEV `jev-latest`), `anthropic` (vision bridge, `claude-haiku-4-5-20251001`), PyYAML, Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-jev-ui-checking-agent-design.md`

---

## File Structure

```
pyproject.toml                     # deps + pytest config (pythonpath=src)
.gitignore  .env.example
config/devices.yaml                # Appium capabilities + viewport mỗi nền tảng
config/policy.yaml                 # ngưỡng, trọng số, toggles, expectations
flows/login_smoke.yaml             # flow mẫu (Android, Now in Android)
src/jev_ui_agent/
  __init__.py  models.py           # Bounds, UIElement, StepArtifact, ScreenState, CheckResult, Verdict, reports
  flows.py                         # load + validate flow YAML
  driver/base.py                   # BaseDriver ABC
  driver/selectors.py              # parse "res-id:x" → ("id","x") — pure, testable
  driver/fake.py                   # FakeDriver đọc fixtures
  driver/android.py                # Appium UiAutomator2
  driver/__init__.py               # make_driver factory
  extract/normalize.py             # parse_android / parse_ios / build_state
  checks/rules.py                  # functional + layout rule checks (code thuần)
  checks/router.py                 # routing rule/jev/vision+jev, fan-out 1 call
  checks/composite.py              # score_checkpoint + apply_confidence_gate
  jev/questions.py                 # question bank — 1 file constants
  jev/client.py                    # JevClient wrap TypeSafeClient + usage
  vision/claude_bridge.py          # VisionBridge → observation JSON
  report/json_report.py  report/html.py
  pipeline.py  __main__.py         # orchestrator + CLI
tests/fixtures/                    # XML fixtures, fake_run/, policy_test.yaml
scripts/verify_typesafe_sdk.py  scripts/setup_android.md
```

Quy ước chung: mọi module trong `src/jev_ui_agent/` dùng `from __future__ import annotations`. Chạy test bằng `uv run pytest` (đã cấu hình `pythonpath=["src"]`).

---

### Task 1: Scaffold project

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`
- Create: `config/devices.yaml`, `config/policy.yaml`, `flows/login_smoke.yaml`
- Create: `src/jev_ui_agent/__init__.py` (rỗng)
- Create: `tests/test_scaffold.py`

- [ ] **Step 1: Init project với uv và tạo pyproject.toml**

```bash
cd C:/Working/FY26/Personal/jev-agent-ui-checking
uv init --no-readme --python 3.11 --vcs none 2>/dev/null || true
```

Sau đó ghi đè `pyproject.toml`:

```toml
[project]
name = "jev-ui-agent"
version = "0.1.0"
description = "Mobile UI checking agent with JEV judgment engine"
requires-python = ">=3.11"
dependencies = [
    "appium-python-client>=5.0",
    "typesafe-sdk",
    "anthropic>=0.40",
    "pyyaml>=6",
    "jinja2>=3",
]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jev_ui_agent"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Tạo .gitignore và .env.example**

`.gitignore`:
```
__pycache__/
.venv/
.pytest_cache/
reports/
apps/
node_modules/
.env
*.apk
*.app
```

`.env.example`:
```
TYPESAFE_API_KEY=your_key_from_console.typesafe.ai
ANTHROPIC_API_KEY=your_key
```

- [ ] **Step 3: Tạo config/devices.yaml**

```yaml
android:
  capabilities:
    platformName: Android
    automationName: UiAutomator2
    deviceName: emulator-5554
    app: ./apps/nowinandroid.apk
    noReset: "true"
  viewport: {width: 1080, height: 2400}
ios:
  capabilities:
    platformName: iOS
    automationName: XCUITest
    deviceName: iPhone 16
    platformVersion: "18.0"
    app: ./apps/DemoApp.app
  viewport: {width: 1170, height: 2532}
```

- [ ] **Step 4: Tạo config/policy.yaml**

```yaml
confidence_gate: 0.75
weights:
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
functional_expectations:
  - checkpoint: home
    element: "text:For You"
    expect_text: "For You"
  - checkpoint: topics
    element: "acc-id:Topics"
    expect_text: null
layout:
  overlap_min_ratio: 0.10
  offscreen_tolerance_px: 2
  truncation_char_width_ratio: 0.025
content_quality:
  typo_pass_score: 0.75
vision:
  model: claude-haiku-4-5-20251001
  max_calls_per_checkpoint: 1
```

- [ ] **Step 5: Tạo flows/login_smoke.yaml** (flow mẫu cho app Now in Android — selector sẽ tinh chỉnh ở Task 13 bằng Appium Inspector)

```yaml
name: login_smoke
app: com.google.samples.apps.nowinandroid
platform: android
steps:
  - action: launch
  - checkpoint: home
  - action: tap
    target: "acc-id:Topics"
  - checkpoint: topics
  - action: tap
    target: "acc-id:Settings"
  - checkpoint: settings
```

- [ ] **Step 6: Viết test scaffold**

`tests/test_scaffold.py`:
```python
def test_package_imports():
    import jev_ui_agent
    assert jev_ui_agent is not None
```

- [ ] **Step 7: Cài deps và chạy test**

```bash
uv sync
uv run pytest -v
```
Expected: `1 passed`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: scaffold project structure and config"
```

---

### Task 2: Domain models + selectors

**Files:**
- Create: `src/jev_ui_agent/models.py`
- Create: `src/jev_ui_agent/driver/selectors.py`
- Test: `tests/test_models.py`, `tests/test_selectors.py`

- [ ] **Step 1: Viết test models trước**

`tests/test_models.py`:
```python
from jev_ui_agent.models import Bounds, CheckResult, Verdict


def test_bounds_props():
    b = Bounds(10, 20, 110, 270)
    assert b.width == 100
    assert b.height == 250
    assert b.area == 25000


def test_bounds_intersection():
    a = Bounds(0, 0, 100, 100)
    b = Bounds(50, 50, 150, 150)
    inter = a.intersection(b)
    assert inter == Bounds(50, 50, 100, 100)
    assert a.intersection(Bounds(200, 200, 300, 300)) is None


def test_verdict_values():
    assert Verdict.PASS.value == "pass"
    assert Verdict.NEEDS_REVIEW.value == "needs_review"
    r = CheckResult("x", "layout", "rule", Verdict.PASS)
    assert r.probabilities == {}
    assert r.evidence == {}
```

- [ ] **Step 2: Run test — expect FAIL (ModuleNotFoundError)**

Run: `uv run pytest tests/test_models.py -v`
Expected: `ModuleNotFoundError: No module named 'jev_ui_agent.models'`

- [ ] **Step 3: Viết models.py**

`src/jev_ui_agent/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Bounds:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def intersection(self, other: "Bounds") -> Optional["Bounds"]:
        x1, y1 = max(self.x1, other.x1), max(self.y1, other.y1)
        x2, y2 = min(self.x2, other.x2), min(self.y2, other.y2)
        if x1 >= x2 or y1 >= y2:
            return None
        return Bounds(x1, y1, x2, y2)


@dataclass
class UIElement:
    id: str = ""             # resource-id / native id
    type: str = ""           # widget class rút gọn (Button, TextView...)
    text: str = ""           # text/value hiển thị
    content_desc: str = ""   # accessibility label
    bounds: Bounds = field(default_factory=lambda: Bounds(0, 0, 0, 0))
    clickable: bool = False
    displayed: bool = True

    @property
    def label(self) -> str:
        return self.text or self.content_desc


@dataclass
class StepArtifact:
    checkpoint: str
    screenshot_path: str
    source_xml: str
    activity: str = ""


@dataclass
class ScreenState:
    run_id: str
    checkpoint: str
    platform: str  # "android" | "ios"
    app: str
    viewport: dict  # {"width": int, "height": int}
    elements: list[UIElement] = field(default_factory=list)
    screenshot: str = ""

    def find(self, selector: str) -> Optional[UIElement]:
        from jev_ui_agent.driver.selectors import find_element
        return find_element(self.elements, selector)


@dataclass
class CheckResult:
    check_id: str
    group: str      # functional | layout | content_quality | error_anomaly | visual
    path: str       # rule | jev | vision+jev
    verdict: Verdict
    score: Optional[float] = None
    confidence: Optional[float] = None
    probabilities: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class CheckpointReport:
    checkpoint: str
    screen_score: Optional[float] = None
    results: list[CheckResult] = field(default_factory=list)
    screenshot: str = ""
    error: str = ""


@dataclass
class RunReport:
    run_id: str
    flow_name: str
    started_at: str
    checkpoints: list[CheckpointReport] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    costs: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Viết test selectors**

`tests/test_selectors.py`:
```python
import pytest

from jev_ui_agent.driver.selectors import find_element, parse
from jev_ui_agent.models import Bounds, UIElement


def test_parse_prefixes():
    assert parse("res-id:login_btn") == ("id", "login_btn")
    assert parse("acc-id:Sign in") == ("acc", "Sign in")
    assert parse("text:Hello") == ("text", "Hello")
    assert parse("xpath://a/b") == ("xpath", "//a/b")


def test_parse_invalid():
    with pytest.raises(ValueError):
        parse("login_btn")


def test_find_by_id_suffix():
    els = [UIElement(id="com.example:id/login_btn", type="Button", text="Sign in")]
    assert find_element(els, "res-id:login_btn") is els[0]


def test_find_by_acc_and_text():
    els = [
        UIElement(id="a", content_desc="Email field"),
        UIElement(id="b", text="Welcome"),
    ]
    assert find_element(els, "acc-id:Email field") is els[0]
    assert find_element(els, "text:Welcome") is els[1]
    assert find_element(els, "text:Missing") is None
```

- [ ] **Step 5: Run — expect FAIL**

Run: `uv run pytest tests/test_selectors.py -v`
Expected: `ModuleNotFoundError: ... driver.selectors`

- [ ] **Step 6: Viết selectors.py** (pure, không import appium)

`src/jev_ui_agent/driver/selectors.py`:
```python
from __future__ import annotations

from jev_ui_agent.models import UIElement

_PREFIXES = {"res-id:": "id", "acc-id:": "acc", "text:": "text", "xpath:": "xpath"}


def parse(selector: str) -> tuple[str, str]:
    for prefix, kind in _PREFIXES.items():
        if selector.startswith(prefix):
            return kind, selector[len(prefix):]
    raise ValueError(f"Selector phải có prefix một trong {sorted(_PREFIXES)}: {selector!r}")


def matches(el: UIElement, kind: str, value: str) -> bool:
    if kind == "id":
        if el.id == value:
            return True
        return el.id.endswith(f"/{value}") or el.id.endswith(f":id/{value}")
    if kind == "acc":
        return el.content_desc == value
    if kind == "text":
        return el.text == value or el.content_desc == value
    if kind == "xpath":
        return False  # xpath chỉ dùng với driver thật, không match trên state
    return False


def find_element(elements: list[UIElement], selector: str) -> UIElement | None:
    kind, value = parse(selector)
    for el in elements:
        if matches(el, kind, value):
            return el
    return None
```

- [ ] **Step 7: Run toàn bộ — expect PASS**

Run: `uv run pytest -v`
Expected: all passed.

- [ ] **Step 8: Commit**

```bash
git add src/jev_ui_agent/models.py src/jev_ui_agent/driver/selectors.py tests/test_models.py tests/test_selectors.py
git commit -m "feat: domain models and selector parsing"
```

---

### Task 3: Flow loader

**Files:**
- Create: `src/jev_ui_agent/flows.py`
- Test: `tests/test_flows.py`

- [ ] **Step 1: Viết test trước**

`tests/test_flows.py`:
```python
from pathlib import Path

import pytest

from jev_ui_agent.flows import FlowError, load_flow

VALID = """
name: demo
app: com.example
platform: android
steps:
  - action: launch
  - checkpoint: home
  - action: tap
    target: "acc-id:Go"
  - checkpoint: second
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "flow.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid_flow(tmp_path):
    flow = load_flow(_write(tmp_path, VALID))
    assert flow["name"] == "demo"
    kinds = [s["kind"] for s in flow["steps"]]
    assert kinds == ["action", "checkpoint", "action", "checkpoint"]
    assert flow["steps"][1]["name"] == "home"
    assert flow["steps"][2]["target"] == "acc-id:Go"


@pytest.mark.parametrize("bad", [
    "steps:\n  - action: dance\n",                      # action lạ
    "steps:\n  - action: tap\n",                       # tap thiếu target
    "steps:\n  - action: input\n    target: 't:x'\n",  # input thiếu value
    "steps:\n  - action: unknown_kind\n",              # không phải action/checkpoint
    "name: x\nsteps: []\n",                            # không có step nào
])
def test_invalid_flows(tmp_path, bad):
    with pytest.raises(FlowError):
        load_flow(_write(tmp_path, bad))


def test_missing_file():
    with pytest.raises(FlowError):
        load_flow(Path("nope.yaml"))
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_flows.py -v`
Expected: `ModuleNotFoundError: ... jev_ui_agent.flows`

- [ ] **Step 3: Viết flows.py**

`src/jev_ui_agent/flows.py`:
```python
from __future__ import annotations

from pathlib import Path

import re

import yaml

_ACTIONS = {"launch", "tap", "input", "swipe"}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class FlowError(ValueError):
    pass


def load_flow(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        raise FlowError(f"Flow file không tồn tại: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as e:
        raise FlowError(f"Không đọc/parse được flow file: {e}") from e
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list) or not raw["steps"]:
        raise FlowError("Flow phải có 'steps' là danh sách không rỗng")
    steps: list[dict] = []
    for i, item in enumerate(raw["steps"]):
        if not isinstance(item, dict):
            raise FlowError(f"Step {i} không hợp lệ: {item!r}")
        if "checkpoint" in item:
            name = item["checkpoint"]
            if not isinstance(name, str) or not name.strip():
                raise FlowError(f"Checkpoint {i} thiếu tên")
            name = name.strip()
            if not _NAME_RE.match(name):
                raise FlowError(f"Checkpoint {i}: tên {name!r} chỉ được chứa chữ, số, '.', '_', '-'")
            if any(s["kind"] == "checkpoint" and s["name"] == name for s in steps):
                raise FlowError(f"Checkpoint bị trùng tên: {name!r}")
            steps.append({"kind": "checkpoint", "name": name})
            continue
        action = item.get("action")
        if action not in _ACTIONS:
            raise FlowError(f"Step {i}: action phải thuộc {sorted(_ACTIONS)}, got {action!r}")
        if action in {"tap", "input"} and not item.get("target"):
            raise FlowError(f"Step {i}: {action} cần 'target'")
        if action == "input" and item.get("value") is None:
            raise FlowError(f"Step {i}: input cần 'value'")
        if action == "swipe" and not all(k in item for k in ("x1", "y1", "x2", "y2")):
            raise FlowError(f"Step {i}: swipe cần x1,y1,x2,y2")
        steps.append({**item, "kind": "action"})
    return {"name": raw.get("name", "unnamed"), "app": raw.get("app", ""),
            "platform": raw.get("platform", "android"), "steps": steps}
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_flows.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/jev_ui_agent/flows.py tests/test_flows.py
git commit -m "feat: flow yaml loader with validation"
```

---

### Task 4: Extractor (XML → ScreenState)

**Files:**
- Create: `src/jev_ui_agent/extract/normalize.py`, `src/jev_ui_agent/extract/__init__.py` (rỗng)
- Create: `tests/fixtures/android_home.xml`, `tests/fixtures/ios_login.xml`
- Test: `tests/test_extractor.py`

- [ ] **Step 1: Tạo fixture Android** (chứa bug nhân tạo: subtitle là i18n key thô `login.title`)

`tests/fixtures/android_home.xml`:
```xml
<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example"
        content-desc="" clickable="false" displayed="true" bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="com.example:id/header" class="android.widget.LinearLayout"
          content-desc="" clickable="false" displayed="true" bounds="[0,100][1080,300]">
      <node index="0" text="Welcome" resource-id="com.example:id/title" class="android.widget.TextView"
            content-desc="" clickable="false" displayed="true" bounds="[40,150][500,250]"/>
      <node index="1" text="login.title" resource-id="com.example:id/subtitle" class="android.widget.TextView"
            content-desc="" clickable="false" displayed="true" bounds="[40,260][600,300]"/>
    </node>
    <node index="1" text="Sign in" resource-id="com.example:id/login_btn" class="android.widget.Button"
          content-desc="" clickable="true" displayed="true" bounds="[100,800][980,880]"/>
    <node index="2" text="" resource-id="" class="android.widget.ImageView" content-desc="Hero image"
          clickable="false" displayed="true" bounds="[0,300][1080,780]"/>
    <node index="3" text="Hidden" resource-id="com.example:id/ghost" class="android.widget.TextView"
          content-desc="" clickable="false" displayed="false" bounds="[0,0][100,50]"/>
  </node>
</hierarchy>
```

- [ ] **Step 2: Tạo fixture iOS**

`tests/fixtures/ios_login.xml`:
```xml
<?xml version='1.0' encoding='UTF-8'?>
<AppiumAUT>
  <XCUIElementTypeApplication type="Application" name="Demo" label="Demo">
    <XCUIElementTypeWindow type="Window">
      <XCUIElementTypeOther type="Other" name="login_container" label="">
        <XCUIElementTypeStaticText type="StaticText" name="title" label="Welcome"
            x="40" y="150" width="460" height="100" visible="true"/>
        <XCUIElementTypeTextField type="TextField" name="email_field" label="Email"
            value="demo@example.com" x="40" y="800" width="1000" height="80" visible="true"/>
        <XCUIElementTypeButton type="Button" name="signin_btn" label="Sign in"
            x="100" y="900" width="880" height="80" visible="true"/>
        <XCUIElementTypeStaticText type="StaticText" name="hidden_lbl" label="Ghost"
            x="0" y="0" width="10" height="10" visible="false"/>
      </XCUIElementTypeOther>
    </XCUIElementTypeWindow>
  </XCUIElementTypeApplication>
</AppiumAUT>
```

- [ ] **Step 3: Viết test extractor**

`tests/test_extractor.py`:
```python
from pathlib import Path

from jev_ui_agent.extract.normalize import build_state, parse_android, parse_ios
from jev_ui_agent.models import StepArtifact

FIX = Path(__file__).parent / "fixtures"


def test_parse_android():
    els = parse_android((FIX / "android_home.xml").read_text(encoding="utf-8"))
    labels = {e.label for e in els}
    assert "Sign in" in labels and "login.title" in labels
    assert all(e.displayed for e in els)  # ghost bị lọc
    btn = next(e for e in els if e.label == "Sign in")
    assert btn.id == "com.example:id/login_btn"
    assert btn.type == "Button"
    assert (btn.bounds.x1, btn.bounds.y1, btn.bounds.x2, btn.bounds.y2) == (100, 800, 980, 880)


def test_parse_ios():
    els = parse_ios((FIX / "ios_login.xml").read_text(encoding="utf-8"))
    btn = next(e for e in els if e.type == "Button")
    assert btn.content_desc == "Sign in"
    assert btn.id == "signin_btn"
    assert btn.clickable
    tf = next(e for e in els if e.type == "TextField")
    assert tf.text == "demo@example.com"
    assert all(e.displayed for e in els)  # Ghost visible=false bị lọc


def test_build_state_and_find():
    artifact = StepArtifact(
        checkpoint="home",
        screenshot_path="/tmp/x.png",
        source_xml=(FIX / "android_home.xml").read_text(encoding="utf-8"),
        activity=".MainActivity",
    )
    state = build_state(artifact, run_id="run-1", platform="android",
                        app="com.example", viewport={"width": 1080, "height": 2400})
    assert state.checkpoint == "home"
    found = state.find("res-id:login_btn")
    assert found is not None and found.label == "Sign in"
    assert state.find("acc-id:Hero image").type == "ImageView"


def test_build_state_caps_elements():
    artifact = StepArtifact(checkpoint="c", screenshot_path="",
                            source_xml=(FIX / "android_home.xml").read_text(encoding="utf-8"))
    state = build_state(artifact, run_id="r", platform="android", app="a",
                        viewport={"width": 1080, "height": 2400}, max_elements=2)
    assert len(state.elements) <= 2
```

- [ ] **Step 4: Run — expect FAIL**

Run: `uv run pytest tests/test_extractor.py -v`
Expected: `ModuleNotFoundError: ... extract.normalize`

- [ ] **Step 5: Viết extract/normalize.py**

`src/jev_ui_agent/extract/normalize.py`:
```python
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from jev_ui_agent.models import Bounds, ScreenState, StepArtifact, UIElement

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")  # chấp nhận tọa độ âm


def parse_bounds_str(s: str) -> Bounds:
    m = _BOUNDS_RE.search(s or "")
    if not m:
        return Bounds(0, 0, 0, 0)
    x1, y1, x2, y2 = (int(v) for v in m.groups())
    return Bounds(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _short_class(cls: str) -> str:
    return cls.rsplit(".", 1)[-1] if cls else ""


def parse_android(source_xml: str) -> list[UIElement]:
    root = ET.fromstring(source_xml)
    els: list[UIElement] = []
    for node in root.iter("node"):
        if node.get("visible") == "false" or node.get("displayed") == "false":
            continue
        els.append(UIElement(
            id=node.get("resource-id", ""),
            type=_short_class(node.get("class", "")),
            text=node.get("text", ""),
            content_desc=node.get("content-desc", ""),
            bounds=parse_bounds_str(node.get("bounds", "")),
            clickable=node.get("clickable") == "true",
            displayed=True,
        ))
    return els


def parse_ios(source_xml: str) -> list[UIElement]:
    root = ET.fromstring(source_xml)
    els: list[UIElement] = []
    for node in root.iter():
        if not node.tag.startswith("XCUIElementType"):
            continue
        if node.get("visible") == "false":
            continue
        try:
            x, y = int(float(node.get("x", 0))), int(float(node.get("y", 0)))
            w, h = int(float(node.get("width", 0))), int(float(node.get("height", 0)))
        except ValueError:
            x = y = w = h = 0
        els.append(UIElement(
            id=node.get("name", ""),
            type=node.tag.replace("XCUIElementType", ""),
            text=node.get("value", ""),
            content_desc=node.get("label", ""),
            bounds=Bounds(x, y, x + w, y + h),
            clickable=node.tag.endswith("Button") or node.get("clickable") == "true",
            displayed=True,
        ))
    return els


def _interesting(el: UIElement) -> bool:
    return el.label != "" or el.clickable or el.id != ""


def build_state(artifact: StepArtifact, *, run_id: str, platform: str, app: str,
                viewport: dict, max_elements: int = 100) -> ScreenState:
    parser = parse_android if platform == "android" else parse_ios
    els = [e for e in parser(artifact.source_xml) if _interesting(e)][:max_elements]
    return ScreenState(
        run_id=run_id, checkpoint=artifact.checkpoint, platform=platform, app=app,
        viewport=viewport, elements=els, screenshot=artifact.screenshot_path,
    )
```

- [ ] **Step 6: Run — expect PASS**

Run: `uv run pytest tests/test_extractor.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add src/jev_ui_agent/extract/ tests/test_extractor.py tests/fixtures/
git commit -m "feat: ui tree extractor for android and ios"
```

---

### Task 5: Rule checks (functional + layout)

**Files:**
- Create: `src/jev_ui_agent/checks/__init__.py` (rỗng), `src/jev_ui_agent/checks/rules.py`
- Test: `tests/test_rules.py`

- [ ] **Step 1: Viết test trước**

`tests/test_rules.py`:
```python
from jev_ui_agent.checks.rules import functional_checks, layout_checks
from jev_ui_agent.models import Bounds, ScreenState, UIElement, Verdict

POLICY = {
    "functional_expectations": [
        {"checkpoint": "home", "element": "res-id:login_btn", "expect_text": "Sign in"},
        {"checkpoint": "home", "element": "res-id:missing_btn", "expect_text": None},
        {"checkpoint": "other", "element": "res-id:x", "expect_text": None},
    ],
    "layout": {"overlap_min_ratio": 0.10, "offscreen_tolerance_px": 2,
               "truncation_char_width_ratio": 0.025},
}


def make_state(els, checkpoint="home"):
    return ScreenState(run_id="r", checkpoint=checkpoint, platform="android",
                       app="a", viewport={"width": 1080, "height": 2400}, elements=els)


def test_functional_pass_fail():
    els = [UIElement(id="com.example:id/login_btn", text="Sign in", type="Button")]
    results = functional_checks(make_state(els), POLICY)
    by_id = {r.check_id: r for r in results}
    assert by_id["functional/element:res-id:login_btn"].verdict is Verdict.PASS
    assert by_id["functional/element:res-id:missing_btn"].verdict is Verdict.FAIL


def test_functional_text_mismatch():
    els = [UIElement(id="com.example:id/login_btn", text="Sign In!", type="Button")]
    results = functional_checks(make_state(els), POLICY)
    r = next(r for r in results if r.check_id.endswith("login_btn"))
    assert r.verdict is Verdict.FAIL
    assert r.evidence["expected"] == "Sign in"


def test_functional_no_expectations_skipped():
    results = functional_checks(make_state([], checkpoint="nowhere"), POLICY)
    assert results[0].verdict is Verdict.SKIPPED


def test_layout_overlap_detected():
    els = [
        UIElement(id="a", text="Hello", bounds=Bounds(0, 0, 200, 100)),
        UIElement(id="b", text="World", bounds=Bounds(50, 0, 250, 100)),
    ]
    results = layout_checks(make_state(els), POLICY)
    overlaps = [r for r in results if r.check_id.startswith("layout/overlap")]
    assert overlaps[0].verdict is Verdict.FAIL


def test_layout_clean_pass():
    els = [
        UIElement(id="a", text="Hello", bounds=Bounds(0, 0, 200, 100)),
        UIElement(id="b", text="World", bounds=Bounds(0, 200, 200, 300)),
    ]
    results = layout_checks(make_state(els), POLICY)
    assert all(r.verdict is Verdict.PASS for r in results)


def test_layout_offscreen_fail():
    els = [UIElement(id="a", text="Far", bounds=Bounds(0, 0, 1200, 100))]  # x2 > 1080
    results = layout_checks(make_state(els), POLICY)
    off = [r for r in results if r.check_id.startswith("layout/offscreen")]
    assert off[0].verdict is Verdict.FAIL


def test_layout_truncation_candidates_needs_review():
    # 40 ký tự * (1080*0.025=27px) = 1080px > width 300
    els = [UIElement(id="a", text="x" * 40, bounds=Bounds(0, 0, 300, 100))]
    results = layout_checks(make_state(els), POLICY)
    tr = next(r for r in results if r.check_id == "layout/truncation_candidates")
    assert tr.verdict is Verdict.NEEDS_REVIEW
    assert "x" * 40 in tr.evidence["candidates"]
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_rules.py -v`
Expected: `ModuleNotFoundError: ... checks.rules`

- [ ] **Step 3: Viết checks/rules.py**

`src/jev_ui_agent/checks/rules.py`:
```python
from __future__ import annotations

from jev_ui_agent.driver.selectors import find_element
from jev_ui_agent.models import CheckResult, ScreenState, Verdict


def functional_checks(state: ScreenState, policy: dict) -> list[CheckResult]:
    exps = [e for e in policy.get("functional_expectations", [])
            if e.get("checkpoint") == state.checkpoint]
    if not exps:
        return [CheckResult("functional/no-expectations", "functional", "rule",
                            Verdict.SKIPPED,
                            evidence={"note": "no expectations configured"})]
    out: list[CheckResult] = []
    for exp in exps:
        sel = exp["element"]
        check_id = f"functional/element:{sel}"
        el = find_element(state.elements, sel)
        if el is None:
            out.append(CheckResult(check_id, "functional", "rule", Verdict.FAIL,
                                   evidence={"missing": sel}))
            continue
        expect_text = exp.get("expect_text")
        if expect_text is not None and el.label.strip() != str(expect_text).strip():
            out.append(CheckResult(check_id, "functional", "rule", Verdict.FAIL,
                                   evidence={"element": sel, "actual": el.label,
                                             "expected": expect_text}))
        else:
            out.append(CheckResult(check_id, "functional", "rule", Verdict.PASS,
                                   evidence={"element": sel, "label": el.label}))
    return out


def layout_checks(state: ScreenState, policy: dict) -> list[CheckResult]:
    cfg = policy.get("layout", {})
    labeled = [e for e in state.elements if e.label]
    results: list[CheckResult] = []

    # 1) Overlap: cặp element có text giao nhau quá ngưỡng
    min_ratio = float(cfg.get("overlap_min_ratio", 0.10))
    overlaps: list[tuple] = []
    for i, a in enumerate(labeled):
        for b in labeled[i + 1:]:
            inter = a.bounds.intersection(b.bounds)
            if inter is None:
                continue
            smaller = min(a.bounds.area, b.bounds.area) or 1
            ratio = inter.area / smaller
            if ratio >= min_ratio:
                overlaps.append((a, b, ratio))
    if overlaps:
        for a, b, ratio in overlaps:
            results.append(CheckResult(
                f"layout/overlap:{a.label}|{b.label}", "layout", "rule", Verdict.FAIL,
                evidence={"a": a.label, "b": b.label, "overlap_ratio": round(ratio, 3)}))
    else:
        results.append(CheckResult("layout/overlap", "layout", "rule", Verdict.PASS,
                                   evidence={"labeled_elements": len(labeled)}))

    # 2) Off-screen: tràn khỏi viewport quá tolerance
    tol = int(cfg.get("offscreen_tolerance_px", 2))
    vw, vh = state.viewport["width"], state.viewport["height"]
    offscreen = [e for e in labeled
                 if e.bounds.x1 < -tol or e.bounds.y1 < -tol
                 or e.bounds.x2 > vw + tol or e.bounds.y2 > vh + tol]
    if offscreen:
        for e in offscreen:
            results.append(CheckResult(
                f"layout/offscreen:{e.label}", "layout", "rule", Verdict.FAIL,
                evidence={"element": e.label,
                          "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                          "viewport": [vw, vh]}))
    else:
        results.append(CheckResult("layout/offscreen", "layout", "rule", Verdict.PASS))

    # 3) Truncation candidates: ước lượng chữ không đủ chỗ — visual check xác nhận sau
    char_w = vw * float(cfg.get("truncation_char_width_ratio", 0.025))
    candidates = [e for e in labeled if len(e.label) * char_w > e.bounds.width]
    if candidates:
        results.append(CheckResult(
            "layout/truncation_candidates", "layout", "rule", Verdict.NEEDS_REVIEW,
            evidence={"candidates": [c.label for c in candidates],
                      "note": "cần xác nhận thị giác qua visual check"}))
    else:
        results.append(CheckResult("layout/truncation_candidates", "layout", "rule",
                                   Verdict.PASS))
    return results
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_rules.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/jev_ui_agent/checks/ tests/test_rules.py
git commit -m "feat: functional and layout rule checks"
```

---

### Task 6: JEV client + question bank

**Files:**
- Create: `src/jev_ui_agent/jev/__init__.py` (rỗng), `src/jev_ui_agent/jev/questions.py`, `src/jev_ui_agent/jev/client.py`
- Create: `scripts/verify_typesafe_sdk.py`
- Test: `tests/test_jev_client.py`

Lưu ý: SDK `typesafe-sdk` cài module tên `typesafe_sdk` (đã xác minh trong venv: exports `TypeSafeClient/Noul/Score/Choice`, `system_one(state, questions, *, model=None)` nhận kwarg `model`) — mọi import dùng `from typesafe_sdk import ...`. Docs quickstart mô tả (`from typesafe import TypeSafeClient` + `client.system_one(state=..., questions=...)`, response có `.answers[key].noul/.score/.choice`, `.confidence`, `.probabilities`, usage tokens). Script verify ở Step 1 sẽ pin lại signature thật trước khi viết client.

- [ ] **Step 1: Viết scripts/verify_typesafe_sdk.py và chạy để pin API surface**

`scripts/verify_typesafe_sdk.py`:
```python
"""Pin API surface của typesafe-sdk trước khi viết JevClient.

Chạy: uv run python scripts/verify_typesafe_sdk.py
Nếu TYPESAFE_API_KEY có trong env sẽ ping live 1 câu noul.
"""
import inspect
import os
import sys


def main() -> int:
    try:
        import typesafe_sdk
    except ImportError:
        print("FAIL: khong import duoc module 'typesafe_sdk' — kiem tra pip install typesafe-sdk")
        return 1
    names = [n for n in dir(typesafe) if not n.startswith("_")]
    print("typesafe exports:", names)
    from typesafe_sdk import TypeSafeClient
    print("TypeSafeClient methods:", [n for n in dir(TypeSafeClient) if not n.startswith("_")])
    for m in ("system_one", "systemOne", "judge"):
        if hasattr(TypeSafeClient, m):
            print(f"signature {m}:", inspect.signature(getattr(TypeSafeClient, m)))
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("(khong co TYPESAFE_API_KEY — skip live ping)")
        return 0
    from typesafe_sdk import Noul
    client = TypeSafeClient()
    resp = client.system_one(
        state="The login button says 'Sign in'.",
        questions={"ok": Noul(instructions="Does the text mention a sign-in button?")},
    )
    print("live ping answers:", resp.answers if hasattr(resp, "answers") else resp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `uv run python scripts/verify_typesafe_sdk.py`
Expected: in ra exports + signature. **Nếu signature/khác tên method hay cấu trúc answers khác mô tả trong Task này → điều chỉnh `jev/client.py` (Step 5) theo output thật**, giữ nguyên interface `JevClient.judge(state, questions) -> dict[str, dict]`.

- [ ] **Step 2: Viết test trước (mock TypeSafeClient)**

`tests/test_jev_client.py`:
```python
from types import SimpleNamespace

import pytest

import jev_ui_agent.jev.client as client_mod
from jev_ui_agent.jev.client import JevClient, JevError


def _fake_resp():
    return SimpleNamespace(
        answers={
            "is_urgent": SimpleNamespace(noul=1.0, confidence=None, probabilities=None),
            "frustration": SimpleNamespace(score=2.0, confidence=0.9,
                                           probabilities={0: 0.1, 1: 0.2, 2: 0.7}),
            "topic": SimpleNamespace(choice="technical", confidence=0.78,
                                     probabilities={"technical": 0.85, "billing": 0.15}),
        },
        usage=SimpleNamespace(input_tokens=392, output_tokens=65),
    )


def test_judge_parses_answers(monkeypatch):
    fake = SimpleNamespace(system_one=lambda **kw: _fake_resp())
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient()
    out = jc.judge("state", {"q": object()})
    assert out["is_urgent"] == {"value": 1.0, "confidence": None, "probabilities": {}}
    assert out["frustration"]["value"] == 2.0
    assert out["frustration"]["probabilities"] == {"0": 0.1, "1": 0.2, "2": 0.7}
    assert out["topic"]["value"] == "technical"
    assert jc.usage == {"calls": 1, "input_tokens": 392, "output_tokens": 65}


def test_judge_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    def boom(**kw):
        calls["n"] += 1
        raise RuntimeError("api down")

    fake = SimpleNamespace(system_one=boom)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient(retries=2)
    jc._sleep = lambda s: None  # bỏ delay khi test
    with pytest.raises(JevError):
        jc.judge("state", {"q": object()})
    assert calls["n"] == 3  # 1 lần đầu + 2 retry


def test_judge_model_kwarg_fallback(monkeypatch):
    seen = {}

    def sysone(**kw):
        seen.update(kw)
        if kw.get("model"):
            raise TypeError("unexpected keyword 'model'")
        return _fake_resp()

    fake = SimpleNamespace(system_one=sysone)
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient()
    jc._sleep = lambda s: None
    out = jc.judge("state", {"q": object()})
    assert out["topic"]["value"] == "technical"
```

- [ ] **Step 3: Run — expect FAIL**

Run: `uv run pytest tests/test_jev_client.py -v`
Expected: `ModuleNotFoundError: ... jev.client`

- [ ] **Step 4: Viết jev/questions.py (question bank — 1 file constants)**

`src/jev_ui_agent/jev/questions.py`:
```python
from __future__ import annotations

from typesafe_sdk import Choice, Noul, Score


def core_questions(content_quality: bool = True, error_anomaly: bool = True) -> dict:
    """Bộ câu hỏi JEV chạy trực tiếp trên ScreenState payload."""
    q: dict = {}
    if error_anomaly:
        q["screen_class"] = Choice(
            instructions="Classify what kind of mobile screen this element tree represents.",
            criteria={
                "normal": "A fully rendered screen showing its expected content.",
                "error_screen": "The screen displays an error message or a failed-load state.",
                "crash_dialog": "A system dialog saying the app crashed or stopped.",
                "empty_state": "The screen rendered but contains no content (empty list, blank body).",
                "loading_stuck": "Only a loading indicator is visible, content never arrived.",
            },
        )
    if content_quality:
        q["has_raw_i18n_key"] = Noul(
            instructions="Does any visible element text look like an untranslated i18n key, "
                         "e.g. `login.title`, `welcome.message`, `btn.submit`?")
        q["has_dev_text"] = Noul(
            instructions="Does any visible text contain developer artifacts such as TODO, "
                         "FIXME, stack traces, debug values, or filler like 'Lorem ipsum'?")
        q["typo_severity"] = Score(
            instructions="Rate the writing quality of all visible labels and texts.",
            criteria=[
                "No visible text at all.",
                "Severe issues: misspellings or broken grammar in multiple prominent labels.",
                "Some misspellings or awkward grammar in one or two labels.",
                "Minor issues only: inconsistent capitalization or spacing.",
                "Clean, consistent, well-written text.",
            ],
        )
    return q


def visual_questions() -> dict:
    """Bộ câu hỏi JEV chạy trên payload có visual_observation (từ vision bridge)."""
    return {
        "visual_blank": Noul(
            instructions="Using the visual_observation field, does the screen look mostly "
                         "blank or unrendered?"),
        "visual_broken": Noul(
            instructions="Using the visual_observation field, does the screen show broken "
                         "images, missing images, or obvious rendering artifacts?"),
        "visual_text_cut": Noul(
            instructions="Using the visual_observation field, does any text appear visually "
                         "cut off, clipped, or truncated?"),
    }
```

- [ ] **Step 5: Viết jev/client.py**

`src/jev_ui_agent/jev/client.py`:
```python
from __future__ import annotations

import time
from typing import Any

from typesafe_sdk import TypeSafeClient

DEFAULT_MODEL = "jev-latest"


class JevError(RuntimeError):
    pass


class JevClient:
    """Wrap TypeSafeClient: retry, parse answers về dict phẳng, tích lũy usage."""

    def __init__(self, model: str = DEFAULT_MODEL, retries: int = 2, backoff: float = 0.5):
        self._client = TypeSafeClient()  # đọc TYPESAFE_API_KEY từ env
        self.model = model
        self.retries = retries
        self._backoff = backoff
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def judge(self, state: Any, questions: dict) -> dict[str, dict]:
        """Trả {key: {"value": float|str, "confidence": float|None, "probabilities": dict}}."""
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                try:
                    resp = self._client.system_one(state=state, questions=questions,
                                                   model=self.model)
                except TypeError:
                    # SDK cũ không nhận kwarg model
                    resp = self._client.system_one(state=state, questions=questions)
                self.usage["calls"] += 1
                self._absorb_usage(resp)
                return self._parse_answers(resp)
            except Exception as e:  # noqa: BLE001 — layer boundary
                last_err = e
                self._sleep(self._backoff * (attempt + 1))
        raise JevError(str(last_err))

    def _absorb_usage(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return

        def g(k: str) -> int:
            v = getattr(u, k, None)
            if v is None and isinstance(u, dict):
                v = u.get(k, 0)
            return int(v or 0)

        self.usage["input_tokens"] += g("input_tokens")
        self.usage["output_tokens"] += g("output_tokens")

    def _parse_answers(self, resp: Any) -> dict[str, dict]:
        out: dict[str, dict] = {}
        answers = getattr(resp, "answers", None) or {}
        try:
            items = answers.items()
        except AttributeError:
            items = [(a.get("key"), a) for a in answers if isinstance(a, dict)]
        for key, ans in items:
            entry: dict = {"value": None, "confidence": None, "probabilities": {}}
            for attr in ("noul", "score", "choice"):
                if getattr(ans, attr, None) is not None:
                    entry["value"] = getattr(ans, attr)
                    break
            entry["confidence"] = getattr(ans, "confidence", None)
            probs = getattr(ans, "probabilities", None)
            if isinstance(probs, dict):
                entry["probabilities"] = {str(k): float(v) for k, v in probs.items()}
            out[str(key)] = entry
        return out
```

- [ ] **Step 6: Run — expect PASS**

Run: `uv run pytest tests/test_jev_client.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/jev_ui_agent/jev/ scripts/verify_typesafe_sdk.py tests/test_jev_client.py
git commit -m "feat: jev client wrapper and question bank"
```

---

### Task 7: Composite scoring + confidence gate

**Files:**
- Create: `src/jev_ui_agent/checks/composite.py`
- Test: `tests/test_composite.py`

- [ ] **Step 1: Viết test trước**

`tests/test_composite.py`:
```python
from jev_ui_agent.checks.composite import VERDICT_VALUE, apply_confidence_gate, score_checkpoint
from jev_ui_agent.models import CheckResult, Verdict


def r(group, verdict):
    return CheckResult(f"c-{group}", group, "rule", verdict)


def test_score_weighted_average():
    results = [r("functional", Verdict.PASS),          # 1.0
               r("layout", Verdict.FAIL),               # 0.0
               r("layout", Verdict.PASS),               # layout mean = 0.5
               r("visual", Verdict.NEEDS_REVIEW)]       # 0.5
    weights = {"functional": 0.35, "layout": 0.20, "visual": 0.10}
    # (0.35*1.0 + 0.20*0.5 + 0.10*0.5) / 0.65 = 0.6/0.65... tính: num=0.35+0.10+0.05=0.50
    assert score_checkpoint(results, weights) == round(0.50 / 0.65, 4)


def test_score_ignores_error_and_skipped():
    results = [r("functional", Verdict.PASS), r("functional", Verdict.ERROR),
               r("visual", Verdict.SKIPPED)]
    assert score_checkpoint(results, {"functional": 0.35, "visual": 0.10}) == 1.0


def test_score_none_when_no_scorable():
    assert score_checkpoint([r("visual", Verdict.SKIPPED)], {"visual": 0.1}) is None


def test_gate_flips_low_confidence():
    res = CheckResult("c", "visual", "vision+jev", Verdict.FAIL, confidence=0.6)
    gated = apply_confidence_gate(res, gate=0.75)
    assert gated.verdict is Verdict.NEEDS_REVIEW
    assert gated.evidence["pre_gate_verdict"] == "fail"


def test_gate_keeps_high_confidence():
    res = CheckResult("c", "visual", "jev", Verdict.PASS, confidence=0.9)
    assert apply_confidence_gate(res, 0.75).verdict is Verdict.PASS


def test_gate_ignores_none_confidence():
    res = CheckResult("c", "content_quality", "jev", Verdict.PASS, confidence=None)
    assert apply_confidence_gate(res, 0.75).verdict is Verdict.PASS


def test_verdict_value_map():
    assert VERDICT_VALUE[Verdict.NEEDS_REVIEW] == 0.5
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_composite.py -v`
Expected: `ModuleNotFoundError: ... checks.composite`

- [ ] **Step 3: Viết checks/composite.py**

`src/jev_ui_agent/checks/composite.py`:
```python
from __future__ import annotations

from jev_ui_agent.models import CheckResult, Verdict

# Giá trị chuẩn hóa khi tính điểm (error/skipped bị loại khỏi phép tính)
VERDICT_VALUE = {Verdict.PASS: 1.0, Verdict.FAIL: 0.0, Verdict.NEEDS_REVIEW: 0.5}


def score_checkpoint(results: list[CheckResult], weights: dict[str, float]) -> float | None:
    """Điểm tổng checkpoint = trung bình trọng số theo nhóm check (pattern composite scoring)."""
    acc, total = 0.0, 0.0
    for group, weight in weights.items():
        values = [VERDICT_VALUE[r.verdict] for r in results
                  if r.group == group and r.verdict in VERDICT_VALUE]
        if not values:
            continue
        acc += weight * (sum(values) / len(values))
        total += weight
    return round(acc / total, 4) if total > 0 else None


def apply_confidence_gate(result: CheckResult, gate: float) -> CheckResult:
    """Confidence dưới ngưỡng → needs_human_review, giữ verdict gốc trong evidence."""
    if result.confidence is not None and result.confidence < gate:
        result.evidence["pre_gate_verdict"] = result.verdict.value
        result.verdict = Verdict.NEEDS_REVIEW
    return result
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_composite.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jev_ui_agent/checks/composite.py tests/test_composite.py
git commit -m "feat: composite scoring and confidence gate"
```

---

### Task 8: Vision bridge (Claude Haiku)

**Files:**
- Create: `src/jev_ui_agent/vision/__init__.py` (rỗng), `src/jev_ui_agent/vision/claude_bridge.py`
- Test: `tests/test_vision.py`

- [ ] **Step 1: Viết test trước (mock anthropic.Anthropic)**

`tests/test_vision.py`:
```python
from types import SimpleNamespace

import pytest

import jev_ui_agent.vision.claude_bridge as bridge_mod
from jev_ui_agent.vision.claude_bridge import VisionBridge, VisionUnavailable, _extract_json


def _msg(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_extract_json_plain_and_fenced():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('blah ```json\n{"a": 2}\n``` trailing') == {"a": 2}


def test_observe_parses_json(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")

    fake_client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: _msg('```json\n{"blank_areas": "none", "broken_images": "none",'
                                 ' "text_cut": "none", "summary": "ok"}\n```')))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge()
    obs = vb.observe(str(img))
    assert obs["summary"] == "ok"
    assert vb.calls == 1


def test_observe_retries_then_unavailable(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG fake")
    calls = {"n": 0}

    def boom(**kw):
        calls["n"] += 1
        raise RuntimeError("api down")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge(retries=1)
    with pytest.raises(VisionUnavailable):
        vb.observe(str(img))
    assert calls["n"] == 2
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_vision.py -v`
Expected: `ModuleNotFoundError: ... vision.claude_bridge`

- [ ] **Step 3: Viết vision/claude_bridge.py**

`src/jev_ui_agent/vision/claude_bridge.py`:
```python
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

from anthropic import Anthropic

# Model id pin — tham khảo claude-api skill khi nâng cấp
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

OBSERVE_PROMPT = (
    "You are a mobile UI test observer. Look at the screenshot and report ONLY what is "
    "visually verifiable. Be terse and factual, no speculation. "
    "Return a single JSON object with exactly these keys: "
    '"blank_areas": description of large blank/unrendered areas or "none", '
    '"broken_images": description of broken/missing images or rendering artifacts or "none", '
    '"text_cut": description of any text that appears clipped/truncated or "none", '
    '"summary": one-sentence overall visual summary.'
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class VisionUnavailable(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    m = _FENCE_RE.search(text)
    return json.loads(m.group(1) if m else text)


class VisionBridge:
    """Gọi Claude Haiverse trả observation JSON có cấu trúc cho JEV phán xét."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL,
                 retries: int = 1, max_tokens: int = 1024):
        self._client = Anthropic(api_key=api_key)  # đọc ANTHROPIC_API_KEY từ env
        self.model = model
        self.retries = retries
        self.max_tokens = max_tokens
        self.calls = 0

    def observe(self, image_path: str) -> dict:
        data = base64.b64encode(Path(image_path).read_bytes()).decode()
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self.calls += 1
                msg = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image",
                             "source": {"type": "base64", "media_type": "image/png",
                                        "data": data}},
                            {"type": "text", "text": OBSERVE_PROMPT},
                        ],
                    }],
                )
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
                return _extract_json(text)
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        raise VisionUnavailable(str(last_err))
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_vision.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jev_ui_agent/vision/ tests/test_vision.py
git commit -m "feat: claude vision bridge with structured observation"
```

---

### Task 9: Check router

**Files:**
- Create: `src/jev_ui_agent/checks/router.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Viết test trước (FakeJev + FakeVision)**

`tests/test_router.py`:
```python
import pytest

from jev_ui_agent.checks.router import run_checks
from jev_ui_agent.jev.client import JevError
from jev_ui_agent.models import Bounds, ScreenState, UIElement, Verdict
from jev_ui_agent.vision.claude_bridge import VisionUnavailable

POLICY = {
    "confidence_gate": 0.75,
    "check_toggles": {"functional": True, "layout": True, "content_quality": True,
                      "error_anomaly": True, "visual": True},
    "layout": {"overlap_min_ratio": 0.1, "offscreen_tolerance_px": 2,
               "truncation_char_width_ratio": 0.025},
    "content_quality": {"typo_pass_score": 0.75},
}


def make_state():
    return ScreenState(run_id="r", checkpoint="home", platform="android", app="a",
                       viewport={"width": 1080, "height": 2400},
                       elements=[UIElement(id="com.a:id/t", text="login.title",
                                           bounds=Bounds(0, 0, 200, 50))],
                       screenshot="shot.png")


class FakeJev:
    def __init__(self, answers=None, error=None):
        self.answers = answers or {}
        self.error = error
        self.states = []

    def judge(self, state, questions):
        if self.error:
            raise JevError(self.error)
        self.states.append(state)
        return self.answers


class FakeVision:
    def __init__(self, observation=None, error=None):
        self.observation = observation or {"blank_areas": "none", "broken_images": "none",
                                           "text_cut": "none", "summary": "ok"}
        self.error = error
        self.calls = 0

    def observe(self, path):
        self.calls += 1
        if self.error:
            raise VisionUnavailable(self.error)
        return self.observation


def core_answers(noul=0.0, choice="normal", score=4.0, conf=0.95):
    return {
        "screen_class": {"value": choice, "confidence": conf,
                         "probabilities": {"normal": 1.0}},
        "has_raw_i18n_key": {"value": noul, "confidence": conf, "probabilities": {}},
        "has_dev_text": {"value": 0.0, "confidence": conf, "probabilities": {}},
        "typo_severity": {"value": score, "confidence": conf, "probabilities": {}},
    }


def test_rule_groups_run_without_jev():
    results = run_checks(make_state(), POLICY, jev=None, vision=None)
    ids = {r.check_id for r in results}
    assert "layout/overlap" in ids
    # các nhóm jev/vision đánh dấu skipped khi thiếu client
    assert all(r.verdict is Verdict.SKIPPED for r in results if r.path in ("jev", "vision+jev"))


def test_jev_i18n_bug_detected():
    jev = FakeJev(answers=core_answers(noul=0.9))  # i18n key gần chắc chắn
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "content_quality/raw_i18n_key")
    assert r.verdict is Verdict.FAIL
    assert r.evidence["noul"] == 0.9


def test_jev_error_screen_classified():
    jev = FakeJev(answers=core_answers(choice="error_screen"))
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "error_anomaly/screen_class")
    assert r.verdict is Verdict.FAIL
    assert r.evidence["classified"] == "error_screen"


def test_confidence_gate_flips_to_needs_review():
    jev = FakeJev(answers=core_answers(noul=0.9, conf=0.5))
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "content_quality/raw_i18n_key")
    assert r.verdict is Verdict.NEEDS_REVIEW
    assert r.evidence["pre_gate_verdict"] == "fail"


def test_typo_score_normalized():
    jev = FakeJev(answers=core_answers(score=3.0))  # 3/4 = 0.75 → pass ở ngưỡng 0.75
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    r = next(r for r in results if r.check_id == "content_quality/typo")
    assert r.verdict is Verdict.PASS and r.score == 0.75


def test_visual_path_with_observation():
    jev = FakeJev(answers={
        "visual_blank": {"value": 0.9, "confidence": 0.95, "probabilities": {}},
        "visual_broken": {"value": 0.0, "confidence": 0.95, "probabilities": {}},
        "visual_text_cut": {"value": 0.0, "confidence": 0.95, "probabilities": {}},
    })
    vision = FakeVision()
    results = run_checks(make_state(), POLICY, jev=jev, vision=vision)
    assert vision.calls == 1
    r = next(r for r in results if r.check_id == "visual/blank")
    assert r.verdict is Verdict.FAIL and r.path == "vision+jev"
    # state thứ 2 (visual) phải chứa visual_observation
    assert "visual_observation" in jev.states[1]


def test_visual_unavailable_marks_skipped():
    jev = FakeJev(answers={})
    vision = FakeVision(error="api down")
    results = run_checks(make_state(), POLICY, jev=jev, vision=vision)
    vis = [r for r in results if r.group == "visual"]
    assert vis and all(r.verdict is Verdict.SKIPPED for r in vis)


def test_jev_error_marks_error():
    jev = FakeJev(error="api down")
    results = run_checks(make_state(), POLICY, jev=jev, vision=None)
    errs = [r for r in results if r.verdict is Verdict.ERROR]
    assert errs and all(r.path == "jev" for r in errs)


def test_toggles_disable_groups():
    policy = dict(POLICY, check_toggles={"functional": False, "layout": False,
                                         "content_quality": True, "error_anomaly": True,
                                         "visual": False})
    results = run_checks(make_state(), policy, jev=FakeJev(answers=core_answers()),
                         vision=FakeVision())
    assert results, "jev groups vẫn chạy"
    assert all(r.group in ("content_quality", "error_anomaly") for r in results)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_router.py -v`
Expected: `ModuleNotFoundError: ... checks.router`

- [ ] **Step 3: Viết checks/router.py**

`src/jev_ui_agent/checks/router.py`:
```python
from __future__ import annotations

from jev_ui_agent.checks.composite import apply_confidence_gate
from jev_ui_agent.checks.rules import functional_checks, layout_checks
from jev_ui_agent.jev.client import JevClient, JevError
from jev_ui_agent.jev.questions import core_questions, visual_questions
from jev_ui_agent.models import CheckResult, ScreenState, Verdict
from jev_ui_agent.vision.claude_bridge import VisionBridge, VisionUnavailable

_JEV_GROUP_BY_KEY = {
    "screen_class": "error_anomaly",
    "has_raw_i18n_key": "content_quality",
    "has_dev_text": "content_quality",
    "typo_severity": "content_quality",
}
_JEV_CHECK_ID = {
    "screen_class": "error_anomaly/screen_class",
    "has_raw_i18n_key": "content_quality/raw_i18n_key",
    "has_dev_text": "content_quality/dev_text",
    "typo_severity": "content_quality/typo",
}
_VISUAL_IDS = ["visual/blank", "visual/broken_images", "visual/text_cut"]


def _state_payload(state: ScreenState) -> dict:
    return {
        "checkpoint": state.checkpoint,
        "platform": state.platform,
        "app": state.app,
        "viewport": state.viewport,
        "elements": [
            {
                "id": e.id, "type": e.type, "label": e.label, "text": e.text,
                "content_desc": e.content_desc,
                "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                "clickable": e.clickable,
            }
            for e in state.elements
        ],
    }


def _noul_result(check_id: str, group: str, path: str, ans: dict, gate: float,
                 threshold: float = 0.5) -> CheckResult:
    bad = (ans.get("value") or 0.0) >= threshold
    r = CheckResult(check_id, group, path, Verdict.FAIL if bad else Verdict.PASS,
                    confidence=ans.get("confidence"), evidence={"noul": ans.get("value")})
    return apply_confidence_gate(r, gate)


def _jev_checks(state: ScreenState, policy: dict, jev: JevClient) -> list[CheckResult]:
    gate = float(policy.get("confidence_gate", 0.75))
    toggles = policy.get("check_toggles", {})
    questions = core_questions(content_quality=toggles.get("content_quality", True),
                               error_anomaly=toggles.get("error_anomaly", True))
    if not questions:
        return []
    try:
        answers = jev.judge(_state_payload(state), questions)
    except JevError as e:
        return [CheckResult(_JEV_CHECK_ID[k], _JEV_GROUP_BY_KEY[k], "jev", Verdict.ERROR,
                            error=str(e))
                for k in questions if k in _JEV_CHECK_ID]

    out: list[CheckResult] = []
    if "screen_class" in answers:
        a = answers["screen_class"]
        verdict = Verdict.PASS if a["value"] == "normal" else Verdict.FAIL
        r = CheckResult(_JEV_CHECK_ID["screen_class"], "error_anomaly", "jev", verdict,
                        score=a["probabilities"].get("normal"),
                        confidence=a["confidence"], probabilities=a["probabilities"],
                        evidence={"classified": a["value"]})
        out.append(apply_confidence_gate(r, gate))
    if "has_raw_i18n_key" in answers:
        out.append(_noul_result(_JEV_CHECK_ID["has_raw_i18n_key"], "content_quality", "jev",
                                answers["has_raw_i18n_key"], gate))
    if "has_dev_text" in answers:
        out.append(_noul_result(_JEV_CHECK_ID["has_dev_text"], "content_quality", "jev",
                                answers["has_dev_text"], gate))
    if "typo_severity" in answers:
        a = answers["typo_severity"]
        norm = (a["value"] or 0.0) / 4.0
        threshold = float(policy.get("content_quality", {}).get("typo_pass_score", 0.75))
        r = CheckResult(_JEV_CHECK_ID["typo_severity"], "content_quality", "jev",
                        Verdict.PASS if norm >= threshold else Verdict.FAIL,
                        score=norm, confidence=a["confidence"],
                        evidence={"raw_score": a["value"], "threshold": threshold})
        out.append(apply_confidence_gate(r, gate))
    return out


def _visual_checks(state: ScreenState, policy: dict, jev: JevClient,
                   vision: VisionBridge) -> list[CheckResult]:
    gate = float(policy.get("confidence_gate", 0.75))
    try:
        observation = vision.observe(state.screenshot)
    except VisionUnavailable as e:
        return [CheckResult(i, "visual", "vision+jev", Verdict.SKIPPED, error=str(e))
                for i in _VISUAL_IDS]
    payload = {"screen": _state_payload(state), "visual_observation": observation}
    try:
        answers = jev.judge(payload, visual_questions())
    except JevError as e:
        return [CheckResult(i, "visual", "vision+jev", Verdict.ERROR, error=str(e))
                for i in _VISUAL_IDS]
    return [
        _noul_result("visual/blank", "visual", "vision+jev", answers["visual_blank"], gate),
        _noul_result("visual/broken_images", "visual", "vision+jev",
                     answers["visual_broken"], gate),
        _noul_result("visual/text_cut", "visual", "vision+jev",
                     answers["visual_text_cut"], gate),
    ]


def run_checks(state: ScreenState, policy: dict, jev: JevClient | None,
               vision: VisionBridge | None) -> list[CheckResult]:
    """Routing theo nguyên tắc: rule rẻ nhất → JEV trực tiếp → vision+JEV."""
    toggles = policy.get("check_toggles", {})
    results: list[CheckResult] = []

    if toggles.get("functional", True):
        results += functional_checks(state, policy)
    if toggles.get("layout", True):
        results += layout_checks(state, policy)

    jev_groups = [g for g in ("content_quality", "error_anomaly")
                  if toggles.get(g, True)]
    if jev_groups:
        if jev is None:
            results += [CheckResult(_JEV_CHECK_ID[k], _JEV_GROUP_BY_KEY[k], "jev",
                                    Verdict.SKIPPED, error="jev client unavailable")
                        for k in _JEV_CHECK_ID
                        if _JEV_GROUP_BY_KEY[k] in jev_groups]
        else:
            results += _jev_checks(state, policy, jev)

    if toggles.get("visual", True):
        if jev is None or vision is None:
            results += [CheckResult(i, "visual", "vision+jev", Verdict.SKIPPED,
                                    error="jev/vision client unavailable")
                        for i in _VISUAL_IDS]
        else:
            results += _visual_checks(state, policy, jev, vision)
    return results
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_router.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jev_ui_agent/checks/router.py tests/test_router.py
git commit -m "feat: check router with rule/jev/vision paths and confidence gating"
```

---

### Task 10: Report renderers (JSON + HTML)

**Files:**
- Create: `src/jev_ui_agent/report/__init__.py` (rỗng), `src/jev_ui_agent/report/json_report.py`, `src/jev_ui_agent/report/html.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Viết test trước**

`tests/test_report.py`:
```python
import json

from jev_ui_agent.models import CheckpointReport, CheckResult, RunReport, Verdict
from jev_ui_agent.report.html import render_html
from jev_ui_agent.report.json_report import render_json


def sample_report() -> RunReport:
    return RunReport(
        run_id="run-1", flow_name="demo", started_at="2026-10-02T10:00:00",
        checkpoints=[
            CheckpointReport(
                checkpoint="home", screen_score=0.8123, screenshot="artifacts/home.png",
                results=[
                    CheckResult("functional/element:res-id:login_btn", "functional",
                                "rule", Verdict.PASS),
                    CheckResult("content_quality/raw_i18n_key", "content_quality", "jev",
                                Verdict.NEEDS_REVIEW, confidence=0.5,
                                evidence={"pre_gate_verdict": "fail"}),
                ]),
        ],
        failed_steps=["tap acc-id:Go"],
        costs={"jev": {"calls": 2, "input_tokens": 800, "output_tokens": 100}},
    )


def test_render_json_roundtrip():
    data = json.loads(render_json(sample_report()))
    assert data["run_id"] == "run-1"
    verdicts = [r["verdict"] for r in data["checkpoints"][0]["results"]]
    assert verdicts == ["pass", "needs_review"]  # enum → string value
    assert data["costs"]["jev"]["calls"] == 2


def test_render_html_markers():
    html = render_html(sample_report())
    assert "run-1" in html and "demo" in html
    assert "home" in html
    assert "needs_review" in html
    assert "acc-id:Go" in html          # failed step hiển thị
    assert 'src="artifacts/home.png"' in html
    assert "0.8123" in html
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_report.py -v`
Expected: `ModuleNotFoundError: ... report.json_report`

- [ ] **Step 3: Viết report/json_report.py**

`src/jev_ui_agent/report/json_report.py`:
```python
from __future__ import annotations

import dataclasses
import json
from typing import Any

from jev_ui_agent.models import RunReport, Verdict


def _default(o: Any) -> str:
    if isinstance(o, Verdict):
        return o.value
    return str(o)


def render_json(report: RunReport) -> str:
    return json.dumps(dataclasses.asdict(report), default=_default,
                      indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Viết report/html.py**

`src/jev_ui_agent/report/html.py`:
```python
from __future__ import annotations

from jinja2 import Environment

from jev_ui_agent.models import RunReport, Verdict

_BADGES = {
    Verdict.PASS: "badge pass", Verdict.FAIL: "badge fail",
    Verdict.NEEDS_REVIEW: "badge review", Verdict.ERROR: "badge error",
    Verdict.SKIPPED: "badge skipped",
}

_TEMPLATE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>JEV UI Report {{ report.run_id }}</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #fafafa; }
  h1, h2 { color: #1a1a2e; }
  .meta { color: #555; margin-bottom: 1rem; }
  .card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
          padding: 1rem; margin: 1rem 0; }
  table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee;
           font-size: 0.9rem; }
  .badge { padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; font-weight: 600; }
  .pass { background: #d4edda; color: #155724; }
  .fail { background: #f8d7da; color: #721c24; }
  .review { background: #fff3cd; color: #856404; }
  .error { background: #e2d5f8; color: #4a2a8f; }
  .skipped { background: #e9ecef; color: #495057; }
  img.shot { max-width: 240px; border: 1px solid #ccc; border-radius: 6px; }
  .score { font-size: 1.2rem; font-weight: 700; }
  .failed-steps { color: #721c24; }
</style></head>
<body>
<h1>JEV UI Checking — {{ report.flow_name }}</h1>
<p class="meta">Run <b>{{ report.run_id }}</b> · bắt đầu {{ report.started_at }}
   · {{ report.checkpoints | length }} checkpoint</p>
{% if report.failed_steps %}
<div class="card"><h2>Failed steps</h2>
  <ul class="failed-steps">{% for s in report.failed_steps %}<li>{{ s }}</li>{% endfor %}</ul>
</div>
{% endif %}
{% for cp in report.checkpoints %}
<div class="card">
  <h2>{{ cp.checkpoint }}
    {% if cp.screen_score is not none %}
      <span class="score">· {{ "%.4f" | format(cp.screen_score) }}</span>
    {% endif %}</h2>
  {% if cp.error %}<p class="failed-steps">Lỗi capture: {{ cp.error }}</p>{% endif %}
  {% if cp.screenshot %}<img class="shot" src="{{ cp.screenshot }}" alt="{{ cp.checkpoint }}">{% endif %}
  <table><tr><th>Check</th><th>Nhóm</th><th>Path</th><th>Verdict</th>
    <th>Score</th><th>Confidence</th></tr>
  {% for r in cp.results %}
    <tr><td>{{ r.check_id }}</td><td>{{ r.group }}</td><td>{{ r.path }}</td>
      <td><span class="{{ badges[r.verdict] }}">{{ r.verdict.value }}</span></td>
      <td>{% if r.score is not none %}{{ "%.3f" | format(r.score) }}{% endif %}</td>
      <td>{% if r.confidence is not none %}{{ "%.2f" | format(r.confidence) }}{% endif %}</td></tr>
  {% endfor %}</table>
  <details><summary>Evidence</summary>
    {% for r in cp.results %}
      {% if r.evidence %}<p><b>{{ r.check_id }}</b>: <code>{{ r.evidence }}</code></p>{% endif %}
      {% if r.error %}<p class="failed-steps"><b>{{ r.check_id }}</b>: {{ r.error }}</p>{% endif %}
    {% endfor %}
  </details>
</div>
{% endfor %}
<div class="card"><h2>Chi phí</h2><pre>{{ report.costs | tojson(indent=2) }}</pre></div>
</body></html>
"""

_env = Environment(autoescape=True)


def render_html(report: RunReport) -> str:
    return _env.from_string(_TEMPLATE).render(report=report, badges=_BADGES)
```

- [ ] **Step 5: Run — expect PASS**

Run: `uv run pytest tests/test_report.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/jev_ui_agent/report/ tests/test_report.py
git commit -m "feat: json and html report renderers"
```

---

### Task 11: FakeDriver + pipeline + CLI

**Files:**
- Create: `src/jev_ui_agent/driver/base.py`, `src/jev_ui_agent/driver/fake.py`, `src/jev_ui_agent/driver/__init__.py`
- Create: `src/jev_ui_agent/pipeline.py`, `src/jev_ui_agent/__main__.py`
- Create: `tests/fixtures/policy_test.yaml`, `tests/fixtures/fake_run/home.xml`, `tests/fixtures/fake_run/topics.xml`, `tests/fixtures/fake_run/settings.xml`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Viết driver/base.py**

`src/jev_ui_agent/driver/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod

from jev_ui_agent.models import StepArtifact


class BaseDriver(ABC):
    """Interface chung cho Android/iOS/Fake driver."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def launch(self) -> None: ...

    @abstractmethod
    def tap(self, target: str) -> None: ...

    @abstractmethod
    def input_text(self, target: str, value: str) -> None: ...

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None: ...

    @abstractmethod
    def capture(self, checkpoint: str) -> StepArtifact: ...

    @abstractmethod
    def quit(self) -> None: ...
```

- [ ] **Step 2: Viết driver/fake.py**

`src/jev_ui_agent/driver/fake.py`:
```python
from __future__ import annotations

import base64
from pathlib import Path

from jev_ui_agent.driver.base import BaseDriver
from jev_ui_agent.models import StepArtifact

# PNG 1x1 đỏ — placeholder screenshot cho chế độ fake
_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class FakeDriver(BaseDriver):
    """Driver giả: đọc UI tree từ fixture dir, ghi screenshot placeholder.

    Fixture layout: <fixtures_dir>/<checkpoint>.xml (fallback default.xml).
    """

    def __init__(self, fixtures_dir: Path | str, out_dir: Path):
        self.fixtures_dir = Path(fixtures_dir)
        self.out_dir = Path(out_dir)
        (self.out_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    def connect(self) -> None: ...

    def launch(self) -> None: ...

    def tap(self, target: str) -> None: ...

    def input_text(self, target: str, value: str) -> None: ...

    def swipe(self, x1, y1, x2, y2, duration_ms: int = 500) -> None: ...

    def capture(self, checkpoint: str) -> StepArtifact:
        xml_path = self.fixtures_dir / f"{checkpoint}.xml"
        if not xml_path.exists():
            xml_path = self.fixtures_dir / "default.xml"
        if not xml_path.exists():
            raise FileNotFoundError(f"Không có fixture cho checkpoint {checkpoint!r}")
        png = self.out_dir / "artifacts" / f"{checkpoint}.png"
        png.write_bytes(base64.b64decode(_PNG_B64))
        return StepArtifact(checkpoint=checkpoint, screenshot_path=str(png),
                            source_xml=xml_path.read_text(encoding="utf-8"),
                            activity="com.example.FakeActivity")

    def quit(self) -> None: ...
```

- [ ] **Step 3: Tạo fixtures cho integration test**

Copy `tests/fixtures/android_home.xml` → `tests/fixtures/fake_run/home.xml`, và tạo 2 file còn lại tương tự (thay nội dung node text/resource-id tùy ý, giữ cấu trúc hierarchy — minimum 1 TextView + 1 Button).

`tests/fixtures/policy_test.yaml`:
```yaml
confidence_gate: 0.75
weights: {functional: 0.35, layout: 0.20, content_quality: 0.15, error_anomaly: 0.20, visual: 0.10}
check_toggles: {functional: true, layout: true, content_quality: true, error_anomaly: true, visual: true}
functional_expectations:
  - checkpoint: home
    element: "res-id:login_btn"
    expect_text: "Sign in"
layout:
  overlap_min_ratio: 0.10
  offscreen_tolerance_px: 2
  truncation_char_width_ratio: 0.025
content_quality:
  typo_pass_score: 0.75
vision:
  model: claude-haiku-4-5-20251001
  max_calls_per_checkpoint: 1
```

- [ ] **Step 4: Viết test pipeline trước**

`tests/test_pipeline.py`:
```python
import json
from pathlib import Path

import yaml

from jev_ui_agent.driver.fake import FakeDriver
from jev_ui_agent.pipeline import run_flow

FIX = Path(__file__).parent / "fixtures"


def _flow(tmp_path: Path) -> Path:
    flow = {"name": "demo", "app": "com.example", "platform": "android", "steps": [
        {"action": "launch"},
        {"checkpoint": "home"},
        {"checkpoint": "topics"},
        {"checkpoint": "settings"},
    ]}
    p = tmp_path / "flow.yaml"
    p.write_text(yaml.safe_dump(flow), encoding="utf-8")
    return p


def test_fake_run_writes_reports(tmp_path):
    report = run_flow(
        flow_path=_flow(tmp_path), policy_path=FIX / "policy_test.yaml",
        devices_path=Path("config/devices.yaml"), driver_kind="fake",
        out_root=tmp_path / "reports", fixtures_dir=FIX / "fake_run",
        jev=None, vision=None,
    )
    assert [c.checkpoint for c in report.checkpoints] == ["home", "topics", "settings"]
    assert all(c.error == "" for c in report.checkpoints)
    assert all(c.screen_score is not None for c in report.checkpoints)  # rule groups chấm được
    run_dir = tmp_path / "reports" / report.run_id
    assert (run_dir / "report.json").exists() and (run_dir / "report.html").exists()
    data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert data["run_id"] == report.run_id


def test_missing_fixture_records_error(tmp_path):
    flow = {"name": "demo", "app": "com.example", "platform": "android", "steps": [
        {"checkpoint": "nonexistent"}]}
    p = tmp_path / "flow.yaml"
    p.write_text(yaml.safe_dump(flow), encoding="utf-8")
    report = run_flow(flow_path=p, policy_path=FIX / "policy_test.yaml",
                      devices_path=Path("config/devices.yaml"), driver_kind="fake",
                      out_root=tmp_path / "reports", fixtures_dir=FIX / "fake_run",
                      jev=None, vision=None)
    assert report.checkpoints[0].error != ""       # capture lỗi được ghi lại
    assert report.checkpoints[0].results == []      # nhưng pipeline không chết


def test_try_action_retries_then_records(tmp_path):
    from jev_ui_agent.pipeline import _try_action

    class Flaky:
        def __init__(self):
            self.n = 0

        def tap(self, target):
            self.n += 1
            if self.n < 2:
                raise RuntimeError("flaky")
            return None

    assert _try_action(Flaky(), {"action": "tap", "target": "x"}) is True

    class Dead:
        def tap(self, target):
            raise RuntimeError("dead")

    assert _try_action(Dead(), {"action": "tap", "target": "x"}) is False
```

- [ ] **Step 5: Run — expect FAIL**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: `ModuleNotFoundError: ... pipeline`

- [ ] **Step 6: Viết pipeline.py**

`src/jev_ui_agent/pipeline.py`:
```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from jev_ui_agent.checks.composite import score_checkpoint
from jev_ui_agent.checks.router import run_checks
from jev_ui_agent.driver.base import BaseDriver
from jev_ui_agent.extract.normalize import build_state
from jev_ui_agent.flows import load_flow
from jev_ui_agent.jev.client import JevClient
from jev_ui_agent.models import CheckpointReport, RunReport
from jev_ui_agent.report.html import render_html
from jev_ui_agent.report.json_report import render_json
from jev_ui_agent.vision.claude_bridge import VisionBridge


def load_yaml(path: Path | str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def make_driver(driver_kind: str, device_cfg: dict, out_dir: Path,
                fixtures_dir: Path | None) -> BaseDriver:
    if driver_kind == "fake":
        from jev_ui_agent.driver.fake import FakeDriver
        return FakeDriver(fixtures_dir or Path("tests/fixtures/fake_run"), out_dir)
    if driver_kind == "android":
        from jev_ui_agent.driver.android import AndroidDriver
        return AndroidDriver(device_cfg, out_dir)
    raise ValueError(f"Unknown driver kind: {driver_kind!r}")


def _do_action(driver: BaseDriver, step: dict) -> None:
    action = step["action"]
    if action == "launch":
        driver.launch()
    elif action == "tap":
        driver.tap(step["target"])
    elif action == "input":
        driver.input_text(step["target"], step["value"])
    elif action == "swipe":
        driver.swipe(int(step["x1"]), int(step["y1"]), int(step["x2"]), int(step["y2"]),
                     int(step.get("duration", 500)))


def _try_action(driver: BaseDriver, step: dict, retries: int = 1) -> bool:
    for _ in range(retries + 1):
        try:
            _do_action(driver, step)
            return True
        except Exception:  # noqa: BLE001 — action failure là dữ liệu, không phải crash
            continue
    return False


def run_flow(*, flow_path: Path | str, policy_path: Path | str,
             devices_path: Path | str, driver_kind: str, out_root: Path | str,
             fixtures_dir: Path | None = None, jev: JevClient | None = None,
             vision: VisionBridge | None = None) -> RunReport:
    flow = load_flow(flow_path)
    policy = load_yaml(policy_path)
    devices = load_yaml(devices_path)

    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = Path(out_root) / run_id
    (out_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    platform = flow.get("platform", "android")
    device_cfg = devices.get(platform)
    if device_cfg is None:
        raise ValueError(f"devices.yaml không có cấu hình cho platform {platform!r}")

    driver = make_driver(driver_kind, device_cfg, out_dir, fixtures_dir)
    driver.connect()

    report = RunReport(run_id=run_id, flow_name=flow["name"],
                       started_at=datetime.now().isoformat(timespec="seconds"))

    try:
        for step in flow["steps"]:
            if step["kind"] == "checkpoint":
                cp = CheckpointReport(checkpoint=step["name"])
                try:
                    artifact = driver.capture(step["name"])
                    state = build_state(artifact, run_id=run_id, platform=platform,
                                        app=flow["app"], viewport=device_cfg["viewport"])
                except Exception as e:  # noqa: BLE001 — bao gồm ET.ParseError từ page_source hỏng
                    cp.error = str(e)
                    report.checkpoints.append(cp)
                    continue
                cp.screenshot = state.screenshot
                cp.results = run_checks(state, policy, jev, vision)
                cp.screen_score = score_checkpoint(cp.results, policy.get("weights", {}))
                report.checkpoints.append(cp)
            else:
                if not _try_action(driver, step):
                    report.failed_steps.append(
                        f"{step['action']} {step.get('target', '')}".strip())
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass

    if jev is not None:
        report.costs["jev"] = dict(jev.usage)
    if vision is not None:
        report.costs["vision"] = {"calls": vision.calls}

    (out_dir / "report.json").write_text(render_json(report), encoding="utf-8")
    (out_dir / "report.html").write_text(render_html(report), encoding="utf-8")
    return report
```

- [ ] **Step 7: Viết __main__.py (CLI)**

`src/jev_ui_agent/__main__.py`:
```python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from jev_ui_agent.jev.client import JevClient
from jev_ui_agent.pipeline import run_flow
from jev_ui_agent.vision.claude_bridge import VisionBridge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jev-ui-agent",
                                     description="JEV mobile UI checking agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="Chạy một flow test")
    run_p.add_argument("--flow", required=True)
    run_p.add_argument("--driver", choices=["fake", "android"], default="fake")
    run_p.add_argument("--policy", default="config/policy.yaml")
    run_p.add_argument("--devices", default="config/devices.yaml")
    run_p.add_argument("--out", default="reports")
    run_p.add_argument("--fixtures-dir", default="tests/fixtures/fake_run")
    args = parser.parse_args(argv)

    jev = JevClient() if os.environ.get("TYPESAFE_API_KEY") else None
    vision = VisionBridge() if os.environ.get("ANTHROPIC_API_KEY") else None
    report = run_flow(
        flow_path=args.flow, policy_path=args.policy, devices_path=args.devices,
        driver_kind=args.driver, out_root=args.out,
        fixtures_dir=Path(args.fixtures_dir) if args.driver == "fake" else None,
        jev=jev, vision=vision,
    )
    failed = sum(1 for cp in report.checkpoints
                 for r in cp.results if r.verdict.value == "fail")
    print(f"Run {report.run_id}: {len(report.checkpoints)} checkpoints, {failed} failed checks")
    print(f"Report: {Path(args.out) / report.run_id / 'report.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Run toàn bộ test — expect PASS**

Run: `uv run pytest -v`
Expected: all passed (~30 tests).

- [ ] **Step 9: Smoke CLI fake mode** (chưa set API keys → jev=None, vision=None path)

Tạo `tmp_demo_flow.yaml` ở project root:
```yaml
name: demo
app: com.example
platform: android
steps:
  - action: launch
  - checkpoint: home
  - checkpoint: topics
  - checkpoint: settings
```

```bash
uv run python -m jev_ui_agent run --flow tmp_demo_flow.yaml --driver fake
```
Expected: in ra `Run run-YYYYMMDD-HHMMSS: 3 checkpoints, ...` và file `reports/run-*/report.html` mở được bằng browser. Xong xóa `tmp_demo_flow.yaml`.

- [ ] **Step 10: Commit**

```bash
git add src/jev_ui_agent/driver/ src/jev_ui_agent/pipeline.py src/jev_ui_agent/__main__.py tests/test_pipeline.py tests/fixtures/policy_test.yaml tests/fixtures/fake_run/
git commit -m "feat: pipeline orchestrator, fake driver, and cli"
```

---

### Task 12: Android driver (Appium)

**Files:**
- Create: `src/jev_ui_agent/driver/android.py`
- Test: `tests/test_android_driver_selectors.py`

Driver thật cần emulator nên chỉ unit-test phần pure (mapping selector → AppiumBy). Phần còn lại kiểm tra thủ công ở Task 13.

- [ ] **Step 1: Viết test phần pure trước**

`tests/test_android_driver_selectors.py`:
```python
from jev_ui_agent.driver.android import to_appium_locator


def test_to_appium_locator():
    from appium.webdriver.common.appiumby import AppiumBy
    assert to_appium_locator("res-id:login_btn") == (AppiumBy.ID, "login_btn")
    assert to_appium_locator("acc-id:Sign in") == (AppiumBy.ACCESSIBILITY_ID, "Sign in")
    assert to_appium_locator("xpath://x/y") == (AppiumBy.XPATH, "//x/y")
    kind, value = to_appium_locator("text:For You")
    assert kind == AppiumBy.XPATH
    assert "For You" in value and value.startswith("//*[@")
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_android_driver_selectors.py -v`
Expected: `ModuleNotFoundError: ... driver.android`

- [ ] **Step 3: Viết driver/android.py**

`src/jev_ui_agent/driver/android.py`:
```python
from __future__ import annotations

from pathlib import Path

from appium import webdriver as appium_webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

from jev_ui_agent.driver.base import BaseDriver
from jev_ui_agent.driver.selectors import parse
from jev_ui_agent.models import StepArtifact

_BY = {
    "id": AppiumBy.ID,
    "acc": AppiumBy.ACCESSIBILITY_ID,
    "text": AppiumBy.XPATH,
    "xpath": AppiumBy.XPATH,
}


def to_appium_locator(selector: str) -> tuple[str, str]:
    """Pure mapping 'res-id:x' → (AppiumBy.ID, 'x'). Text → xpath theo @text."""
    kind, value = parse(selector)
    if kind == "text":
        return AppiumBy.XPATH, f"//*[@text='{value}']"
    return _BY[kind], value


class AndroidDriver(BaseDriver):
    def __init__(self, device_cfg: dict, out_dir: Path,
                 server_url: str = "http://127.0.0.1:4723"):
        self.out_dir = Path(out_dir)
        (self.out_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        opts = UiAutomator2Options()
        for key, value in device_cfg.get("capabilities", {}).items():
            opts.set_capability(key, value)
        self._d = appium_webdriver.Remote(server_url, options=opts)

    def connect(self) -> None: ...  # session được tạo trong __init__

    def launch(self) -> None: ...  # appium tự launch app theo capability "app"

    def _find(self, selector: str):
        by, value = to_appium_locator(selector)
        return self._d.find_element(by, value)

    def tap(self, target: str) -> None:
        self._find(target).click()

    def input_text(self, target: str, value: str) -> None:
        self._find(target).send_keys(value)

    def swipe(self, x1, y1, x2, y2, duration_ms: int = 500) -> None:
        self._d.swipe(x1, y1, x2, y2, duration_ms)

    def capture(self, checkpoint: str) -> StepArtifact:
        png = self.out_dir / "artifacts" / f"{checkpoint}.png"
        self._d.get_screenshot_as_file(str(png))
        try:
            activity = self._d.current_activity
        except Exception:  # noqa: BLE001
            activity = ""
        return StepArtifact(checkpoint=checkpoint, screenshot_path=str(png),
                            source_xml=self._d.page_source, activity=activity)

    def quit(self) -> None:
        self._d.quit()
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_android_driver_selectors.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jev_ui_agent/driver/android.py tests/test_android_driver_selectors.py
git commit -m "feat: android appium driver with selector mapping"
```

---

### Task 13: E2E smoke trên Android emulator (runbook)

**Files:**
- Create: `scripts/setup_android.md`
- Modify: `flows/login_smoke.yaml` (tinh chỉnh selector theo app thật)
- Create: `docs/superpowers/e2e/` (sample report)

Task này là thủ công + verification môi trường — không TDD, nhưng mỗi bước có lệnh và expected output.

- [ ] **Step 1: Viết scripts/setup_android.md**

`scripts/setup_android.md`:
```markdown
# Setup môi trường Android E2E (Windows)

## 1. Node.js + Appium server
winget install OpenJS.NodeJS.LTS   (hoặc cài từ nodejs.org)
npm install -g appium
appium driver install uiautomator
appium driver doctor uiautomator   # kiểm tra thiếu gì thì bổ sung (JAVA_HOME, ANDROID_HOME)

## 2. Java 17 (UiAutomator2 cần)
winget install EclipseAdoptium.Temurin.17.JDK
set JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17... (theo đường dẫn cài thật)

## 3. Android SDK + Emulator
- Cài Android Studio, mở SDK Manager: cài Android SDK Platform 34, Android SDK Platform-Tools, Android Emulator, Android SDK Build-Tools.
- Device Manager: tạo AVD (VD: Pixel 7, API 34).
- Khởi động emulator: mở Android Studio > Device Manager > ▶  (giữ nguyên trong suốt run)

## 4. App mẫu: Now in Android
- Vào https://github.com/android/nowinandroid/releases
- Tải asset APK (nowinandroid.apk) về apps/nowinandroid.apk
- (hoặc) gh release view --repo android/nowinandroid --json assets

## 5. Biến môi trường
export TYPESAFE_API_KEY=<từ console.typesafe.ai/keys>
export ANTHROPIC_API_KEY=<key>

## 6. Chạy
# terminal 1:
appium                                   # start server tại 127.0.0.1:4723
# terminal 2:
uv run python -m jev_ui_agent run --flow flows/login_smoke.yaml --driver android

Expected: in ra "Run run-...: 3 checkpoints, N failed checks" và tạo reports/run-*/report.html
```

- [ ] **Step 2: Cài đặt môi trường theo runbook** (thực hiện từng mục, doctor pass hết)

Run: `appium driver doctor uiautomator && adb devices`
Expected: doctor không còn lỗi đỏ; emulator hiện trong `adb devices`.

- [ ] **Step 3: Verify SDK JEV live**

Run: `uv run python scripts/verify_typesafe_sdk.py` (đã set `TYPESAFE_API_KEY`)
Expected: live ping in ra answers (noul ~1.0 cho câu "sign-in button").

- [ ] **Step 4: Tinh chỉnh selector flow bằng Appium Inspector**

- Cài Appium Inspector (desktop app), kết nối tới server `127.0.0.1:4723` với capabilities như `config/devices.yaml` (mục android).
- Vào từng màn hình của Now in Android, tìm resource-id/content-desc/text thật của các element cần tap/expect.
- Cập nhật `flows/login_smoke.yaml` + `config/policy.yaml` (mục `functional_expectations`) theo selector thật.

- [ ] **Step 5: Chạy E2E smoke**

Run: `uv run python -m jev_ui_agent run --flow flows/login_smoke.yaml --driver android`
Expected: 3 checkpoint (home/topics/settings), report HTML sinh ra, JE.Usage > 0 (JEV được gọi thật), không có exception dừng pipeline.

- [ ] **Step 6: Kiểm tra kết quả & tinh chỉnh câu hỏi nếu false positive**

Mở `reports/run-*/report.html`:
- Mỗi finding FAIL/NEEDS_REVIEW đối chiếu screenshot — nếu sai → sửa `src/jev_ui_agent/jev/questions.py` (câu hỏi cụ thể hơn) hoặc ngưỡng trong `config/policy.yaml`, chạy lại Step 5.
- Ghi chú kết quả tinh chỉnh vào commit message.

- [ ] **Step 7: Lưu sample report làm bằng chứng**

```bash
mkdir -p docs/superpowers/e2e
cp reports/run-*/report.html docs/superpowers/e2e/2026-10-02-sample-report.html
```

- [ ] **Step 8: Commit**

```bash
git add scripts/setup_android.md flows/login_smoke.yaml config/policy.yaml docs/superpowers/e2e/
git commit -m "feat: e2e smoke run on android emulator with tuned selectors"
```

---

## Hardening notes (từ code review các task — ghi nhớ cho task sau / Phase 2)

- **Task 11**: try/except quanh checkpoint đã được mở rộng bao `build_state` (chống ET.ParseError từ page_source hỏng làm mất toàn bộ report).
- **Phase 2 (iOS)**: `_interesting` hiện giữ container có label (Application/Window với tên app) — sẽ gây overlap false-positive trên iOS. Trước khi chạy iOS thật: loại container types hoặc cho layout check bỏ qua cặp ancestor-contained.
- **Phase 2**: `build_state` route mọi platform != "android" sang parse_ios — nên thêm validate platform in {"android","ios"} để fail-fast.
- **Task 13**: nếu state quá lớn bị cap 100 elements, ghi nhận truncation (spec §7 yêu cầu cảnh báo trong report) — hiện chưa có kênh; cân nhắc thêm khi cần.

## Self-Review (đã thực hiện sau khi viết plan)

1. **Spec coverage:**
   - 5 nhóm check → Task 5 (functional/layout rules), Task 6+9 (content_quality, error_anomaly qua JEV), Task 8+9 (visual qua vision+JEV). ✅
   - Hybrid routing "đường rẻ nhất" → Task 9 router. ✅
   - Confidence gate 0.75 → Task 7. ✅
   - Composite scoring + weights trong policy.yaml → Task 7 + Task 1. ✅
   - Report HTML+JSON + cost log → Task 10 + pipeline (Task 11). ✅
   - Error handling từng loại (appium retry, JEV error, vision skip, capture fail) → Task 11 + 8 + 9. ✅
   - App mẫu Now in Android + bug nhân tạo (i18n key trong fixture) → Task 13 + Task 4. ✅
   - iOS: extractor (Task 4) + devices.yaml (Task 1) sẵn; driver ios.py là Phase 2 — khớp non-goals của spec. ✅
2. **Placeholder scan:** không còn "TBD/TODO/implement later" nào; mọi bước code đều có code block đầy đủ, mọi run đều có lệnh + expected output.
3. **Type consistency:** `JevClient.judge(state, questions) -> dict[str, dict]` dùng nhất quán ở Task 9/11; `BaseDriver.input_text` (không phải `input`) nhất quán Task 11/12; `CheckResult(check_id, group, path, verdict, ...)` theo thứ tự positional thống nhất mọi task; `VisionBridge.observe(path) -> dict` + `.calls` thống nhất Task 8/9/11.

## Ghi chú thực thi

- Task 1–12 chạy hoàn toàn offline (mock), Task 13 cần emulator + API keys.
- Nếu SDK `typesafe` thực tế khác mô tả (Task 6 Step 1 sẽ phát hiện): chỉ chỉnh `jev/client.py` và `jev/questions.py`, phần còn lại của hệ thống phụ thuộc interface `judge()` đã mock.
- Attribution cho commit: kết thúc mỗi commit message bằng dòng `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
