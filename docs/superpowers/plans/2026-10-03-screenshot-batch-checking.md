# Screenshot Batch Checking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm mode `check-screenshots`: batch check folder screenshot tĩnh (≥ 2.000 ảnh) theo rules YAML tự định nghĩa (noul pass/fail + score rubric), 1 vision + 1 JEV call/ảnh, dedup hash, song song, resume được.

**Architecture:** Entry point mới song song `run_flow`: scan ảnh → dedup sha256 → ThreadPoolExecutor (vision `observe_detailed` → JEV fan-out mọi rules) → verdict + confidence gate → checkpoint.jsonl (append, resume) → RunReport có `summary` → HTML fail-first + JSON.

**Tech Stack:** như Phase 1 (Python 3.12/uv, typesafe_sdk, anthropic, pytest) + `concurrent.futures`, `hashlib`.

**Spec:** `docs/superpowers/specs/2026-10-03-screenshot-batch-checking-design.md`

---

### Task 1: Rules loader

**Files:**
- Create: `src/jev_ui_agent/rules.py`
- Test: `tests/test_rules.py`

- [ ] **Step 1: Viết test trước**

`tests/test_rules.py`:
```python
from pathlib import Path

import pytest

from jev_ui_agent.rules import DEFAULT_SCORE_CRITERIA, RulesError, load_rules

VALID = """
name: demo_rules
rules:
  - id: login_button_present
    instruction: "A login button labeled 'Sign in' is visible"
  - id: no_error_banner
    instruction: "No red error banner is visible"
    type: noul
  - id: visual_polish
    instruction: "Rate the visual polish"
    type: score
    pass_at: 0.8
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid(tmp_path):
    r = load_rules(_write(tmp_path, VALID))
    assert r["name"] == "demo_rules"
    assert len(r["rules"]) == 3
    assert r["rules"][0] == {"id": "login_button_present",
                             "instruction": "A login button labeled 'Sign in' is visible",
                             "type": "noul"}
    assert r["rules"][2]["pass_at"] == 0.8
    assert "criteria" not in r["rules"][0]


def test_score_default_criteria(tmp_path):
    r = load_rules(_write(tmp_path, "name: x\nrules:\n  - id: s1\n    instruction: Rate it\n    type: score\n"))
    assert r["rules"][0]["criteria"] == DEFAULT_SCORE_CRITERIA
    assert len(DEFAULT_SCORE_CRITERIA) == 5


@pytest.mark.parametrize("bad", [
    "rules:\n  - id: x\n    instruction: hi\n",        # thiếu name
    "name: x\nrules: []\n",                            # rules rỗng
    "name: x\nrules:\n  - id: BAD_ID\n    instruction: hi\n",   # id không slug
    "name: x\nrules:\n  - id: a\n    instruction: hi\n  - id: a\n    instruction: hi2\n",  # trùng id
    "name: x\nrules:\n  - id: a\n",                    # thiếu instruction
    "name: x\nrules:\n  - id: a\n    instruction: hi\n    type: dance\n",  # type lạ
    "name: x\nrules:\n  - id: a\n    instruction: hi\n    type: score\n    criteria: [a, b]\n",  # criteria != 5
    "name: x\nrules:\n  - id: a\n    instruction: hi\n    type: score\n    pass_at: 1.5\n",  # pass_at ngoài [0,1]
])
def test_invalid_rules(tmp_path, bad):
    with pytest.raises(RulesError):
        load_rules(_write(tmp_path, bad))


def test_missing_file():
    with pytest.raises(RulesError):
        load_rules(Path("nope.yaml"))
```

- [ ] **Step 2: Run — expect FAIL** (`uv run pytest tests/test_rules.py -v` → ModuleNotFoundError)

