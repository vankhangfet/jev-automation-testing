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
