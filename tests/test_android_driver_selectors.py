from jev_ui_agent.driver.android import to_appium_locator


def test_to_appium_locator():
    from appium.webdriver.common.appiumby import AppiumBy
    assert to_appium_locator("res-id:login_btn") == (AppiumBy.ID, "login_btn")
    assert to_appium_locator("acc-id:Sign in") == (AppiumBy.ACCESSIBILITY_ID, "Sign in")
    assert to_appium_locator("xpath://x/y") == (AppiumBy.XPATH, "//x/y")
    kind, value = to_appium_locator("text:For You")
    assert kind == AppiumBy.XPATH
    assert "For You" in value and value.startswith("//*[@")