- [ ] **Step 3: Viết `src/jev_ui_agent/rules.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

import yaml

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_TYPES = {"noul", "score"}

DEFAULT_SCORE_CRITERIA = [
    "Completely fails the requirement.",
    "Major problems: the requirement is mostly violated.",
    "Some violations of the requirement are visible.",
    "Minor issues only; the requirement is mostly met.",
    "Fully satisfies the requirement.",
]


class RulesError(ValueError):
    pass


def load_rules(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        raise RulesError(f"Rules file không tồn tại: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as e:
        raise RulesError(f"Không đọc/parse được rules file: {e}") from e
    if (not isinstance(raw, dict) or not isinstance(raw.get("name"), str)
            or not raw["name"].strip() or not isinstance(raw.get("rules"), list) or not raw["rules"]):
        raise RulesError("Rules file phải có 'name' và 'rules' là danh sách không rỗng")
    seen: set[str] = set()
    out: list[dict] = []
    for i, item in enumerate(raw["rules"]):
        if not isinstance(item, dict):
            raise RulesError(f"Rule {i} không hợp lệ: {item!r}")
        rid = item.get("id")
        if not isinstance(rid, str) or not _ID_RE.match(rid):
            raise RulesError(f"Rule {i}: id phải là slug (chữ thường, số, '.', '_', '-'), got {rid!r}")
        if rid in seen:
            raise RulesError(f"Rule id bị trùng: {rid!r}")
        seen.add(rid)
        instruction = item.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise RulesError(f"Rule {rid!r}: cần 'instruction' không rỗng")
        rtype = item.get("type", "noul")
        if rtype not in _TYPES:
            raise RulesError(f"Rule {rid!r}: type phải thuộc {sorted(_TYPES)}, got {rtype!r}")
        rule = {"id": rid, "instruction": instruction.strip(), "type": rtype}
        if rtype == "score":
            criteria = item.get("criteria") or DEFAULT_SCORE_CRITERIA
            if not isinstance(criteria, list) or len(criteria) != 5:
                raise RulesError(f"Rule {rid!r}: criteria (nếu có) phải là đúng 5 mức")
            rule["criteria"] = [str(c) for c in criteria]
            try:
                pass_at = float(item.get("pass_at", 0.75))
            except (TypeError, ValueError) as e:
                raise RulesError(f"Rule {rid!r}: pass_at phải là số") from e
            if not 0.0 <= pass_at <= 1.0:
                raise RulesError(f"Rule {rid!r}: pass_at phải trong [0, 1]")
            rule["pass_at"] = pass_at
        out.append(rule)
    return {"name": raw["name"].strip(), "rules": out}
```

- [ ] **Step 4: Run — expect PASS (11 test cases: 2 + 8 parametrized + 1)**

- [ ] **Step 5: Commit** `feat: natural-language rules loader` (+ Co-Authored-By trailer)

---

### Task 2: Vision observe_detailed + sniffing + thread locks

**Files:**
- Modify: `src/jev_ui_agent/vision/claude_bridge.py`, `src/jev_ui_agent/jev/client.py`
- Test: `tests/test_vision.py` (thêm), `tests/test_jev_client.py` (thêm 1 test)

- [ ] **Step 1: Thêm test trước** (vào `tests/test_vision.py`):

```python
def test_sniff_media_type():
    from jev_ui_agent.vision.claude_bridge import _sniff_media_type
    assert _sniff_media_type(b"\x89PNG\r\n\x1a\n rest") == "image/png"
    assert _sniff_media_type(b"\xff\xd8\xff\xe0 jpeg") == "image/jpeg"
    assert _sniff_media_type(b"garbage") == "image/png"  # default


def test_observe_detailed_keys_and_media_type(monkeypatch, tmp_path):
    img = tmp_path / "shot.jpg"
    img.write_bytes(b"\xff\xd8\xff fake jpeg")
    seen = {}

    def create(**kw):
        seen.update(kw)
        block = seen["messages"][0]["content"][0]
        return _msg('```json\n{"screen_type": "login", "texts": ["Sign in"]}\n```')

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(bridge_mod, "Anthropic", lambda *a, **kw: fake_client)
    vb = VisionBridge()
    obs = vb.observe_detailed(str(img))
    assert seen["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"
    assert obs["screen_type"] == "login"
    for key in bridge_mod.OBS_DETAIL_KEYS:
        assert key in obs  # normalize fill đủ keys
```
(vào `tests/test_jev_client.py`):
```python
def test_usage_updates_thread_safe(monkeypatch):
    import threading
    fake = SimpleNamespace(system_one=lambda **kw: _fake_resp())
    monkeypatch.setattr(client_mod, "TypeSafeClient", lambda *a, **kw: fake)
    jc = JevClient()
    jc._sleep = lambda s: None

    def worker():
        for _ in range(50):
            jc.judge("state", _QK)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert jc.usage["calls"] == 200  # không mất cập nhật do race
```
(biến `_QK` là dict question keys dùng chung — định nghĩa module-level: `_QK = {"q": object()}` và các test hiện có dùng nó thay `{"q": object()}` nếu cần tính đồng nhất; judge với câu trả lời đủ key "q".)

- [ ] **Step 2: Run — expect FAIL** (AttributeError observe_detailed / _sniff_media_type)

- [ ] **Step 3: Implement** trong `claude_bridge.py`:

