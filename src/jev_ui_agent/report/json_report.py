from __future__ import annotations

import dataclasses
import json
from typing import Any

from jev_ui_agent.models import RunReport, Verdict


def _default(o: Any) -> str:
    if isinstance(o, Verdict):
        return o.value
    return str(o)


def render_json(report: RunReport) -> str:
    return json.dumps(dataclasses.asdict(report), default=_default,
                      indent=2, ensure_ascii=False)
