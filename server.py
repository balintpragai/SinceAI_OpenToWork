"""FastAPI backend for the copilot UI. Run: python3 -m uvicorn server:app --reload --port 8000

Streaming endpoints return NDJSON (one JSON object per line):
  {"type":"tool_start","id","tool","args"}  {"type":"tool_end","id","tool","args","result","ms"}
  {"type":"final", ...Copilot.ask() result...}  {"type":"error","message"}
"""
import json
import os
import queue
import threading
import traceback
import uuid

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from answer_e import ANS, FMT, parse
from copilot import data, review

app = FastAPI(title="Climate & Nature Navigator copilot")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

_threads: dict[str, object] = {}  # thread_id -> Copilot (one Gemini chat each)
_lock = threading.Lock()  # guards _threads and _busy
_store_lock = threading.Lock()  # guards drafts/conversation read-modify-write
_busy: set[str] = set()  # threads with an answer in progress


class _FakeCopilot:
    """COPILOT_FAKE=1: real tools, scripted 'model'. For UI work and offline demos; spends no Gemini quota."""
    on_event = None
    model = "fake (COPILOT_FAKE=1)"

    def ask(self, question: str, fresh: bool = False) -> dict:
        import time
        from copilot import tools
        from copilot.agent import check_citations
        trace = []
        for i, (fn, kw) in enumerate([(tools.get_inventory, {"year": 2024, "scope": "scope1"}),
                                      (tools.sql, {"query": "SELECT * FROM published_inventory_history WHERE year = 2024"})]):
            self.on_event and self.on_event({"type": "tool_start", "id": f"t{i}", "tool": fn.__name__, "args": kw})
            time.sleep(0.6)
            step = {"id": f"t{i}", "tool": fn.__name__, "args": kw, "result": fn(**kw), "ms": 600}
            trace.append(step)
            self.on_event and self.on_event({"type": "tool_end", **step})
        s1 = trace[0]["result"]["total_tco2e_by_scope"].get("scope1")
        text = (f"**Answer:** The uncleaned 2024 Scope 1 total is {s1:,.0f} tCO2e; the published figure is 6,251 tCO2e.\n\n"
                "**How:**\n- `get_inventory(2024, scope1)` on the naive baseline\n- `published_inventory_history` for 2024\n\n"
                "**Evidence:** refrigerant_service_log line S-SAK:R404A; [docs/METHODOLOGY.md#3. Scope 1 and 2]\n\n"
                "**Review:** Check the R404A top-up at S-SAK before using this number.\n\nANSWER: 6251\nEVIDENCE: "
                "published_inventory_history row 6; [docs/METHODOLOGY.md#3. Scope 1 and 2]")
        text = (f"*Demo mode: scripted answer, no model was called. You asked: \"{question.splitlines()[0][:200]}\"*\n\n" + text)
        return {"question": question, "answer": text, "trace": trace, "citations": check_citations(text),
                "data_status": ["naive"], "model": self.model, "tokens": {"prompt": 0, "cached": 0, "output": 0}}