```python
import threading
# ... sau phần hiện có:
_MAGIC = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"))


def _sniff_media_type(data: bytes) -> str:
    for magic, media in _MAGIC:
        if data.startswith(magic):
            return media
    return "image/png"  # default


DETAILED_OBSERVE_PROMPT = (
    "You are a mobile UI test observer. Look at the screenshot and report ONLY what is "
    "visually verifiable. Be terse and factual, no speculation. "
    "Return a single JSON object with exactly these keys: "
    '"screen_type": your best-guess name for this kind of screen, '
    '"layout": array of {"region": short-area-name, "contents": what is in it}, '
    '"texts": array of the exact visible texts (cap 30, most prominent first), '
    '"images_icons": description of imagery/photos/icons present, '
    '"colors_style": dominant colors, light/dark theme, notable styling, '
    '"error_indicators": any error messages, crash dialogs, empty-state or loading indicators, or "none", '
    '"notable": anything unusual such as clipping, overlapping elements, placeholder or garbled text, or "none".'
)

OBS_DETAIL_KEYS = ("screen_type", "layout", "texts", "images_icons", "colors_style",
                   "error_indicators", "notable")
```
Refactor `VisionBridge`:
- `__init__` thêm `self._lock = threading.Lock()`
- tách core: `def _observe(self, image_path: str, *, prompt: str, keys: tuple[str, ...]) -> dict` — hiện tại `observe()` gọi `self._observe(image_path, prompt=OBSERVE_PROMPT, keys=OBS_KEY)`, và:
```python
    def observe_detailed(self, image_path: str) -> dict:
        """Observation toàn diện cho batch screenshot checking (Task batch mode)."""
        return self._observe(image_path, prompt=DETAILED_OBSERVE_PROMPT, keys=OBS_DETAIL_KEYS)
```
- trong `_observe`: `media_type` từ `_sniff_media_type(data)` thay vì hardcode "image/png"; `with self._lock: self.calls += 1`; normalize theo `keys` (dict fill "none", list keys "layout"/"texts" fill `[]` — normalize: nếu key in ("layout","texts") mặc định [] else "none"); non-dict → ValueError (như hiện tại).
- `OBS_KEY` = 4 keys hiện tại (`blank_areas`, `broken_images`, `text_cut`, `summary`) — giữ nguyên behavior `observe()` cũ (trừ media_type sniff — cải tiến, ảnh PNG không đổi).

Trong `jev/client.py`:
- `import threading`; `__init__` thêm `self._usage_lock = threading.Lock()`
- bọc `self.usage["calls"] += 1` và phần `_absorb_usage` vào `with self._usage_lock:` (gộp: `with self._usage_lock: self.usage["calls"] += 1; self._absorb_usage(resp)`)

- [ ] **Step 4: Run toàn bộ — expect PASS (97 + 3 mới = 100)** — các test vision cũ phải vẫn pass (mock trả PNG bytes thì sniff vẫn png).

- [ ] **Step 5: Commit** `feat: detailed vision observation, media sniffing, thread-safe usage`

---

### Task 3: Rule question builder

**Files:**
- Create: `src/jev_ui_agent/jev/rule_questions.py`
- Test: `tests/test_rule_questions.py`

- [ ] **Step 1: Test trước** (`tests/test_rule_questions.py`):

```python
from typesafe_sdk import Noul, Score

from jev_ui_agent.jev.rule_questions import build_questions
from jev_ui_agent.rules import DEFAULT_SCORE_CRITERIA

RULES = [
    {"id": "login_visible", "instruction": "A 'Sign in' button is visible", "type": "noul"},
    {"id": "polish", "instruction": "Rate the polish", "type": "score",
     "criteria": DEFAULT_SCORE_CRITERIA, "pass_at": 0.75},
    {"id": "polish_default", "instruction": "Rate it", "type": "score"},
]


def test_build_questions_types():
    q = build_questions(RULES)
    assert sorted(q) == ["login_visible", "polish", "polish_default"]
    assert isinstance(q["login_visible"], Noul)
    assert isinstance(q["polish"], Score)
    assert q["polish"].criteria == DEFAULT_SCORE_CRITERIA
    assert q["polish_default"].criteria == DEFAULT_SCORE_CRITERIA  # default rubric


def test_build_questions_content():
    q = build_questions(RULES)
    assert "Sign in" in q["login_visible"].instructions
    assert "near 0.5" in q["login_visible"].instructions  # uncertain guidance
    assert "true" in q["login_visible"].criteria and "false" in q["login_visible"].criteria
    assert "Rate the polish" in q["polish"].instructions
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Viết `src/jev_ui_agent/jev/rule_questions.py`**:

```python
from __future__ import annotations

