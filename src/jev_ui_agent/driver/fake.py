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
