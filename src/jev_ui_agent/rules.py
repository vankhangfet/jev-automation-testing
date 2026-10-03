from __future__ import annotations

import re
from pathlib import Path

import yaml

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_TYPES = {"noul", "score"}

DEFAULT_SCORE_CRITERIA = [
    "Completely fails the requirement.",
    "Major problems: the requirement is mostly violated.",
    "Some violations of the requirement are visible.",
    "Minor issues only; the requirement is mostly met.",
    "Fully satisfies the requirement.",
]


class RulesError(ValueError):
    pass


def load_rules(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        raise RulesError(f"Rules file không tồn tại: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as e:
        raise RulesError(f"Không đọc/parse được rules file: {e}") from e
    if (not isinstance(raw, dict) or not isinstance(raw.get("name"), str)
            or not raw["name"].strip() or not isinstance(raw.get("rules"), list) or not raw["rules"]):
        raise RulesError("Rules file phải có 'name' và 'rules' là danh sách không rỗng")
    seen: set[str] = set()
    out: list[dict] = []
    for i, item in enumerate(raw["rules"]):
        if not isinstance(item, dict):
            raise RulesError(f"Rule {i} không hợp lệ: {item!r}")
        rid = item.get("id")
        if not isinstance(rid, str) or not _ID_RE.match(rid):
            raise RulesError(f"Rule {i}: id phải là slug (chữ thường, số, '.', '_', '-'), got {rid!r}")
        if rid in seen:
            raise RulesError(f"Rule id bị trùng: {rid!r}")
        seen.add(rid)
        instruction = item.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise RulesError(f"Rule {rid!r}: cần 'instruction' không rỗng")
        rtype = item.get("type", "noul")
        if rtype not in _TYPES:
            raise RulesError(f"Rule {rid!r}: type phải thuộc {sorted(_TYPES)}, got {rtype!r}")
        rule = {"id": rid, "instruction": instruction.strip(), "type": rtype}
        if rtype == "score":
            criteria = item.get("criteria") or DEFAULT_SCORE_CRITERIA
            if not isinstance(criteria, list) or len(criteria) != 5:
                raise RulesError(f"Rule {rid!r}: criteria (nếu có) phải là đúng 5 mức")
            rule["criteria"] = [str(c) for c in criteria]
            try:
                pass_at = float(item.get("pass_at", 0.75))
            except (TypeError, ValueError) as e:
                raise RulesError(f"Rule {rid!r}: pass_at phải là số") from e
            if not 0.0 <= pass_at <= 1.0:
                raise RulesError(f"Rule {rid!r}: pass_at phải trong [0, 1]")
            rule["pass_at"] = pass_at
        out.append(rule)
    return {"name": raw["name"].strip(), "rules": out}
