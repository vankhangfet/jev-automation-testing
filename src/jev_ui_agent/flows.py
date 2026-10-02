from __future__ import annotations

import re
from pathlib import Path

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
                raise FlowError(f"Checkpoint {i}: tên {name!r} chỉ được chứa chữ, số, '.', '_', '-' và không bắt đầu bằng ký tự đặc biệt")
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
