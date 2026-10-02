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
