"""Batch-answer the E questions with the copilot. Drafts only: the submission comes from approved answers in app.py."""
import argparse
import json
import re
import time

import pandas as pd

from copilot import data

DRAFTS = data.OUT / "e_drafts.json"
FMT = ("\n\nWrite the two-part answer as usual. Inside the TECHNICAL part (after the ---TECHNICAL--- line), end your reply "
       "with exactly two lines:\nANSWER: {a}\n"
       "EVIDENCE: <record keys, table+filter, and [path#Heading] citations, separated by '; '>")
ANS = {"numeric": "<number only, no units, no thousands separators, '.' as decimal>", "rubric": "<2-4 sentence answer>"}


def parse(text):
    """Last 'ANSWER:' / 'EVIDENCE:' line values, tolerating markdown bold/backticks. Missing -> ''."""
    def last(tag):
        m = re.findall(rf"^[\s>*_`#-]*{tag}\s*[:：]?[*_`]*\s*:?\s*(.*)$", text, re.M | re.I)
        return m[-1].strip().strip("*_` ") if m else ""
    return last("ANSWER"), last("EVIDENCE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--split", default="all", choices=["dev", "test", "all"])
    ap.add_argument("--sleep", type=float, default=15)
    a = ap.parse_args()
    qs = pd.read_csv(data.CCN_ROOT / "tasks" / "E_questions.csv").fillna("")
    if a.split != "all":
        qs = qs[qs["split"] == a.split]
    if a.only:
        qs = qs[qs["question_id"].isin(a.only.split(","))]
    from copilot.agent_openai import make_copilot  # after arg parsing so --help works without a key
    cp = make_copilot()
    data.OUT.mkdir(exist_ok=True)
    drafts = json.loads(DRAFTS.read_text()) if DRAFTS.exists() else {}
    for n, q in enumerate(qs.itertuples()):
        if n:
            time.sleep(a.sleep)
        d = {"question_id": q.question_id, "kind": q.kind, "question": q.question, "unit": q.unit,
             "answer": "", "evidence": "", "full": None, "review": None}
        try:
            d["full"] = cp.ask(q.question + FMT.format(a=ANS[q.kind]), fresh=True)
            d["answer"], d["evidence"] = parse(d["full"]["raw"])
            print(q.question_id, "->", d["answer"][:80] or "(parse failed)")
        except Exception as e:
            d["error"] = f"{type(e).__name__}: {e}"
            print(q.question_id, "ERROR", d["error"])
        drafts[q.question_id] = d
        DRAFTS.write_text(json.dumps(drafts, indent=1, default=str))
    rows = [{k: d[k] for k in ("question_id", "answer", "evidence")} for d in drafts.values()]
    pd.DataFrame(rows, columns=["question_id", "answer", "evidence"]).to_csv(data.OUT / "E_answers_draft.csv", index=False)
    dev = pd.DataFrame([{"question_id": r.question_id, "answer": drafts[r.question_id]["answer"]}
                        for r in qs.itertuples() if r.split == "dev" and r.question_id in drafts and drafts[r.question_id]["answer"]])
    if len(dev):
        from ccn_tools.score import score_e
        print(json.dumps(score_e(dev, pd.read_csv(data.CCN_ROOT / "tasks" / "dev" / "E_dev_answers.csv")), indent=1, default=str))


if __name__ == "__main__":
    main()
