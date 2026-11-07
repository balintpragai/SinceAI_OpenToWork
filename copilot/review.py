"""Expert review: drafts, decisions and the audit log. Nothing reaches the submission without a human decision."""
import csv
import os
import re
import json
from datetime import datetime, timezone

import pandas as pd

from . import data

OUT = data.OUT
AUDIT = OUT / "audit_log.csv"
DRAFTS = OUT / "e_drafts.json"
SUBMISSION = OUT / "E_answers_submission.csv"
COLS = ["timestamp_utc", "reviewer", "source", "question_id", "question", "decision", "final_answer",
        "final_evidence", "model", "citations", "trace"]
DECISIONS = ("approved", "edited", "rejected")


def _write_json(path, obj):
    """Atomic write: a crash mid-write never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str))
    os.replace(tmp, path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_decision(reviewer, source, qid, res, decision, final_answer, final_evidence=""):
    """Append one row to the audit log (header created if missing)."""
    OUT.mkdir(exist_ok=True)
    new = not AUDIT.exists() or AUDIT.stat().st_size == 0
    row = [now(), reviewer, source, qid or "", res.get("question", ""), decision, final_answer, final_evidence or "",
           res.get("model", ""), json.dumps(res.get("citations", [])),
           json.dumps(res.get("trace", []), separators=(",", ":"), default=str)]
    with AUDIT.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow(row)


def audit_rows() -> list[dict]:
    if not AUDIT.exists():
        return []
    d = pd.read_csv(AUDIT, dtype=str).fillna("")
    return d.drop(columns=["trace"], errors="ignore").iloc[::-1].to_dict("records")


def load_drafts() -> dict:
    return json.loads(DRAFTS.read_text()) if DRAFTS.exists() else {}


def save_drafts(d: dict):
    _write_json(DRAFTS, d)


def stamp(reviewer, status, answer, evidence=None) -> dict:
    return {"status": status, "reviewer": reviewer, "ts": now(), "final_answer": answer, "final_evidence": evidence}


def export_submission(drafts: dict) -> tuple[int, int]:
    """Write E_answers_submission.csv for ALL drafts; only approved/edited get an answer. Returns (n_approved, n_total)."""
    rows, n = [], 0
    for qid, d in drafts.items():
        r = d.get("review")
        ok = bool(r) and r["status"] in ("approved", "edited")
        n += ok
        rows.append({"question_id": qid, "answer": r["final_answer"] if ok else "",
                     "evidence": (r.get("final_evidence") or "") if ok else ""})
    OUT.mkdir(exist_ok=True)
    pd.DataFrame(rows, columns=["question_id", "answer", "evidence"]).to_csv(SUBMISSION, index=False)
    return n, len(drafts)


# ---- conversations (one JSON file per thread, so chats survive "New conversation" and server restarts) ----

CONV = OUT / "conversations"


def valid_thread_id(thread_id: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", thread_id or ""))  # ids are used as file names


def load_conv(thread_id: str) -> dict | None:
    if not valid_thread_id(thread_id):
        return None
    p = CONV / f"{thread_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def save_conv(conv: dict):
    conv["updated"] = now()
    _write_json(CONV / f"{conv['thread_id']}.json", conv)


def list_convs() -> list[dict]:
    if not CONV.exists():
        return []
    out = []
    for p in CONV.glob("*.json"):
        try:  # one damaged file must not take down the sidebar
            c = json.loads(p.read_text())
            out.append({k: c.get(k, "") for k in ("thread_id", "title", "created", "updated")} | {"n_messages": len(c["messages"])})
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            continue
    return sorted(out, key=lambda c: c["updated"], reverse=True)
