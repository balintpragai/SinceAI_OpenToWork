"""Auditor exports (copilot/export.py): banner follows the review decision, workbooks carry the evidence. Uses a temp
store, never outputs/."""
import io
import json

import pytest
from openpyxl import load_workbook

from copilot import export, review

TID = "a" * 32


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CONV", tmp_path / "conversations")
    monkeypatch.setattr(review, "AUDIT", tmp_path / "audit_log.csv")
    monkeypatch.setattr(review, "OUT", tmp_path)
    res = {"question": "Scope 1 in 2025?", "technical": "**Evidence:** eli:2025:1", "model": "test",
           "sources": [{"label": "Emission calculation (data pipeline)", "file": "lakehouse: gold_emission_line_items", "detail": "2025"}],
           "citations": [{"citation": "docs/METHODOLOGY.md#3", "valid": True}],
           "trace": [{"id": "t0", "tool": "sql", "args": {"query": "SELECT 1"}, "ms": 5,
                      "result": {"rows": [{"scope": "scope1", "tco2e": 4414.0}]}}]}
    conv = {"thread_id": TID, "title": "t", "created": "2026-11-07", "messages": [
        {"id": "u1", "role": "user", "content": "Scope 1 in 2025?"},
        {"id": "m1", "role": "assistant", "content": "**About 4,414 t CO₂e.**", "result": res, "review": None}]}
    review.save_conv(conv)
    return conv


def _sheets(content: bytes):
    return load_workbook(io.BytesIO(content))


def test_unreviewed_answer_is_marked_draft(store):
    wb = _sheets(export.answer_xlsx(export.find_answer(TID, "m1")))
    assert {"Summary", "Sources", "Checks", "Citations", "Data 1 sql"} <= set(wb.sheetnames)
    assert all(wb[s]["A1"].value == "DRAFT – NOT APPROVED" for s in wb.sheetnames)
    assert wb["Data 1 sql"]["B5"].value == 4414.0  # header on row 4, first data row on 5


def test_approved_answer_carries_reviewer_and_hash(store):
    store["messages"][1]["review"] = review.stamp("Auditor A", "approved", "**About 4,414 t CO₂e.**")
    review.save_conv(store)
    a = export.find_answer(TID, "m1")
    s = export.answer_summary(a)
    assert s["status"].startswith("APPROVED by Auditor A") and s["approved"]
    assert _sheets(export.answer_xlsx(a))["Summary"]["A1"].value == s["status"]
    assert s["content_sha256"] != export.content_hash("**About 4,415 t CO₂e.**", a["evidence"])


def test_rejected_is_not_for_reliance(store):
    assert "not for reliance" in export.banner(review.stamp("B", "rejected", "x"))


def test_conversation_and_audit_exports(store):
    wb = _sheets(export.conversation_xlsx(TID))
    assert wb["Answers"]["A1"].value.startswith("CONVERSATION – 0 of 1 answers approved")
    review.log_decision("Auditor A", "chat", "", {"question": "q", "trace": store["messages"][1]["result"]["trace"]}, "approved", "ans")
    ws = _sheets(export.audit_xlsx())["Audit log"]
    header = [c.value for c in ws[4]]
    assert "tools_used" in header and "trace" not in header
    assert ws.cell(5, header.index("tools_used") + 1).value == "sql" and ws.max_row == 5


def test_missing_answer_raises(store):
    with pytest.raises(StopIteration):
        export.find_answer(TID, "nope")
    with pytest.raises(KeyError):
        export.find_answer("b" * 32, "m1")
