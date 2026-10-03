import pytest

from jev_ui_agent.driver.android import to_appium_locator


def test_to_appium_locator():
    from appium.webdriver.common.appiumby import AppiumBy
    assert to_appium_locator("res-id:login_btn") == (AppiumBy.ID, "login_btn")
    assert to_appium_locator("acc-id:Sign in") == (AppiumBy.ACCESSIBILITY_ID, "Sign in")
    assert to_appium_locator("xpath://x/y") == (AppiumBy.XPATH, "//x/y")
    kind, value = to_appium_locator("text:For You")
    assert kind == AppiumBy.XPATH
    assert "For You" in value and value.startswith("//*[@")


def test_text_selector_with_apostrophe():
    from appium.webdriver.common.appiumby import AppiumBy
    kind, value = to_appium_locator("text:You're offline")
    assert kind == AppiumBy.XPATH
    assert value == "//*[@text=concat('You', \"'\", 're offline')]"


def test_android_driver_lazy_session(tmp_path):
    from jev_ui_agent.driver.android import AndroidDriver
    d = AndroidDriver({"capabilities": {"platformName": "Android"}}, out_dir=tmp_path)
    assert (tmp_path / "artifacts").is_dir()  # __init__ không còn mở session
    with pytest.raises(RuntimeError):
        d.tap("res-id:x")          # action trước connect() phải raise rõ ràng
    with pytest.raises(RuntimeError):
        d.launch()
    d.quit()                       # chưa connect → no-op, không raise
