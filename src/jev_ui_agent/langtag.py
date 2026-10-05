from __future__ import annotations

import re
from pathlib import Path

# Placeholder trong rule instruction, được thay bằng tên ngôn ngữ lấy từ
# đuôi tên file ảnh (vd 'events_filter_advanced_2-en.png' -> 'English').
LANG_PLACEHOLDER = "{language}"

_TAG_RE = re.compile(r"-([A-Za-z]{2})$")

# Tên hiển thị cho các locale phổ biến; code lạ -> dùng chính code đó.
LANG_NAMES = {
    "en": "English", "vi": "Vietnamese", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "th": "Thai", "id": "Indonesian", "ms": "Malay",
    "fr": "French", "de": "German", "es": "Spanish", "pt": "Portuguese",
    "it": "Italian", "ru": "Russian", "ar": "Arabic", "hi": "Hindi",
    "nl": "Dutch", "pl": "Polish", "tr": "Turkish", "sv": "Swedish",
}


def detect_language_tag(filename: str) -> str | None:
    """Trả về code ngôn ngữ 2 ký tự ở cuối tên file, None nếu không có.

    >>> detect_language_tag("events_filter_advanced_2-en.png")
    'en'
    """
    m = _TAG_RE.search(Path(filename).stem)
    return m.group(1).lower() if m else None


def language_name(code: str) -> str:
    """Tên ngôn ngữ tiếng Anh cho code; code lạ giữ nguyên theo dạng dễ đọc."""
    c = code.lower()
    return LANG_NAMES.get(c, f"the language with code '{c}'")
