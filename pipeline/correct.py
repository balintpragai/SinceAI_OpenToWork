"""S3 Corrected: apply corrections and estimates from the issue log, then reviewer decisions.

Issue status after S3:
  auto_applied  correction/estimate/method applied by a rule
  open          flagged issue, record keeps its original values
  accepted      a reviewer accepted the issue (approved_by set)
  rejected      a reviewer rejected the issue: no change, excluded from the A1 export
  overridden    a reviewer replaced the proposed value; the override is the correction
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

REVIEW_COLUMNS = ["decision_id", "issue_id", "decision", "override_field", "override_value", "reviewer",
                  "decided_at", "comment"]


def empty_review_decisions() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="string") for c in REVIEW_COLUMNS})


def _latest_decisions(reviews: pd.DataFrame) -> dict[str, dict]:
    if reviews is None or reviews.empty:
        return {}
    r = reviews[reviews.decision.isin(["accept", "reject", "override"])].copy()
    r = r.sort_values("decided_at")
    return {row["issue_id"]: row for row in r.to_dict("records")}


def _as_value(v):
    if isinstance(v, str):
        try:
            f = float(v)
            return int(f) if f.is_integer() and "." not in v else f
        except ValueError:
            return v
    return v


def stage_s3(s1: dict[str, pd.DataFrame], issues: pd.DataFrame, reviews: pd.DataFrame | None, run_id: str):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    decisions = _latest_decisions(reviews)
    tables = {}
    for name, df in s1.items():
        d = df.copy()
        d["is_excluded"] = False
        d["is_estimate"] = False
        d["has_flag"] = False
        tables[name] = d
    log_rows = []
    status = []
    for iss in issues.to_dict("records"):
        t = tables[iss["table"]]
        dec = decisions.get(iss["issue_id"])
        st = {"correct": "auto_applied", "estimate": "auto_applied", "method": "auto_applied", "flag": "open"}[iss["action"]]
        approved_by = None
        proposed_by = "pipeline"
        changes = dict(iss["changes"] or {})
        if dec is not None:
            if dec["decision"] == "reject":
                status.append(dict(issue_id=iss["issue_id"], status="rejected", reviewer=dec["reviewer"]))
                continue
            if dec["decision"] == "accept":
                st, approved_by = "accepted", dec["reviewer"]
            if dec["decision"] == "override":
                st, proposed_by, approved_by = "overridden", dec["reviewer"], dec["reviewer"]
                changes = {dec["override_field"] or iss["field"]: _as_value(dec["override_value"])}
                iss = {**iss, "drop": False, "new_row": None}
        status.append(dict(issue_id=iss["issue_id"], status=st, reviewer=approved_by))
        base = dict(issue_id=iss["issue_id"], record_key=iss["record_key"], table=iss["table"],
                    rule_or_model=iss["rule_id"] if proposed_by == "pipeline" else "reviewer_override",
                    evidence=iss["evidence"], proposed_by=proposed_by, approved_by=approved_by, timestamp=now,
                    status=st, run_id=run_id)
        kind = {"correct": "correction", "estimate": "estimate", "method": "method", "flag": None}[iss["action"]]
        if st == "overridden":
            kind = "correction"
        if kind is None:          # flagged issue: mark, keep original values
            idx = t.index[t.record_key == iss["record_key"]]
            t.loc[idx, "has_flag"] = True
            continue
        if iss.get("new_row"):
            row = dict(iss["new_row"])
            row.update(is_excluded=False, is_estimate=True, has_flag=False, _source_file=None, _source_row=None)
            tables[iss["table"]] = t = pd.concat([t, pd.DataFrame([row])], ignore_index=True)
            log_rows.append({**base, "kind": "estimate", "field": iss["field"], "old_value": None,
                             "new_value": iss["proposed_value"]})
            continue
        idx = t.index[t.record_key == iss["record_key"]]
        if len(idx) == 0:
            continue
        if iss["drop"]:
            t.loc[idx, "is_excluded"] = True
            log_rows.append({**base, "kind": kind, "field": "*", "old_value": "record", "new_value": "excluded"})
            continue
        if kind == "method":
            log_rows.append({**base, "kind": "method", "field": iss["field"], "old_value": iss["observed_value"],
                             "new_value": iss["proposed_value"]})
            continue
        for fld, val in changes.items():
            old = t.loc[idx[0], fld] if fld in t.columns else None
            if fld not in t.columns:
                t[fld] = pd.Series([None] * len(t), dtype=object)
            if isinstance(val, str) or pd.api.types.is_bool_dtype(t[fld]) is False and isinstance(val, bool):
                t[fld] = t[fld].astype(object)
            elif pd.api.types.is_integer_dtype(t[fld]) and isinstance(val, float) and not float(val).is_integer():
                t[fld] = t[fld].astype(float)
            t.loc[idx, fld] = val
            log_rows.append({**base, "kind": kind, "field": fld,
                             "old_value": None if old is None or (isinstance(old, float) and np.isnan(old)) else str(old),
                             "new_value": None if val is None else str(val)})
        if kind == "estimate":
            t.loc[idx, "is_estimate"] = True
    corr = pd.DataFrame(log_rows)
    st = pd.DataFrame(status)
    return tables, corr, st