from typesafe_sdk import Noul, Score

from jev_ui_agent.rules import DEFAULT_SCORE_CRITERIA


def build_questions(rules: list[dict]) -> dict:
    """Sinh câu hỏi JEV từ rules do người dùng định nghĩa (mỗi rule 1 câu hỏi)."""
    q: dict = {}
    for rule in rules:
        instruction = rule["instruction"]
        if rule["type"] == "noul":
            q[rule["id"]] = Noul(
                instructions=(
                    "Using the screen_observation, is this requirement satisfied? "
                    f'Requirement: "{instruction}" '
                    "If the observation lacks enough detail to decide, answer near 0.5 (uncertain)."
                ),
                criteria={
                    "true": "The observation clearly shows the requirement is satisfied.",
                    "false": "The observation clearly shows the requirement is violated "
                             "or the expected content is absent.",
                },
            )
        else:
            q[rule["id"]] = Score(
                instructions=f'Rate the screen against this requirement: "{instruction}"',
                criteria=rule.get("criteria") or DEFAULT_SCORE_CRITERIA,
            )
    return q
```
(Lưu ý: `criteria` của Noul/Score là pydantic model — truy cập `.criteria` trả mapping/sequence; test assert membership/equality đã được Task 6 của Phase 1 chứng minh works.)

- [ ] **Step 4: Run — expect PASS (102)**

- [ ] **Step 5: Commit** `feat: dynamic question builder for user-defined rules`

---

### Task 4: RunReport.summary + batch core

**Files:**
- Modify: `src/jev_ui_agent/models.py` (thêm 1 field)
- Create: `src/jev_ui_agent/batch.py`
- Test: `tests/test_batch.py`

- [ ] **Step 1: models.py** — thêm field cuối `RunReport`:
```python
    summary: dict[str, Any] = field(default_factory=dict)  # batch mode: stats tổng hợp
```
(chạy `uv run pytest -q` — 102 vẫn pass, field additive)

- [ ] **Step 2: Viết test trước** (`tests/test_batch.py`):

```python
import json
from pathlib import Path

import pytest

from jev_ui_agent.batch import _cp_from_record, _image_status, run_batch, scan_images
from jev_ui_agent.models import Verdict

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def img_dir(tmp_path):
    d = tmp_path / "shots"
    d.mkdir()
    (d / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nAAA")
    (d / "b.png").write_bytes(b"\x89PNG\r\n\x1a\nBBB")
    (d / "c.jpg").write_bytes(b"\xff\xd8\xffCCC")
    (d / "ignored.txt").write_text("not an image")
    (d / "sub").mkdir()
    (d / "sub" / "d.png").write_bytes(b"\x89PNG\r\n\x1a\nDDD")
    return d


class FakeVision:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on or set()
        self.calls = 0

    def observe_detailed(self, path):
        from jev_ui_agent.vision.claude_bridge import VisionUnavailable
        self.calls += 1
        if Path(path).name in self.fail_on:
            raise VisionUnavailable("api down")
        return {k: ("none" if k != "texts" else ["Sign in"]) for k in
                ("screen_type", "texts", "images_icons", "colors_style",
                 "error_indicators", "notable")}


class FakeJev:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on or set()
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def judge(self, state, questions):
        from jev_ui_agent.jev.client import JevError
        self.usage["calls"] += 1
        if state["image"] in self.fail_on:
            raise JevError("api down")
        out = {}
        for rid in questions:
            if rid.endswith("_polish"):
                out[rid] = {"value": 4.0, "confidence": 0.95, "probabilities": {}}
            else:
                out[rid] = {"value": 0.9, "confidence": 0.95, "probabilities": {}}
        return out


RULES = """
name: t
rules:
  - id: login_visible
    instruction: "A 'Sign in' button is visible"
  - id: overall_polish
    instruction: "Rate the polish"
    type: score
"""


def _rules_file(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text(RULES, encoding="utf-8")
    return p


def test_scan_images(img_dir):
    assert [p.name for p in scan_images(img_dir)] == ["a.png", "b.png", "c.jpg"]
    assert len(scan_images(img_dir, recursive=True)) == 4


def test_sha256_dedup(img_dir, tmp_path):
    (img_dir / "b.png").write_bytes((img_dir / "a.png").read_bytes())
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=FakeJev(), vision=FakeVision())
    assert report.summary["total_images"] == 4
    assert report.summary["duplicates"] == 1
    by_name = {cp.checkpoint: cp for cp in report.checkpoints}
    assert by_name["b.png"].results[0].evidence.get("duplicate_of") == "a.png"


def test_run_batch_pass_and_costs(img_dir, tmp_path):
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=FakeJev(), vision=FakeVision())
    s = report.summary
    assert s["total_images"] == 4 and s["passed"] == 4 and s["failed"] == 0
    assert s["needs_review"] == 0 and s["errors"] == 0
    assert report.costs["jev"]["calls"] == 3  # a, c, sub/d (b duplicate)
    assert report.costs["vision"] == {"calls": 3}
    run_dir = tmp_path / "r" / report.run_id
    data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert data["summary"]["total_images"] == 4
    lines = (run_dir / "checkpoint.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and all(json.loads(l)["status"] == "done" for l in lines)


def test_fail_verdict_and_gate(img_dir, tmp_path):
    class PickyJev(FakeJev):
        def judge(self, state, questions):
            out = super().judge(state, questions)
            if state["image"] == "a.png":
                out["login_visible"] = {"value": 0.1, "confidence": 0.95, "probabilities": {}}
                out["overall_polish"] = {"value": 1.0, "confidence": 0.95, "probabilities": {}}
            if state["image"] == "c.jpg":
                out["login_visible"] = {"value": 0.9, "confidence": 0.4, "probabilities": {}}
            return out

    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=PickyJev(), vision=FakeVision())
    s = report.summary
    assert s["failed"] == 1 and s["needs_review"] == 1 and s["passed"] == 2
    assert report.checkpoints[0].checkpoint == "a.png"   # fail-first
    assert report.checkpoints[1].checkpoint == "c.jpg"
    by_name = {cp.checkpoint: cp for cp in report.checkpoints}
    fails = [r.check_id for r in by_name["a.png"].results if r.verdict is Verdict.FAIL]
    assert "rule/login_visible" in fails and "rule/overall_polish" in fails
    nr = next(r for r in by_name["c.jpg"].results if r.check_id == "rule/login_visible")
    assert nr.verdict is Verdict.NEEDS_REVIEW and nr.evidence["pre_gate_verdict"] == "pass"


