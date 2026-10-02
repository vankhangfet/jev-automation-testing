from __future__ import annotations

from jinja2 import Environment

from jev_ui_agent.models import RunReport, Verdict

_BADGES = {
    Verdict.PASS: "badge pass", Verdict.FAIL: "badge fail",
    Verdict.NEEDS_REVIEW: "badge review", Verdict.ERROR: "badge error",
    Verdict.SKIPPED: "badge skipped",
}

_TEMPLATE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>JEV UI Report {{ report.run_id }}</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #fafafa; }
  h1, h2 { color: #1a1a2e; }
  .meta { color: #555; margin-bottom: 1rem; }
  .card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
          padding: 1rem; margin: 1rem 0; }
  table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee;
           font-size: 0.9rem; }
  .badge { padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; font-weight: 600; }
  .pass { background: #d4edda; color: #155724; }
  .fail { background: #f8d7da; color: #721c24; }
  .review { background: #fff3cd; color: #856404; }
  .error { background: #e2d5f8; color: #4a2a8f; }
  .skipped { background: #e9ecef; color: #495057; }
  img.shot { max-width: 240px; border: 1px solid #ccc; border-radius: 6px; }
  .score { font-size: 1.2rem; font-weight: 700; }
  .failed-steps { color: #721c24; }
</style></head>
<body>
<h1>JEV UI Checking — {{ report.flow_name }}</h1>
<p class="meta">Run <b>{{ report.run_id }}</b> · bắt đầu {{ report.started_at }}
   · {{ report.checkpoints | length }} checkpoint</p>
{% if report.failed_steps %}
<div class="card"><h2>Failed steps</h2>
  <ul class="failed-steps">{% for s in report.failed_steps %}<li>{{ s }}</li>{% endfor %}</ul>
</div>
{% endif %}
{% for cp in report.checkpoints %}
<div class="card">
  <h2>{{ cp.checkpoint }}
    {% if cp.screen_score is not none %}
      <span class="score">· {{ "%.4f" | format(cp.screen_score) }}</span>
    {% endif %}</h2>
  {% if cp.error %}<p class="failed-steps">Lỗi capture: {{ cp.error }}</p>{% endif %}
  {% if cp.screenshot %}<img class="shot" src="{{ cp.screenshot }}" alt="{{ cp.checkpoint }}">{% endif %}
  <table><tr><th>Check</th><th>Nhóm</th><th>Path</th><th>Verdict</th>
    <th>Score</th><th>Confidence</th></tr>
  {% for r in cp.results %}
    <tr><td>{{ r.check_id }}</td><td>{{ r.group }}</td><td>{{ r.path }}</td>
      <td><span class="{{ badges[r.verdict] }}">{{ r.verdict.value }}</span></td>
      <td>{% if r.score is not none %}{{ "%.3f" | format(r.score) }}{% endif %}</td>
      <td>{% if r.confidence is not none %}{{ "%.2f" | format(r.confidence) }}{% endif %}</td></tr>
  {% endfor %}</table>
  <details><summary>Evidence</summary>
    {% for r in cp.results %}
      {% if r.evidence %}<p><b>{{ r.check_id }}</b>: <code>{{ r.evidence }}</code></p>{% endif %}
      {% if r.error %}<p class="failed-steps"><b>{{ r.check_id }}</b>: {{ r.error }}</p>{% endif %}
    {% endfor %}
  </details>
</div>
{% endfor %}
<div class="card"><h2>Chi phí</h2><pre>{{ report.costs | tojson(indent=2) }}</pre></div>
</body></html>
"""

_env = Environment(autoescape=True)


def render_html(report: RunReport) -> str:
    return _env.from_string(_TEMPLATE).render(report=report, badges=_BADGES)
