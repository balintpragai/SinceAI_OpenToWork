"""Auditor exports: Excel workbooks for answers, conversations, the audit log and dashboard charts. Read-only.
Every sheet carries the approval banner; unapproved content is exportable but marked DRAFT (approved 2026-11-07)."""
from __future__ import annotations

import hashlib
import io
import json

import pandas as pd

from . import gold, review

DISCLAIMER = "Synthetic data (Apetit × Since AI 2026 challenge twin). Not the company's real emissions."
MAX_ROWS = 5000  # per data sheet
MAX_CELL = 32000  # Excel's hard limit is 32,767 characters per cell


def run_stamp() -> dict:
    """The pipeline run the data comes from, so an auditor can reproduce it."""
    if "gold_run_manifest" not in gold.delta_tables():
        return {"run_id": "no pipeline run (uncleaned raw data)"}
    m = gold.frame("gold_run_manifest").sort_values("finished").iloc[-1]
    return {"run_id": m["run_id"], "git_commit": m["git_commit"], "run_finished": m["finished"],
            "inputs_sha256": m["inputs_sha256"], "n_input_files": int(m["n_input_files"]),
            "reference_check_ok": bool(m["reference_check_ok"]), "inventory_status": m["sign_off_status"]}


def banner(r: dict | None) -> str:
    """Approval stamp for one decision (None = no decision yet)."""
    if not r:
        return "DRAFT – NOT APPROVED"
    when = str(r.get("ts", ""))[:10]
    return {"approved": f"APPROVED by {r['reviewer']}, {when}", "edited": f"APPROVED WITH EDITS by {r['reviewer']}, {when}",
            "rejected": f"REJECTED by {r['reviewer']}, {when} – not for reliance"}.get(r.get("status"), "DRAFT – NOT APPROVED")


def is_approved(r: dict | None) -> bool:
    return bool(r) and r.get("status") in ("approved", "edited")


def content_hash(answer: str, evidence: str) -> str:
    return hashlib.sha256(f"{answer}\n---\n{evidence}".encode()).hexdigest()


# ---- locating an answer -----------------------------------------------------------------------------------------

def find_answer(thread_id: str = "", answer_id: str = "", question_id: str = "") -> dict:
    """A chat answer (thread_id + answer_id) or an answer-sheet draft (question_id), as one flat dict. KeyError if missing."""
    if question_id:
        d = review.load_drafts()[question_id]
        res, r = d.get("full") or {}, d.get("review")
        return {"question": res.get("question") or question_id, "answer": (r or {}).get("final_answer") or d.get("answer", ""),
                "evidence": (r or {}).get("final_evidence") or d.get("evidence", "") or res.get("technical", ""),
                "result": res, "review": r, "ref": f"answer sheet {question_id}"}
    conv = review.load_conv(thread_id)
    if conv is None:
        raise KeyError(thread_id)
    msgs = conv["messages"]
    i = next(i for i, m in enumerate(msgs) if m["id"] == answer_id)  # StopIteration -> caller maps to 404
    m, res = msgs[i], msgs[i]["result"] or {}
    asked = next((x["content"] for x in reversed(msgs[:i]) if x["role"] == "user"), res.get("question", ""))
    r = m.get("review")
    return {"question": asked, "answer": (r or {}).get("final_answer") or m["content"],
            "evidence": (r or {}).get("final_evidence") or res.get("technical", ""), "result": res, "review": r,
            "ref": f"conversation {thread_id} · answer {answer_id}"}


def answer_summary(a: dict) -> dict:
    """What every answer export (Excel or PDF) states about the answer. Shared so both carry the same stamp and hash."""
    r = a["review"] or {}
    return {"status": banner(a["review"]), "approved": is_approved(a["review"]), "question": a["question"],
            "answer": a["answer"], "technical_evidence": a["evidence"], "reviewer": r.get("reviewer", ""),
            "decided_at": r.get("ts", ""), "model": a["result"].get("model", ""), "reference": a["ref"],
            "content_sha256": content_hash(a["answer"], a["evidence"]), "exported_at": review.now(),
            **run_stamp(), "note": DISCLAIMER}


# ---- workbook writer --------------------------------------------------------------------------------------------

def _cell(v):
    if isinstance(v, (dict, list)):
        v = json.dumps(v, default=str, ensure_ascii=False)
    return v[:MAX_CELL] if isinstance(v, str) else v


def workbook(sheets: dict[str, pd.DataFrame], stamp: str, approved: bool) -> bytes:
    """One sheet per frame, each under a two-line banner (approval stamp + disclaimer); red tabs when not approved."""
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    buf = io.BytesIO()
    color = "2F7D4F" if approved else "B3412E"
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df = df.head(MAX_ROWS).map(_cell) if len(df.columns) else pd.DataFrame({"": []})
            df.to_excel(xw, sheet_name=name[:31], index=False, startrow=3)
            ws = xw.sheets[name[:31]]
            ws["A1"], ws["A2"] = stamp, DISCLAIMER
            ws["A1"].font = Font(bold=True, size=13, color="FFFFFF")
            ws["A1"].fill = PatternFill("solid", fgColor=color)
            ws["A2"].font = Font(italic=True, color="5C6862")
            ws.sheet_properties.tabColor = color
            ws.freeze_panes = "A5"
            if len(df):
                ws.auto_filter.ref = f"A4:{get_column_letter(len(df.columns))}{len(df) + 4}"
            for i, col in enumerate(df.columns, 1):
                width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)])
                ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 80)
    return buf.getvalue()