def test_error_images_recorded(img_dir, tmp_path):
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       jev=FakeJev(fail_on={"a.png"}), vision=FakeVision(fail_on={"c.jpg"}))
    s = report.summary
    assert s["errors"] == 2 and s["passed"] == 1 and s["duplicates"] == 1


def test_limit(img_dir, tmp_path):
    report = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       limit=1, jev=FakeJev(), vision=FakeVision())
    assert report.summary["total_images"] == 1


def test_resume_skips_done_and_retries_errors(img_dir, tmp_path):
    first = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                      policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                      jev=FakeJev(fail_on={"a.png"}), vision=FakeVision())
    run_dir = tmp_path / "r" / first.run_id
    jev2 = FakeJev()
    second = run_batch(images_dir=img_dir, rules_path=_rules_file(tmp_path),
                       policy_path=FIX / "policy_test.yaml", out_root=tmp_path / "r",
                       resume_dir=run_dir, jev=jev2, vision=FakeVision())
    assert second.run_id == first.run_id
    assert second.summary["errors"] == 0 and second.summary["passed"] == 4
    assert jev2.usage["calls"] == 1  # chỉ retry a.png; b duplicate reuse


def test_cp_from_record_roundtrip():
    rec = {"image": "x.png", "hash": "h", "status": "done",
           "report": {"checkpoint": "x.png", "screen_score": 1.0, "screenshot": "x.png",
                      "error": "",
                      "results": [{"check_id": "rule/r1", "group": "rules", "path": "vision+jev",
                                   "verdict": "pass", "score": None, "confidence": 0.9,
                                   "probabilities": {}, "evidence": {"noul": 0.9}, "error": ""}]}}
    cp = _cp_from_record(rec)
    assert cp.checkpoint == "x.png" and cp.results[0].verdict is Verdict.PASS
    assert _image_status(cp) == "passed"
```

- [ ] **Step 3: Run — expect FAIL** (ModuleNotFoundError batch)

- [ ] **Step 4: Viết `src/jev_ui_agent/batch.py`**:

```python
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from jev_ui_agent.checks.composite import apply_confidence_gate
from jev_ui_agent.jev.client import JevClient, JevError
from jev_ui_agent.jev.rule_questions import build_questions
from jev_ui_agent.models import CheckResult, CheckpointReport, RunReport, Verdict
from jev_ui_agent.pipeline import load_yaml
from jev_ui_agent.report.html import render_html
from jev_ui_agent.report.json_report import render_json
from jev_ui_agent.rules import load_rules
from jev_ui_agent.vision.claude_bridge import VisionBridge, VisionUnavailable

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
CHECKPOINT_FILE = "checkpoint.jsonl"
_ORDER = {"failed": 0, "needs_review": 1, "error": 2, "passed": 3}


