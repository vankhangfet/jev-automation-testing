import json

from jev_ui_agent.models import CheckpointReport, CheckResult, RunReport, Verdict
from jev_ui_agent.report.html import render_html
from jev_ui_agent.report.json_report import render_json


def sample_report() -> RunReport:
    return RunReport(
        run_id="run-1", flow_name="demo", started_at="2026-10-02T10:00:00",
        checkpoints=[
            CheckpointReport(
                checkpoint="home", screen_score=0.8123, screenshot="artifacts/home.png",
                results=[
                    CheckResult("functional/element:res-id:login_btn", "functional",
                                "rule", Verdict.PASS),
                    CheckResult("content_quality/raw_i18n_key", "content_quality", "jev",
                                Verdict.NEEDS_REVIEW, confidence=0.5,
                                evidence={"pre_gate_verdict": "fail"}),
                ]),
        ],
        failed_steps=["tap acc-id:Go"],
        costs={"jev": {"calls": 2, "input_tokens": 800, "output_tokens": 100}},
    )


def test_render_json_roundtrip():
    data = json.loads(render_json(sample_report()))
    assert data["run_id"] == "run-1"
    verdicts = [r["verdict"] for r in data["checkpoints"][0]["results"]]
    assert verdicts == ["pass", "needs_review"]  # enum → string value
    assert data["costs"]["jev"]["calls"] == 2


def test_render_html_markers():
    html = render_html(sample_report())
    assert "run-1" in html and "demo" in html
    assert "home" in html
    assert "needs_review" in html
    assert "acc-id:Go" in html          # failed step hiển thị
    assert 'src="artifacts/home.png"' in html
    assert "0.8123" in html


def test_render_html_summary_section():
    rep = sample_report()
    rep.summary = {"total_images": 10, "passed": 7, "failed": 2, "needs_review": 1,
                   "errors": 0, "duplicates": 3, "rules": 5, "missing": 1}
    html = render_html(rep)
    assert "Batch summary" in html and "10" in html and "Passed" in html


def test_render_html_no_summary_when_empty():
    assert "Batch summary" not in render_html(sample_report())


def test_render_json_includes_finished_at():
    rep = sample_report()
    rep.finished_at = "2026-10-02T10:04:30"
    data = json.loads(render_json(rep))
    assert data["started_at"] == "2026-10-02T10:00:00"
    assert data["finished_at"] == "2026-10-02T10:04:30"


def test_render_html_shows_start_end_and_duration():
    rep = sample_report()
    rep.finished_at = "2026-10-02T10:04:32"
    html = render_html(rep)
    assert "10:00:00" in html
    assert "kết thúc" in html and "10:04:32" in html
    assert "4m 32s" in html


def test_render_html_without_finished_at_hides_end():
    html = render_html(sample_report())  # finished_at để trống (default)
    assert "kết thúc" not in html
    assert "10:00:00" in html  # thời gian bắt đầu vẫn hiển thị