def _kv(d: dict) -> pd.DataFrame:
    return pd.DataFrame({"Field": [k.replace("_", " ").capitalize() for k in d], "Value": list(d.values())})


def _result_table(res) -> list[dict] | None:
    """The tabular part of a tool result (SQL rows, inventory lines, records, chart rows)."""
    if isinstance(res, dict):
        for k in ("rows", "lines", "records"):
            if isinstance(res.get(k), list) and res[k] and isinstance(res[k][0], dict):
                return res[k]
    return None


# ---- the four exports -------------------------------------------------------------------------------------------

def answer_xlsx(a: dict) -> bytes:
    s = answer_summary(a)
    trace = a["result"].get("trace", [])
    sheets = {
        "Summary": _kv(s),
        "Sources": pd.DataFrame(a["result"].get("sources") or [], columns=["label", "file", "detail"]),
        "Checks": pd.DataFrame([{"step": i + 1, "tool": t.get("tool"), "arguments": t.get("args"), "duration_ms": t.get("ms"),
                                 "rows_returned": len(_result_table(t.get("result")) or [])} for i, t in enumerate(trace)],
                               columns=["step", "tool", "arguments", "duration_ms", "rows_returned"]),
        "Citations": pd.DataFrame(a["result"].get("citations") or [], columns=["citation", "valid"]),
    }
    for i, t in enumerate(trace):
        if rows := _result_table(t.get("result")):
            sheets[f"Data {i + 1} {t.get('tool')}"] = pd.DataFrame(rows)
    return workbook(sheets, s["status"], s["approved"])


def conversation_xlsx(thread_id: str) -> bytes:
    conv = review.load_conv(thread_id)
    if conv is None:
        raise KeyError(thread_id)
    rows = []
    for m in conv["messages"]:
        if m["role"] != "assistant":
            continue
        a = find_answer(thread_id, m["id"])
        rows.append({"question": a["question"], "answer": a["answer"], "status": banner(a["review"]),
                     "reviewer": (a["review"] or {}).get("reviewer", ""), "decided_at": (a["review"] or {}).get("ts", ""),
                     "checks_run": len(a["result"].get("trace", [])),
                     "sources": " · ".join(x["label"] for x in a["result"].get("sources") or []),
                     "content_sha256": content_hash(a["answer"], a["evidence"]), "answer_id": m["id"]})
    n_ok = sum(r["status"].startswith("APPROVED") for r in rows)
    stamp = f"CONVERSATION – {n_ok} of {len(rows)} answers approved" + ("" if rows and n_ok == len(rows) else " – DRAFT CONTENT INCLUDED")
    info = {"conversation": conv.get("title", ""), "thread_id": thread_id, "started": conv.get("created", ""),
            "exported_at": review.now(), **run_stamp()}
    return workbook({"Answers": pd.DataFrame(rows), "Run": _kv(info)}, stamp, bool(rows) and n_ok == len(rows))


def audit_xlsx() -> bytes:
    """The full audit log, oldest first, with the tools each decision's answer used (the raw trace stays in the CSV)."""
    d = pd.read_csv(review.AUDIT, dtype=str).fillna("") if review.AUDIT.exists() else pd.DataFrame(columns=review.COLS)

    def tools_used(raw: str) -> str:
        try:
            return ", ".join(t.get("tool", "") for t in json.loads(raw or "[]"))
        except (json.JSONDecodeError, AttributeError):
            return ""
    d["tools_used"] = d["trace"].map(tools_used)
    d = d.drop(columns=["trace"])
    info = {"entries": len(d), "exported_at": review.now(), "source_file": "outputs/audit_log.csv", **run_stamp()}
    return workbook({"Audit log": d, "Run": _kv(info)}, f"AUDIT LOG – {len(d)} review decisions", True)


def chart_xlsx(chart: dict) -> bytes:
    status = chart.get("status") or "draft"
    info = {k: chart.get(k) for k in ("title", "year", "unit", "status", "note")} | {
        "sources": " · ".join(chart.get("sources", [])), "tables": ", ".join(chart.get("tables", [])),
        "exported_at": review.now(), **run_stamp()}
    stamp = "PUBLISHED INVENTORY" if status == "published" else "DRAFT INVENTORY – NOT SIGNED OFF"
    return workbook({"Data": pd.DataFrame(chart.get("rows", [])), "About": _kv(info)}, stamp, status == "published")
