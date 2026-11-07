"""Data review (web app): every issue the pipeline found, traced from source file to footprint, read from the lakehouse.

Reads Gold and stage tables only (copilot/gold.py); never imports pipeline code. Built once per pipeline run
(gold_run_manifest.run_id) and served as JSON by server.py at /api/footprint/{run|inventory|issues}:

  run        run manifest, processing counts, rule catalogue, self-check scores, applied review decisions
  inventory  per year x scope x category: tCO2e after fixes (gold_inventory_summary) and as recorded
             (gold_inventory_summary_as_recorded)
  issues     gold_issues with each issue's effect (gold_issue_effects) and its trace: raw file + row, bronze row,
             S1 changes, S3 corrections and flags, S4 lineage, Gold line items after fixes and as recorded
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from . import data, gold

SCHEMA = "ccn-review/1"
LINE_COLUMNS = ["scope", "category", "line_item", "component", "activity_value", "activity_unit", "factor_id",
                "factor_value", "factor_unit", "basis", "allocation", "tco2e"]
BOUNDARY_SOURCES = {"energy_meter_readings", "waste_transfer_notes", "sales_volumes"}
_META = {"record_key", "_source_file", "_source_row", "run_id", "is_excluded", "is_estimate", "has_flag"}


def _v(x):
    """JSON-safe scalar: NaN/NA -> null, numpy -> python, floats to 10 significant digits."""
    if x is None or x is pd.NA or x is pd.NaT:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else float(f"{f:.10g}")
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.isoformat()
    if isinstance(x, dict):
        return {str(k): _v(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_v(v) for v in x]
    return x


def _same(a, b) -> bool:
    a, b = _v(a), _v(b)
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    return a == b


def _rows(df: pd.DataFrame, cols=None) -> list[dict]:
    d = df if cols is None else df[[c for c in cols if c in df.columns]]
    return [{k: _v(v) for k, v in r.items()} for r in d.to_dict("records")]


def _table(name: str) -> pd.DataFrame | None:
    return gold.frame(name) if name in gold.delta_tables() else None


def _count(name: str) -> int:
    from deltalake import DeltaTable
    return DeltaTable(str(gold.delta_tables()[name])).to_pyarrow_dataset().count_rows()


def current_run_id() -> str:
    if not gold.has("issues") or not gold.has("manifest"):
        raise LookupError("No pipeline output in the lakehouse yet. Run `python -m pipeline run` to build it.")
    return str(gold.frame(gold.GOLD["manifest"]).run_id.iloc[-1])


def payload() -> dict[str, bytes]:
    """{run|inventory|issues: JSON bytes} for the current pipeline run."""
    return _build(current_run_id())


def reset():
    _build.cache_clear()


def _fresh(df: pd.DataFrame | None, run_id: str) -> pd.DataFrame | None:
    """The table only if it was written by this run (a failed as-recorded step leaves last run's tables behind)."""
    if df is None or df.empty or "run_id" not in df.columns:
        return None
    return df if (df.run_id.astype(str) == run_id).all() else None


@lru_cache(maxsize=1)
def _build(run_id: str) -> dict[str, bytes]:
    G = gold.GOLD
    man = gold.frame(G["manifest"]).iloc[-1]
    meta = {"run_id": run_id, "git_commit": _v(man.get("git_commit")), "inputs_sha256": _v(man.get("inputs_sha256")),
            "started": _v(man.get("started")), "generated_at": _v(man.get("finished"))}
    gi = gold.frame(G["issues"])
    eli = gold.frame(G["line_items"])
    raw = _fresh(_table(G["line_items_raw"]), run_id)
    corr = _table(G["corrections"])
    corr = corr if corr is not None else pd.DataFrame(columns=["table", "record_key", "issue_id"])
    lineage = _table("s4_lineage")
    files = _table(G["files"])
    sha = dict(zip(files.file, files.sha256)) if files is not None else {}
    issue_tables = sorted(gi.table.unique())

    # ---------------------------------------------------------------- run
    s3_excl = s3_est = 0
    for t in issue_tables:
        s3t = _table(f"s3_{t}")
        if s3t is not None:
            s3_excl += int(s3t.is_excluded.sum()) if "is_excluded" in s3t else 0
            s3_est += int(s3t.is_estimate.sum()) if "is_estimate" in s3t else 0
    stages = [
        {"id": "raw", "counts": {"files": _v(man.get("n_input_files"))}},
        {"id": "bronze", "counts": {"records": sum(_count(n) for n in gold.delta_tables() if n.startswith("bronze_"))}},
        {"id": "s2", "counts": {"issues": len(gi)}},
        {"id": "s3", "counts": {"corrections": len(corr), "excluded": s3_excl, "estimated": s3_est}},
        {"id": "gold", "counts": {"line_items": len(eli), "reference_check_ok": _v(man.get("reference_check_ok"))}},
    ]
    cat = _table(G["catalog"])
    descr = {}
    if cat is not None and "table_description" in cat:
        d = cat[cat.table.astype(str).str.startswith("bronze_")].drop_duplicates("table")
        descr = {t[len("bronze_"):]: v for t, v in zip(d.table, d.table_description)}
    rules = gold.frame(G["rules"]) if gold.has("rules") else pd.DataFrame(columns=["rule_id", "table", "issue_type", "action", "description"])
    quality = _table(G["run_quality"])
    reviews = _table(G["reviews"])
    run = {"stages": stages,
           "sources": [{"source": t, "description": _v(v)} for t, v in descr.items()],
           "rules": [{"rule": r.rule_id, "table": r.table, "type": r.issue_type, "action": r.action, "description": r.description}
                     for r in rules.itertuples()],
           "coverage": {"rules": sorted({(r.issue_type, r.table) for r in rules.itertuples()})},
           "quality": _rows(quality, ["check", "years", "score", "f1", "precision", "recall"]) if quality is not None else [],
           "reviews": _rows(reviews) if reviews is not None and len(reviews) else []}

    # ---------------------------------------------------------------- inventory
    summ = gold.frame(G["summary"])
    summ_raw = _fresh(_table(G["summary_raw"]), run_id)
    t0 = {} if summ_raw is None else {(int(r.year), r.scope, r.category): r.tco2e for r in summ_raw.itertuples()}
    years = sorted(int(y) for y in summ.year.unique())
    dev_years = sorted({int(y) for q in run["quality"] if q.get("check") == "A2" for y in str(q.get("years", "")).split("-") if y.isdigit()})
    inventory = {"years": years, "dev_years": dev_years, "as_recorded_available": raw is not None,
                 "rows": [{"year": int(r.year), "scope": r.scope, "category": r.category, "t": _v(r.tco2e),
                           "t0": _v(t0.get((int(r.year), r.scope, r.category))) if raw is not None else None}
                          for r in summ.itertuples()]}

    # ---------------------------------------------------------------- issues
    eff = _fresh(_table(G["effects"]), run_id)
    by_issue: dict[str, dict[str, float]] = {}
    if eff is not None:
        for r in eff[eff.issue_id.notna()].itertuples():
            by_issue.setdefault(r.issue_id, {})[f"{r.scope}|{r.category}"] = by_issue.get(r.issue_id, {}).get(f"{r.scope}|{r.category}", 0.0) + r.dt_tco2e
    n_on_record = gi.groupby(["table", "record_key"]).issue_id.transform("size")
    keys = set(gi.record_key)

    def lines_by_record(df):
        if df is None:
            return {}
        d = df[df.record_key.isin(keys)]
        return {k: g for k, g in d.groupby(["source_table", "record_key"])}
    g_after, g_raw = lines_by_record(eli), lines_by_record(raw)

    def gold_of(table, key):
        a, b = g_after.get((table, key)), g_raw.get((table, key))
        if a is None and b is None:
            return None
        rows = lambda g: [[_v(v) for v in row] for row in g[[c for c in LINE_COLUMNS]].itertuples(index=False)] if g is not None else []
        return {"t": _v(float(a.tco2e.sum())) if a is not None else 0.0,
                "t0": (_v(float(b.tco2e.sum())) if b is not None else 0.0) if raw is not None else None,
                "lines": rows(a), "lines0": rows(b)}

    corr_by = {k: g for k, g in corr.groupby(["table", "record_key"])} if len(corr) else {}
    links: dict[str, list] = {}
    if lineage is not None:
        lin = lineage[lineage.source_key.isin(keys)]
        for r in lin[["derived_key", "source_key", "canonical_table"]].itertuples(index=False):
            links.setdefault(r.source_key, []).append([r.canonical_table, None if r.derived_key == r.source_key else r.derived_key])

    rec: dict[tuple, dict] = {}                      # (table, key) -> bronze row, s1 changes, s3 flags, file, row
    for t in issue_tables:
        b, s1, s3 = _table(f"bronze_{t}"), _table(f"s1_{t}"), _table(f"s3_{t}")
        tkeys = set(gi.record_key[gi.table == t])
        bi = b[b.record_key.isin(tkeys)].set_index("record_key") if b is not None else pd.DataFrame()
        s1i = s1[s1.record_key.isin(tkeys)].set_index("record_key") if s1 is not None else pd.DataFrame()
        s3i = s3[s3.record_key.isin(tkeys)].set_index("record_key") if s3 is not None else pd.DataFrame()
        any_file = str(b._source_file.dropna().iloc[0]) if b is not None and "_source_file" in b and b._source_file.notna().any() else None
        bcols = [c for c in (b.columns if b is not None else []) if c not in _META]
        for k in tkeys:
            brow = {c: _v(bi.at[k, c]) for c in bcols} if k in bi.index else None
            s1chg = {}
            if k in s1i.index:
                for c in s1i.columns:
                    if c in _META or c.startswith("_"):
                        continue
                    v = s1i.at[k, c]
                    if brow is None or c not in brow or not _same(brow[c], v):
                        if brow is not None:
                            s1chg[c] = _v(v)
            s3r = s3i.loc[k] if k in s3i.index else None
            file = (str(bi.at[k, "_source_file"]) if k in bi.index and "_source_file" in bi else None) or any_file
            row = _v(bi.at[k, "_source_row"]) if k in bi.index and "_source_row" in bi else None
            rec[(t, k)] = {"bronze": brow, "s1": s1chg, "file": f"data/{file}" if file else None, "row": row,
                           "excluded": bool(s3r.is_excluded) if s3r is not None else False,
                           "estimate": bool(s3r.is_estimate) if s3r is not None else False,
                           "flagged": bool(s3r.has_flag) if s3r is not None else False}

    dev_rows = {}
    try:
        key = pd.read_csv(data.CCN_ROOT / "tasks" / "dev" / "A1_dev_issue_labels_2023_2024.csv")
        for k, g in key.groupby("record_key"):
            dev_rows[k] = {"types": sorted(set(g.issue_type)), "true_value": _v(g.true_value.iloc[0]) if "true_value" in g else None,
                           "note": _v(g.note.iloc[0]) if "note" in g else None}
    except (OSError, KeyError, ValueError):
        pass

    out = []
    for i, r in enumerate(gi.to_dict("records")):
        t, k, iid = r["table"], r["record_key"], r["issue_id"]
        rc = rec.get((t, k), {})
        brow = rc.get("bronze")
        fld = _v(r.get("field"))
        bval = brow.get(fld) if brow and fld else None
        chg = corr_by.get((t, k))
        changes = _rows(chg, ["issue_id", "kind", "field", "old_value", "new_value", "rule_or_model", "proposed_by",
                              "approved_by", "status"]) if chg is not None else []
        lk = links.get(k, [])
        s4 = "excluded" if rc.get("excluded") else "in" if lk else "outside_boundary" if t in BOUNDARY_SOURCES else "direct"
        by = {sc: _v(v) for sc, v in by_issue.get(iid, {}).items()}
        year = _v(r.get("year"))
        dk = dev_rows.get(k)
        dev = None if year not in dev_years else {
            "in_key": bool(dk), "type_match": bool(dk and r["issue_type"] in dk["types"]), "key_types": dk["types"] if dk else [],
            "true_value": dk["true_value"] if dk else None, "note": dk["note"] if dk else None}
        out.append({
            "id": iid, "table": t, "record_key": k, "year": year, "type": r["issue_type"], "rule": r["rule_id"],
            "action": r["action"], "confidence": _v(r.get("confidence")), "field": fld,
            "observed": _v(r.get("observed_value")), "proposed": _v(r.get("proposed_value")), "evidence": _v(r.get("evidence")),
            "drop": _v(r.get("drop")), "status": _v(r.get("status")), "reviewer": _v(r.get("reviewer")),
            "effect": {"dt": _v(sum(by.values())) if raw is not None else None, "by": by, "shared_with": int(n_on_record.iloc[i]) - 1},
            "dev": dev,
            "trace": {"raw": {"file": rc.get("file"), "row": rc.get("row"), "sha256": sha.get(rc.get("file"))},
                      "bronze": {"value": _v(bval), "row": brow},
                      "s1": {"value": rc.get("s1", {}).get(fld, _v(bval)) if fld else None, "changes": rc.get("s1") or None},
                      "s3": {"changes": changes, "excluded": rc.get("excluded", False), "estimate": rc.get("estimate", False),
                             "flagged": rc.get("flagged", False)},
                      "s4": {"status": s4, "links": lk},
                      "gold": gold_of(t, k)}})
    issues = {"issues": out, "line_columns": LINE_COLUMNS}

    env = lambda kind, d: json.dumps({"schema": SCHEMA, "kind": kind, "run": meta, "data": d}, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False, default=str).encode()
    return {"run": env("run", run), "inventory": env("inventory", inventory), "issues": env("issues", issues)}