def scan_images(directory: Path | str, recursive: bool = False) -> list[Path]:
    d = Path(directory)
    if not d.is_dir():
        raise NotADirectoryError(f"Không phải thư mục: {d}")
    it = d.rglob("*") if recursive else d.glob("*")
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in _IMAGE_EXTS)


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _image_status(cp: CheckpointReport) -> str:
    if cp.error:
        return "error"
    verdicts = {r.verdict for r in cp.results}
    if Verdict.FAIL in verdicts:
        return "failed"
    if Verdict.NEEDS_REVIEW in verdicts:
        return "needs_review"
    return "passed"


def _cp_from_record(rec: dict) -> CheckpointReport:
    rep = rec["report"]
    results = [CheckResult(verdict=Verdict(r["verdict"]),
                           **{k: v for k, v in r.items() if k != "verdict"})
               for r in rep.get("results", [])]
    return CheckpointReport(checkpoint=rep["checkpoint"], screen_score=rep.get("screen_score"),
                            results=results, screenshot=rep.get("screenshot", ""),
                            error=rep.get("error", ""))


def _judge_image(path: Path, rules: dict, jev: JevClient, vision: VisionBridge,
                 gate: float) -> CheckpointReport:
    cp = CheckpointReport(checkpoint=path.name, screenshot=str(path).replace("\\", "/"))
    try:
        observation = vision.observe_detailed(str(path))
        payload = {"image": path.name, "screen_observation": observation}
        answers = jev.judge(payload, build_questions(rules["rules"]))
    except (VisionUnavailable, JevError) as e:
        cp.error = f"{type(e).__name__}: {e}"
        return cp
    results: list[CheckResult] = []
    for rule in rules["rules"]:
        ans = answers.get(rule["id"])
        if ans is None:
            results.append(CheckResult(f"rule/{rule['id']}", "rules", "vision+jev",
                                       Verdict.ERROR, error="missing answer"))
            continue
        if rule["type"] == "noul":
            satisfied = (ans.get("value") or 0.0) >= 0.5
            r = CheckResult(f"rule/{rule['id']}", "rules", "vision+jev",
                            Verdict.PASS if satisfied else Verdict.FAIL,
                            confidence=ans.get("confidence"),
                            evidence={"noul": ans.get("value"),
                                      "instruction": rule["instruction"]})
        else:
            norm = (ans.get("value") or 0.0) / 4.0
            r = CheckResult(f"rule/{rule['id']}", "rules", "vision+jev",
                            Verdict.PASS if norm >= rule.get("pass_at", 0.75) else Verdict.FAIL,
                            score=norm, confidence=ans.get("confidence"),
                            evidence={"raw_score": ans.get("value"),
                                      "instruction": rule["instruction"]})
        results.append(apply_confidence_gate(r, gate))
    cp.results = results
    values = [1.0 if v is Verdict.PASS else 0.0 if v is Verdict.FAIL else 0.5
              for v in (r.verdict for r in results)
              if v in (Verdict.PASS, Verdict.FAIL, Verdict.NEEDS_REVIEW)]
    cp.screen_score = round(sum(values) / len(values), 4) if values else None
    return cp


def _status_counts(cps: list[CheckpointReport]) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "needs_review": 0, "error": 0}
    for cp in cps:
        counts[_image_status(cp)] += 1
    return counts


