from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from jev_ui_agent.models import Bounds, ScreenState, StepArtifact, UIElement

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


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
