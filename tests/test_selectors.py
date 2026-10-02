import pytest

from jev_ui_agent.driver.selectors import find_element, parse
from jev_ui_agent.models import Bounds, UIElement


def test_parse_prefixes():
    assert parse("res-id:login_btn") == ("id", "login_btn")
    assert parse("acc-id:Sign in") == ("acc", "Sign in")
    assert parse("text:Hello") == ("text", "Hello")
    assert parse("xpath://a/b") == ("xpath", "//a/b")


def test_parse_invalid():
    with pytest.raises(ValueError):
        parse("login_btn")


def test_parse_rejects_empty_value():
    with pytest.raises(ValueError):
        parse("res-id:")
    with pytest.raises(ValueError):
        parse("text:")


def test_find_by_id_suffix():
    els = [UIElement(id="com.example:id/login_btn", type="Button", text="Sign in")]
    assert find_element(els, "res-id:login_btn") is els[0]


def test_find_by_acc_and_text():
    els = [
        UIElement(id="a", content_desc="Email field"),
        UIElement(id="b", text="Welcome"),
    ]
    assert find_element(els, "acc-id:Email field") is els[0]
    assert find_element(els, "text:Welcome") is els[1]
    assert find_element(els, "text:Missing") is None