def run_batch(*, images_dir: Path | str, rules_path: Path | str, policy_path: Path | str,
              out_root: Path | str, workers: int = 4, limit: int | None = None,
              recursive: bool = False, resume_dir: Path | str | None = None,
              jev: JevClient | None = None, vision: VisionBridge | None = None) -> RunReport:
    if jev is None or vision is None:
        raise ValueError("check-screenshots cần cả jev và vision client")
    policy = load_yaml(policy_path)
    rules = load_rules(rules_path)
    gate = float(policy.get("confidence_gate", 0.75))

    images = scan_images(images_dir, recursive)
    if limit is not None:
        images = images[: max(0, int(limit))]
    hashes = {p: sha256_file(p) for p in images}

    if resume_dir:
        out_dir = Path(resume_dir)
        if not out_dir.is_dir():
            raise ValueError(f"resume dir không tồn tại: {out_dir}")
        run_id = out_dir.name
    else:
        run_id = f"check-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        out_dir = Path(out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / CHECKPOINT_FILE

    done_by_hash: dict[str, dict] = {}
    if ckpt_path.exists():
        for line in ckpt_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("status") == "done":
                    done_by_hash[rec["hash"]] = rec  # dòng sau đè dòng trước (mới nhất thắng)

    unique: dict[str, Path] = {}
    for p in images:
        unique.setdefault(hashes[p], p)

    pending = [p for h, p in unique.items() if h not in done_by_hash]
    new_cps: dict[str, CheckpointReport] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_judge_image, p, rules, jev, vision, gate): p for p in pending}
        for fut in as_completed(futures):
            p = futures[fut]
            new_cps[hashes[p]] = fut.result()

    with open(ckpt_path, "a", encoding="utf-8") as ckpt:
        for h, p in unique.items():
            if h in new_cps:
                rec = {"image": str(p), "hash": h,
                       "status": "error" if new_cps[h].error else "done",
                       "report": asdict(new_cps[h])}
                ckpt.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")
        ckpt.flush()

    cps: list[CheckpointReport] = []
    seen_hash: dict[str, str] = {}
    duplicates = 0
    for p in images:
        h = hashes[p]
        if h in seen_hash:
            duplicates += 1
            src = new_cps[h] if h in new_cps else _cp_from_record(done_by_hash[h])
            cp = CheckpointReport(checkpoint=p.name, screen_score=src.screen_score,
                                  results=list(src.results),
                                  screenshot=str(p).replace("\\", "/"), error=src.error)
            if cp.results:
                first = cp.results[0]
                first.evidence = dict(first.evidence, duplicate_of=seen_hash[h])
            elif cp.error:
                cp.error = f"{cp.error} (duplicate của {seen_hash[h]})"
            cps.append(cp)
        else:
            seen_hash[h] = p.name
            cps.append(new_cps[h] if h in new_cps else _cp_from_record(done_by_hash[h]))

    counts = _status_counts(cps)
    counts["duplicates"] = duplicates
    counts["total_images"] = len(images)
    counts["rules"] = len(rules["rules"])

    report = RunReport(run_id=run_id, flow_name=f"rules:{rules['name']}",
                       started_at=datetime.now().isoformat(timespec="seconds"),
                       checkpoints=sorted(cps, key=lambda c: _ORDER[_image_status(c)]),
                       summary=counts)
    report.costs["jev"] = dict(jev.usage)
    report.costs["vision"] = {"calls": vision.calls}

    (out_dir / "report.json").write_text(render_json(report), encoding="utf-8")
    (out_dir / "report.html").write_text(render_html(report), encoding="utf-8")
    return report
```

- [ ] **Step 5: Run — expect PASS (102 + 9 mới = 111)**

- [ ] **Step 6: Commit** `feat: batch screenshot checking core with dedup, parallelism and resume`

---

### Task 5: Report summary section

**Files:**
- Modify: `src/jev_ui_agent/report/html.py`
- Test: `tests/test_report.py` (thêm)

- [ ] **Step 1: Test trước**:

```python
def test_render_html_summary_section():
    rep = sample_report()
    rep.summary = {"total_images": 10, "passed": 7, "failed": 2, "needs_review": 1,
                   "errors": 0, "duplicates": 3, "rules": 5}
    html = render_html(rep)
    assert "Batch summary" in html and "10" in html


def test_render_html_no_summary_when_empty():
    assert "Batch summary" not in render_html(sample_report())
```

- [ ] **Step 2: Run — expect FAIL (1)**

- [ ] **Step 3: Implement** — trong `_TEMPLATE`, ngay sau khối `<p class="meta">...`:

```html
{% if report.summary %}
<div class="card"><h2>Batch summary</h2>
  <table>
    <tr><th>Total images</th><td>{{ report.summary.total_images }}</td>
        <th>Passed</th><td>{{ report.summary.passed }}</td></tr>
    <tr><th>Failed</th><td>{{ report.summary.failed }}</td>
        <th>Needs review</th><td>{{ report.summary.needs_review }}</td></tr>
    <tr><th>Errors</th><td>{{ report.summary.errors }}</td>
        <th>Duplicates</th><td>{{ report.summary.duplicates }}</td></tr>
    <tr><th>Rules</th><td>{{ report.summary.rules }}</td><th></th><td></td></tr>
  </table>
