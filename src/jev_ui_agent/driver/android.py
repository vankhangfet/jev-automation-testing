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
        ok = self._d.get_screenshot_as_file(str(png))  # trả bool, KHÔNG raise khi fail
        if not ok or not png.exists():
            raise RuntimeError(f"screenshot failed for {checkpoint!r}")
        try:
            activity = self._d.current_activity
        except Exception:  # noqa: BLE001
            activity = ""
        return StepArtifact(checkpoint=checkpoint, screenshot_path=str(png),
                            source_xml=self._d.page_source, activity=activity)

    def quit(self) -> None:
        self._d.quit()
