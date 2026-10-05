from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from jev_ui_agent.checks.composite import apply_confidence_gate
from jev_ui_agent.jev.client import JevClient, JevError
from jev_ui_agent.jev.rule_questions import build_questions
from jev_ui_agent.langtag import LANG_PLACEHOLDER, detect_language_tag, language_name
from jev_ui_agent.models import CheckResult, CheckpointReport, RunReport, Verdict
from jev_ui_agent.pipeline import load_yaml
from jev_ui_agent.report.html import render_html
from jev_ui_agent.report.json_report import render_json
from jev_ui_agent.rules import load_rules
from jev_ui_agent.vision.claude_bridge import VisionBridge, VisionUnavailable

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
CHECKPOINT_FILE = "checkpoint.jsonl"
_ORDER = {"failed": 0, "needs_review": 1, "error": 2, "passed": 3}


def scan_images(directory: Path | str, recursive: bool = False) -> list[Path]:
    d = Path(directory)
    if not d.is_dir():
        raise NotADirectoryError(f"Không phải thư mục: {d}")
    it = d.rglob("*") if recursive else d.glob("*")
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in _IMAGE_EXTS)


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _image_status(cp: CheckpointReport) -> str:
    if cp.error:
        return "error"
    verdicts = {r.verdict for r in cp.results}
    if Verdict.FAIL in verdicts:
        return "failed"
    if Verdict.NEEDS_REVIEW in verdicts:
        return "needs_review"
    return "passed"


def _cp_from_record(rec: dict) -> CheckpointReport:
    rep = rec["report"]
    results = [CheckResult(verdict=Verdict(r["verdict"]),
                           **{k: v for k, v in r.items() if k != "verdict"})
               for r in rep.get("results", [])]
    return CheckpointReport(checkpoint=rep["checkpoint"], screen_score=rep.get("screen_score"),
                            results=results, screenshot=rep.get("screenshot", ""),
                            error=rep.get("error", ""))


def _judge_image(path: Path, rules: dict, jev: JevClient, vision: VisionBridge,
                 gate: float) -> CheckpointReport:
    cp = CheckpointReport(checkpoint=path.name, screenshot=str(path).replace("\\", "/"))
    try:
        observation = vision.observe_detailed(str(path))
        # Rule chứa {language} được tham số hóa theo đuôi tên file (vd '-en').
        # Ảnh không có tag -> các rule đó SKIPPED kèm lý do, không hỏi JEV.
        tag = detect_language_tag(path.name)
        lang = language_name(tag) if tag else None
        prepared: list[tuple[dict, CheckResult | None]] = []
        for rule in rules["rules"]:
            instruction = rule["instruction"]
            if LANG_PLACEHOLDER in instruction:
                if lang is None:
                    prepared.append((rule, CheckResult(
                        f"rule/{rule['id']}", "rules", "vision+jev", Verdict.SKIPPED,
                        evidence={"instruction": instruction, "skipped":
                                  "filename has no -<lang> suffix; expected language unknown"})))
                    continue
                rule = {**rule, "instruction": instruction.replace(LANG_PLACEHOLDER, lang)}
            prepared.append((rule, None))
        asked = [rule for rule, skipped in prepared if skipped is None]
        payload = {"image": path.name, "screen_observation": observation}
        answers = jev.judge(payload, build_questions(asked)) if asked else {}
        results: list[CheckResult] = []
        for rule, skipped in prepared:
            if skipped is not None:
                results.append(skipped)
                continue
            ans = answers.get(rule["id"])
            if ans is None:
                results.append(CheckResult(f"rule/{rule['id']}", "rules", "vision+jev",
                                           Verdict.ERROR, error="missing answer"))
                continue
            if rule["type"] == "noul":
                satisfied = (ans.get("value") or 0.0) >= 0.5
                r = CheckResult(f"rule/{rule['id']}", "rules", "vision+jev",
                                Verdict.PASS if satisfied else Verdict.FAIL,
                                confidence=ans.get("confidence"),
                                evidence={"noul": ans.get("value"),
                                          "instruction": rule["instruction"]})
            else:
                norm = (ans.get("value") or 0.0) / 4.0
                r = CheckResult(f"rule/{rule['id']}", "rules", "vision+jev",
                                Verdict.PASS if norm >= rule.get("pass_at", 0.75) else Verdict.FAIL,
                                score=norm, confidence=ans.get("confidence"),
                                evidence={"raw_score": ans.get("value"),
                                          "instruction": rule["instruction"]})
            results.append(apply_confidence_gate(r, gate))
        cp.results = results
        values = [1.0 if v is Verdict.PASS else 0.0 if v is Verdict.FAIL else 0.5
                  for v in (r.verdict for r in results)
                  if v in (Verdict.PASS, Verdict.FAIL, Verdict.NEEDS_REVIEW)]
        cp.screen_score = round(sum(values) / len(values), 4) if values else None
    except (VisionUnavailable, JevError) as e:
        cp.error = f"{type(e).__name__}: {e}"
        return cp
    except Exception as e:  # noqa: BLE001 — 1 ảnh hỏng không được làm chết cả batch
        cp.error = f"Unexpected {type(e).__name__}: {e}"
        return cp
    return cp


