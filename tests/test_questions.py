from jev_ui_agent.jev.questions import core_questions, visual_questions


def test_core_question_schema():
    q = core_questions()
    assert sorted(q) == ["has_dev_text", "has_raw_i18n_key", "screen_class", "typo_severity"]
    assert "normal" in q["screen_class"].criteria
    assert len(q["typo_severity"].criteria) == 5
    assert sorted(core_questions(content_quality=False)) == ["screen_class"]
    assert sorted(core_questions(error_anomaly=False)) == [
        "has_dev_text", "has_raw_i18n_key", "typo_severity"]


def test_visual_question_schema():
    v = visual_questions()
    assert sorted(v) == ["visual_blank", "visual_broken", "visual_text_cut"]


def test_question_criteria_content():
    q = core_questions()
    # typo_severity: rubric ordinal thuần — mức 0 là garbled, "no text" nằm ở instructions
    assert q["typo_severity"].criteria[0].startswith("Text is garbled")
    assert "choose the top level" in q["typo_severity"].instructions
    # 2 noul question có contrastive criteria true/false
    assert set(q["has_raw_i18n_key"].criteria) == {"true", "false"}
    assert "login.title" in q["has_raw_i18n_key"].criteria["true"]
    assert set(q["has_dev_text"].criteria) == {"true", "false"}
    assert "TODO" in q["has_dev_text"].criteria["true"]
    # loading_stuck: quan sát được từ snapshot
    assert "no content elements" in q["screen_class"].criteria["loading_stuck"]
