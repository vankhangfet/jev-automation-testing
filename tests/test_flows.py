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
    "steps: 5\n",                                      # steps không phải list
    "steps: {a: b}\n",                                 # steps là dict, không phải list
    "steps:\n  - checkpoint: '../evil'\n",             # checkpoint tên path-traversal
    "steps:\n  - checkpoint: 'ho:me'\n",               # checkpoint tên có dấu ':'
    "steps:\n  - checkpoint: 'C:/tmp/evil'\n",         # checkpoint kiểu đường dẫn
])
def test_invalid_flows(tmp_path, bad):
    with pytest.raises(FlowError):
        load_flow(_write(tmp_path, bad))


def test_missing_file():
    with pytest.raises(FlowError):
        load_flow(Path("nope.yaml"))


def test_kind_key_cannot_override(tmp_path):
    flow = load_flow(_write(tmp_path, "steps:\n  - action: launch\n    kind: checkpoint\n"))
    assert flow["steps"][0]["kind"] == "action"
    assert flow["steps"][0]["action"] == "launch"


def test_duplicate_checkpoint_names(tmp_path):
    dup = "steps:\n  - checkpoint: home\n  - checkpoint: home\n"
    with pytest.raises(FlowError):
        load_flow(_write(tmp_path, dup))


def test_non_utf8_file(tmp_path):
    p = tmp_path / "flow.yaml"
    p.write_bytes(b"\xff\xfename: x")
    with pytest.raises(FlowError):
        load_flow(p)
