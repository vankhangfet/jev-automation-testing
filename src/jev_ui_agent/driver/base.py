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