</div>
{% endif %}
```

- [ ] **Step 4: Run — expect PASS (113)**

- [ ] **Step 5: Commit** `feat: batch summary section in html report`

---

### Task 6: CLI subcommand + README

**Files:**
- Modify: `src/jev_ui_agent/__main__.py`, `README.md`
- Test: `tests/test_cli.py` (thêm)

- [ ] **Step 1: Test trước** (thêm vào `tests/test_cli.py`):

```python
def test_check_screenshots_cli_requires_keys(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["check-screenshots", "--dir", str(tmp_path), "--rules", "x.yaml"])
    assert rc == 2


def test_check_screenshots_cli_exit_codes(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    from types import SimpleNamespace
    import jev_ui_agent.__main__ as main_mod

    def fake_batch_fail(**kw):
        return SimpleNamespace(run_id="check-x",
                               summary={"total_images": 3, "passed": 2, "failed": 1,
                                        "needs_review": 0, "errors": 0},
                               checkpoints=[], costs={})

    monkeypatch.setattr(main_mod, "run_batch", fake_batch_fail)
    assert main(["check-screenshots", "--dir", str(tmp_path), "--rules", "r.yaml"]) == 1

    def fake_batch_pass(**kw):
        return SimpleNamespace(run_id="check-y",
                               summary={"total_images": 3, "passed": 3, "failed": 0,
                                        "needs_review": 0, "errors": 0},
                               checkpoints=[], costs={})

    monkeypatch.setattr(main_mod, "run_batch", fake_batch_pass)
    assert main(["check-screenshots", "--dir", str(tmp_path), "--rules", "r.yaml"]) == 0
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement CLI** — trong `__main__.py`: import `from jev_ui_agent.batch import run_batch`; thêm subparser `check-screenshots` với các arg: `--dir` (required), `--rules` (required), `--policy` (default config/policy.yaml), `--out` (default reports), `--workers` (int, default 4), `--limit` (int), `--recursive` (store_true), `--resume`; dispatch:

```python
    if args.command == "check-screenshots":
        if not (os.environ.get("TYPESAFE_API_KEY") and os.environ.get("ANTHROPIC_API_KEY")):
            print("check-screenshots requires both TYPESAFE_API_KEY and ANTHROPIC_API_KEY "
                  "(every rule goes through vision + JEV).", file=sys.stderr)
            return 2
        jev = JevClient()
        vision = VisionBridge()
        report = run_batch(images_dir=args.dir, rules_path=args.rules,
                           policy_path=args.policy, out_root=args.out,
                           workers=max(1, args.workers), limit=args.limit,
                           recursive=args.recursive, resume_dir=args.resume,
                           jev=jev, vision=vision)
        s = report.summary
        print(f"Run {report.run_id}: {s.get('total_images', 0)} images - "
              f"{s.get('passed', 0)} pass, {s.get('failed', 0)} fail, "
              f"{s.get('needs_review', 0)} review, {s.get('errors', 0)} error")
        print(f"Report: {Path(args.out) / report.run_id / 'report.html'}")
        return 1 if (s.get("failed") or s.get("errors")) else 0
```
(giữ nguyên nhánh `run` hiện tại; restructure dispatch if/elif nếu gọn hơn nhưng KHÔNG đổi behavior/handling của `run`)

- [ ] **Step 4: Run toàn bộ — expect PASS (115)**

- [ ] **Step 5: README** — thêm section "Batch screenshot checking (rules-based)" sau phần Live E2E (tiếng Anh, khớp style hiện tại): use case (folder ảnh tĩnh + rule tự nhiên), ví dụ rules.yaml như trong spec, lệnh CLI kèm `--workers/--limit/--recursive/--resume`, chi phí ước tính (2.000 ảnh ≈ $6-15 vision + JEV rẻ), note PNG/JPG.

- [ ] **Step 6: Commit** `feat: check-screenshots cli subcommand and readme`

---

## Self-Review

1. **Spec coverage:** rules noul+score (T1), observation toàn diện + sniff + thread-safe (T2), question factory (T3), dedup/parallel/resume/checkpoint/summary/fail-first (T4), HTML summary (T5), CLI + exit codes + README (T6). ✅
2. **Placeholder scan:** mọi bước code có code block đầy đủ; không TBD/TODO.
3. **Type consistency:** `run_batch(...)` keyword-args nhất quán T4/T6; `observe_detailed`/`OBS_DETAIL_KEYS`/`_sniff_media_type` T2→T4; `build_questions(rules["rules"])` T3→T4; `RunReport.summary` models→T4→T5→T6.

## Ghi chú thực thi

- Task 2 refactor `observe()` → `_observe()` phải giữ nguyên behavior của 97 tests Phase 1 (không đổi test cũ).
- Attribution: mỗi commit kết thúc bằng `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