def _status_counts(cps: list[CheckpointReport]) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "needs_review": 0, "error": 0}
    for cp in cps:
        counts[_image_status(cp)] += 1
    counts["errors"] = counts.pop("error")  # key public ở summary là số nhiều
    return counts


def run_batch(*, images_dir, rules_path, policy_path, out_root, workers: int = 4,
              limit: int | None = None, recursive: bool = True,
              resume_dir=None, jev: JevClient | None = None,
              vision: VisionBridge | None = None) -> RunReport:
    if jev is None or vision is None:
        raise ValueError("check-screenshots cần cả jev và vision client")
    policy = load_yaml(policy_path)
    rules = load_rules(rules_path)
    gate = float(policy.get("confidence_gate", 0.75))

    images = scan_images(images_dir, recursive)
    if limit is not None:
        images = images[: max(0, int(limit))]
    hashes = {p: sha256_file(p) for p in images}

    if resume_dir:
        out_dir = Path(resume_dir)
        if not out_dir.is_dir():
            raise ValueError(f"resume dir không tồn tại: {out_dir}")
        run_id = out_dir.name
    else:
        run_id = f"check-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        out_dir = Path(out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / CHECKPOINT_FILE

    done_by_hash: dict[str, dict] = {}
    if ckpt_path.exists():
        # errors="replace": kill giữa chừng có thể cắt cụt cả chuỗi UTF-8 ở dòng cuối
        for line in ckpt_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") == "done":
                    done_by_hash[rec["hash"]] = rec  # dòng sau đè dòng trước
            except (ValueError, AttributeError, KeyError, TypeError):
                # dòng hỏng/cắt cụt (kill giữa lúc write) — bỏ qua, ảnh đó sẽ được chạy lại
                continue

    unique: dict[str, Path] = {}
    for p in images:
        unique.setdefault(hashes[p], p)

    pending = [p for h, p in unique.items() if h not in done_by_hash]
    new_cps: dict[str, CheckpointReport] = {}
    # Append + flush ngay sau MỖI ảnh (spec luồng [4]e): kill giữa chừng chỉ mất
    # ảnh chưa xong — mọi ảnh đã xong đã nằm sẵn trong checkpoint.
    with open(ckpt_path, "a", encoding="utf-8") as ckpt:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(_judge_image, p, rules, jev, vision, gate): p
                       for p in pending}
            for fut in as_completed(futures):
                p = futures[fut]
                cp = fut.result()
                new_cps[hashes[p]] = cp
                rec = {"image": str(p), "hash": hashes[p],
                       "status": "error" if cp.error else "done",
                       "report": asdict(cp)}
                ckpt.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")
                ckpt.flush()

    cps: list[CheckpointReport] = []
    seen_hash: dict[str, str] = {}
    duplicates = 0
    for p in images:
        h = hashes[p]
        if h in seen_hash:
            duplicates += 1
            src = new_cps[h] if h in new_cps else _cp_from_record(done_by_hash[h])
            cp = CheckpointReport(checkpoint=p.name, screen_score=src.screen_score,
                                  results=[replace(r) for r in src.results],
                                  screenshot=str(p).replace("\\", "/"), error=src.error)
            if cp.results:
                first = cp.results[0]
                first.evidence = dict(first.evidence, duplicate_of=seen_hash[h])
            elif cp.error:
                cp.error = f"{cp.error} (duplicate của {seen_hash[h]})"
            cps.append(cp)
        else:
            seen_hash[h] = p.name
            cps.append(new_cps[h] if h in new_cps else _cp_from_record(done_by_hash[h]))

    # Ảnh bị xoá/không còn trong folder khi resume: giữ kết quả cũ trong report,
    # đánh dấu missing (spec: "ghi nhận missing") — không chạy lại, không mất kết quả.
    missing = 0
    for h, rec in done_by_hash.items():
        if h in unique:  # hash vẫn còn trong folder (unique keyed theo hash)
            continue
        cp = _cp_from_record(rec)
        if cp.results:
            cp.results[0].evidence = dict(cp.results[0].evidence, missing=True)
        cps.append(cp)
        missing += 1

    counts = _status_counts(cps)
    counts["duplicates"] = duplicates
    counts["total_images"] = len(images)
    counts["missing"] = missing
    counts["rules"] = len(rules["rules"])

    report = RunReport(run_id=run_id, flow_name=f"rules:{rules['name']}",
                       started_at=datetime.now().isoformat(timespec="seconds"),
                       checkpoints=sorted(cps, key=lambda c: _ORDER[_image_status(c)]),
                       summary=counts)
    report.costs["jev"] = dict(jev.usage)
    report.costs["vision"] = {"calls": vision.calls}

    (out_dir / "report.json").write_text(render_json(report), encoding="utf-8")
    (out_dir / "report.html").write_text(render_html(report), encoding="utf-8")
    return report
