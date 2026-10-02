from __future__ import annotations

from typesafe_sdk import Choice, Noul, Score


def core_questions(content_quality: bool = True, error_anomaly: bool = True) -> dict:
    """Bộ câu hỏi JEV chạy trực tiếp trên ScreenState payload."""
    q: dict = {}
    if error_anomaly:
        q["screen_class"] = Choice(
            instructions="Classify what kind of mobile screen this element tree represents.",
            criteria={
                "normal": "A fully rendered screen showing its expected content.",
                "error_screen": "The screen displays an error message or a failed-load state.",
                "crash_dialog": "A system dialog saying the app crashed or stopped.",
                "empty_state": "The screen rendered but contains no content (empty list, blank body).",
                "loading_stuck": "Only a loading indicator is visible, content never arrived.",
            },
        )
    if content_quality:
        q["has_raw_i18n_key"] = Noul(
            instructions="Does any visible element text look like an untranslated i18n key, "
                         "e.g. `login.title`, `welcome.message`, `btn.submit`?")
        q["has_dev_text"] = Noul(
            instructions="Does any visible text contain developer artifacts such as TODO, "
                         "FIXME, stack traces, debug values, or filler like 'Lorem ipsum'?")
        q["typo_severity"] = Score(
            instructions="Rate the writing quality of all visible labels and texts.",
            criteria=[
                "No visible text at all.",
                "Severe issues: misspellings or broken grammar in multiple prominent labels.",
                "Some misspellings or awkward grammar in one or two labels.",
                "Minor issues only: inconsistent capitalization or spacing.",
                "Clean, consistent, well-written text.",
            ],
        )
    return q


def visual_questions() -> dict:
    """Bộ câu hỏi JEV chạy trên payload có visual_observation (từ vision bridge)."""
    return {
        "visual_blank": Noul(
            instructions="Using the visual_observation field, does the screen look mostly "
                         "blank or unrendered?"),
        "visual_broken": Noul(
            instructions="Using the visual_observation field, does the screen show broken "
                         "images, missing images, or obvious rendering artifacts?"),
        "visual_text_cut": Noul(
            instructions="Using the visual_observation field, does any text appear visually "
                         "cut off, clipped, or truncated?"),
    }