def _copilot(thread_id: str):
    if os.environ.get("COPILOT_FAKE") == "1":
        return _threads.setdefault(thread_id, _FakeCopilot())
    if not (os.environ.get("FEATHERLESS_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        raise HTTPException(503, "No model API key set: add FEATHERLESS_API_KEY (or GEMINI_API_KEY) to .env.")
    from copilot.agent_openai import make_copilot  # lazy: builds the large system prompt
    with _lock:
        if thread_id not in _threads:  # resume a saved conversation after a restart
            conv = review.load_conv(thread_id) or {"messages": []}
            hist = [("user" if m["role"] == "user" else "model", m["content"]) for m in conv["messages"]]
            _threads[thread_id] = make_copilot(history=hist)
        return _threads[thread_id]


def _claim(thread_id: str):
    """One answer at a time per thread: a copilot's message history is not safe to share."""
    with _lock:
        if thread_id in _busy:
            raise HTTPException(409, "This conversation is still answering the previous question. Wait for it to finish.")
        _busy.add(thread_id)


def _stream(cp, prompt: str, fresh: bool, on_final=None, thread_id: str = ""):
    """Run cp.ask in a worker thread; yield its tool events live, then the final result."""
    q: queue.Queue = queue.Queue()

    def work():
        cp.on_event = q.put
        try:
            res = cp.ask(prompt, fresh=fresh)
            if on_final:
                res = on_final(res)
            q.put({"type": "final", **res})
        except Exception as e:  # quota, network, model errors -> shown in the UI, not a 500
            traceback.print_exc()
            q.put({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            cp.on_event = None
            with _lock:
                _busy.discard(thread_id)
            q.put(None)

    threading.Thread(target=work, daemon=True).start()
    while (ev := q.get()) is not None:
        yield json.dumps(ev, default=str) + "\n"


def _ndjson(gen):
    return StreamingResponse(gen, media_type="application/x-ndjson")


# ---- chat --------------------------------------------------------------------------------------

class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None


@app.post("/api/chat")
def chat(body: ChatIn):
    tid = body.thread_id or uuid.uuid4().hex
    if not review.valid_thread_id(tid):
        raise HTTPException(400, "invalid thread_id")
    cp = _copilot(tid)
    _claim(tid)

    def save(res):
        aid = uuid.uuid4().hex
        with _store_lock:
            conv = review.load_conv(tid) or {"thread_id": tid, "title": body.message.strip()[:60],
                                             "created": review.now(), "messages": []}
            conv["messages"] += [{"id": uuid.uuid4().hex, "role": "user", "content": body.message},
                                 {"id": aid, "role": "assistant", "content": res["answer"], "result": res, "review": None}]
            review.save_conv(conv)
        return {**res, "thread_id": tid, "answer_id": aid}

    return _ndjson(_stream(cp, body.message, fresh=False, on_final=save, thread_id=tid))


@app.get("/api/conversations")
def conversations():
    return review.list_convs()


@app.get("/api/conversations/{thread_id}")
def conversation(thread_id: str):
    conv = review.load_conv(thread_id)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    return conv


# ---- status, records ---------------------------------------------------------------------------

@app.get("/api/status")
def status():
    from copilot.agent_openai import current_model
    fake = os.environ.get("COPILOT_FAKE") == "1"
    from copilot import gold
    return {"model": _FakeCopilot.model if fake else current_model(), "fake": fake,
            "gemini_key": bool(os.environ.get("FEATHERLESS_API_KEY") or os.environ.get("GEMINI_API_KEY")),
            "gold_tables": list(gold.delta_tables()), "lakehouse": str(gold.LAKEHOUSE),
            "data_status": {y: "pipeline" if gold.has("line_items") else data.inventory(y)[1] for y in (2023, 2024, 2025)}}


@app.post("/api/reload")
def reload():
    data.reset_caches()
    from copilot import gold
    gold.reset()
    _threads.clear()
    return status()


@app.get("/api/records")
def records(key: str):
    res = data.lookup(key)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


# ---- E answer sheet ----------------------------------------------------------------------------

def _questions() -> pd.DataFrame:
    return pd.read_csv(data.CCN_ROOT / "tasks" / "E_questions.csv").fillna("")


@app.get("/api/questions")
def questions():
    drafts = review.load_drafts()
    out = []
    for q in _questions().to_dict("records"):
        d = drafts.get(q["question_id"], {})
        out.append({**q, "answer": d.get("answer", ""), "evidence": d.get("evidence", ""), "error": d.get("error"),
                    "full": d.get("full"), "review": d.get("review")})
    return out


@app.post("/api/questions/{qid}/run")
def run_question(qid: str, force: bool = False):
    qs = _questions()
    row = qs[qs.question_id == qid]
    if row.empty:
        raise HTTPException(404, f"unknown question {qid}")
    q = row.iloc[0].to_dict()
    if (review.load_drafts().get(qid) or {}).get("review") and not force:  # never silently drop a decision
        raise HTTPException(409, "This answer already has a review decision. Re-run with force=true to replace it.")

    def save(res):
        answer, evidence = parse(res["answer"])
        res = {**res, "answer_id": uuid.uuid4().hex}
        with _store_lock:
            drafts = review.load_drafts()
            drafts[qid] = {"question_id": qid, "kind": q["kind"], "question": q["question"], "unit": q["unit"],
                           "answer": answer, "evidence": evidence, "full": res, "review": None}
            review.save_drafts(drafts)
        return {**res, "parsed_answer": answer, "parsed_evidence": evidence}

    cp = _copilot(f"batch-{qid}")
    _claim(f"batch-{qid}")
    return _ndjson(_stream(cp, q["question"] + FMT.format(a=ANS[q["kind"]]), fresh=True, on_final=save,
                           thread_id=f"batch-{qid}"))


# ---- review ------------------------------------------------------------------------------------

class ReviewIn(BaseModel):
    reviewer: str
    answer_id: str  # each answer can be decided exactly once
    thread_id: str | None = None  # for chat answers
    decision: str  # approved | edited | rejected
    source: str = "chat"  # chat | answer_sheet
    question_id: str | None = None
    result: dict = {}  # ignored: the server uses its stored copy of the answer (client input is not trusted)
    final_answer: str = ""  # only used for 'edited'
    final_evidence: str = ""


@app.post("/api/review")
def post_review(body: ReviewIn):
    if not body.reviewer.strip():
        raise HTTPException(400, "Reviewer name is required.")
    if body.decision not in review.DECISIONS:
        raise HTTPException(400, f"decision must be one of {review.DECISIONS}")
    if body.decision == "edited" and not body.final_answer.strip():
        raise HTTPException(400, "An edited answer cannot be empty.")
    with _store_lock:  # check-and-set, so two clicks cannot both record a decision
        if body.question_id:
            store = review.load_drafts()
            target = store.get(body.question_id)
            if target is None or (target.get("full") or {}).get("answer_id") != body.answer_id:
                raise HTTPException(409, "This answer is no longer the current draft. Reload the answer sheet.")
        else:
            store = review.load_conv(body.thread_id or "")
            target = next((m for m in (store or {}).get("messages", []) if m["id"] == body.answer_id), None)
            if target is None:
                raise HTTPException(404, "answer not found in this conversation")
        if target.get("review"):
            r = target["review"]
            raise HTTPException(409, f"Already {r['status']} by {r['reviewer']} at {r['ts']}. Each answer gets one decision.")
        # The approved text is the stored model answer, never client-supplied text.
        result = target.get("full") if body.question_id else target.get("result")
        stored_answer = target.get("answer", "") if body.question_id else target.get("content", "")
        stored_evidence = target.get("evidence", "") if body.question_id else ""
        if body.decision == "edited":
            final, evidence = body.final_answer, body.final_evidence
        else:
            final, evidence = stored_answer, stored_evidence
        if body.decision == "approved" and not str(final).strip():
            raise HTTPException(400, "Nothing to approve: the draft has no parsed answer. Edit it or re-run it.")
        st = review.stamp(body.reviewer, body.decision, final, evidence)
        # Audit row first: if logging fails, no decision is stored without its audit trail.
        review.log_decision(body.reviewer, body.source, body.question_id, result or {}, body.decision, final, evidence)
        target["review"] = st
        review.save_drafts(store) if body.question_id else review.save_conv(store)
    return st


@app.get("/api/audit")
def audit():
    return review.audit_rows()


@app.post("/api/export")
def export():
    n, total = review.export_submission(review.load_drafts())
    return {"approved": n, "total": total, "path": data.rel(review.SUBMISSION)}
