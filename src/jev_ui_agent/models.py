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
    summary: dict[str, Any] = field(default_factory=dict)  # batch mode: stats tổng hợp
