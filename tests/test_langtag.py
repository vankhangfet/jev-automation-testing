from jev_ui_agent.langtag import LANG_PLACEHOLDER, detect_language_tag, language_name


def test_detect_tag_from_filename():
    assert detect_language_tag("events_filter_advanced_2-en.png") == "en"
    assert detect_language_tag("home-vi.jpg") == "vi"
    assert detect_language_tag("Home-VI.JPEG") == "vi"      # hoa + đuôi viết hoa
    assert detect_language_tag("menu_2_settings-ja.png") == "ja"


def test_detect_tag_returns_none_when_absent_or_not_two_letters():
    assert detect_language_tag("settings.png") is None      # không có đuôi -xx
    assert detect_language_tag("hero-4k.png") is None       # có số
    assert detect_language_tag("login-v2.png") is None      # 'v2' có số
    assert detect_language_tag("deep-nested-name.png") is None  # 'name' 4 chữ


def test_language_name_known_and_unknown_codes():
    assert language_name("en") == "English"
    assert language_name("VI") == "Vietnamese"
    assert language_name("ja") == "Japanese"
    assert "xy" in language_name("xy")                      # code lạ vẫn dùng được


def test_placeholder_constant():
    assert LANG_PLACEHOLDER == "{language}"
