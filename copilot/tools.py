"""Functions Gemini may call. Every number the copilot states must come out of one of these.
Type hints + docstrings become the Gemini function schemas, so keep them precise.
(No `from __future__ import annotations`: the Gemini SDK needs real type objects.)"""

import ast
import datetime
import math
import operator as op

import pandas as pd

from . import data, gold

MAX_ROWS = 25
KEY_COLS = ("record_key", "derived_key", "source_key", "eli_key", "key")


MAX_CELL = 1500  # characters per cell, so one long text field cannot flood the context or the trace


def clean(v, cap: int | None = MAX_CELL):
    """JSON-safe copy: NaN/NaT/inf -> None (browsers reject NaN), numpy scalars unwrapped, strings capped at `cap`
    (None = no cap, for the model's own answer text)."""
    if isinstance(v, dict):
        return {k: clean(x, cap) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x, cap) for x in v]
    if isinstance(v, str):
        return v[:cap] + "..." if cap and len(v) > cap else v
    if isinstance(v, (pd.Timestamp, datetime.date)):
        return None if pd.isna(v) else v.isoformat()
    if hasattr(v, "item") and not hasattr(v, "__len__"):  # numpy scalar
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _records(df: pd.DataFrame, n: int = MAX_ROWS) -> list[dict]:
    return clean(df.head(n).to_dict("records"))


def _share(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 2) if whole else None


def get_inventory(year: int, scope: str = "", category: str = "", contains: str = "") -> dict:
    """GHG inventory for a year: totals, reliability and the largest emission line items.

    Args:
        year: reporting year, e.g. 2025.
        scope: optional filter: scope1, scope2_location, scope2_market, scope3.
        category: optional substring of the category, e.g. 'cat01', 'cat04', 'fugitive', 'electricity'.
        contains: optional case-insensitive substring matched against line item text, ef_id, component or keys.

    Returns totals by scope, flagged_share_pct (share of tCO2e resting on records with an open data-quality
    flag), estimate_share_pct, status ('draft' unless signed off), and the line items. data_status 'naive'
    means the pipeline has not run: raw data is uncorrected and numbers can be badly wrong.
    """
    if gold.has("line_items"):
        li = gold.frame(gold.GOLD["line_items"])
        ycol = "year" if "year" in li.columns else None
        d = li[li[ycol] == int(year)] if ycol else li
        status, source = "pipeline", f"gold.{gold.GOLD['line_items']}"
    else:
        d, status = data.inventory(int(year))
        source = "reference_calculator on uncleaned raw data"
    if scope:
        d = d[d["scope"] == scope]
    if category:
        d = d[d["category"].astype(str).str.contains(category, case=False, na=False)]
    if contains:
        cols = [c for c in ("line_item", "record_key", "factor_id", "component", "category", "source_table", "basis") if c in d.columns]
        text = d[cols].astype(str).agg(" ".join, axis=1)
        d = d[text.str.contains(contains, case=False, regex=False)]
    total = float(d["tco2e"].sum())
    out = {"year": year, "data_status": status, "source": source, "n_lines": len(d),
           "total_tco2e_by_scope": d.groupby("scope")["tco2e"].sum().round(2).to_dict(),
           "status": signoff_status(int(year))}
    if status == "naive":
        out["warning"] = "Uncleaned baseline: raw-feed errors are not corrected. Do not use for reporting."
    else:
        if "flagged" in d.columns:
            out["flagged_share_pct"] = _share(float(d.loc[d["flagged"].astype(bool), "tco2e"].sum()), total)
        if "is_estimate" in d.columns:
            out["estimate_share_pct"] = _share(float(d.loc[d["is_estimate"].astype(bool), "tco2e"].sum()), total)
        if "flag_tco2e" in d.columns:
            out["flag_tco2e"] = round(float(d["flag_tco2e"].sum()), 2)
    out["lines"] = _records(d.sort_values("tco2e", ascending=False), 40)
    return out


def signoff_status(year: int) -> str:
    """Export status for the year from the pipeline's export manifest (published only after sign-off)."""
    if not gold.has("exports"):
        return "draft (no sign-off recorded)"
    m = gold.frame(gold.GOLD["exports"])
    m = m[m["year"].astype(str) == str(year)]
    if len(m) and (m["status"] == "published").all():
        who = ", ".join(sorted(set(m["signed_off_by"].dropna().astype(str))))
        return f"published (signed off by {who})"
    return "draft (no sign-off recorded)" if len(m) else "no export for this year (dev/history year)"


def sql(query: str, limit: int = 50) -> dict:
    """Run ONE read-only SQL query (DuckDB dialect) over the tables listed under TABLES.

    Args:
        query: a single SELECT or WITH statement, e.g.
            "SELECT site_id, SUM(value) AS mwh FROM energy_meter_readings WHERE year = 2025 GROUP BY site_id".
            Quote odd column names with double quotes, e.g. "skördeår".
        limit: max rows to return (default 50).

    Returns columns, rows, whether the result was truncated, the layer (gold/raw) of each table used, and
    record keys found in the result. Errors come back as {'error': ...}; fix the query and retry.
    """
    try:
        df = gold.run_sql(query, limit)
    except Exception as e:  # surface SQL errors so the model can fix its query
        return {"error": f"{type(e).__name__}: {e}"}
    used = {t: gold.layer(t) for t in (set(gold.delta_tables()) or set(data.table_paths()))
            if f" {t.lower()}" in f" {query.lower()}".replace("(", " ").replace(",", " ").replace("\n", " ")}
    keys = [str(v) for c in KEY_COLS if c in df.columns for v in df[c].head(limit)]
    return {"query": query, "tables": used, "columns": list(df.columns), "truncated": len(df) > limit,
            "rows_returned": min(len(df), limit), "rows": _records(df, limit), "record_keys": keys[:limit]}


def get_records(record_keys: list[str]) -> dict:
    """Trace record keys to their source rows. Derived keys (e.g. 'eli:123', canonical keys) are followed through
    the lineage table back to raw records. Raw keys: 'erp:4500012345:10', 'fuel:FD0123',
    'energy:S01:2025-03:electricity', 'pcf:SUP002:M101:2024', 'ef:EF-PEA-FI'. Max 20 keys."""
    out = []
    for k in record_keys[:20]:
        edges = gold.trace(k)
        if edges:
            src = gold.leaves(edges)
            out.append({"record_key": k, "lineage": edges[:50], "sources": [data.lookup(s) for s in src[:10]],
                        "n_sources": len(src)})
        else:
            out.append(data.lookup(k))
    return {"records": out}


def data_quality(table: str = "", record_key: str = "") -> dict:
    """Data-quality issues and corrections from the pipeline (issue log + correction log).

    Args:
        table: optional table filter, e.g. 'erp_purchase_lines', 'fuel_deliveries'.
        record_key: optional exact key or prefix, e.g. 'erp:' or 'fuel:FD0123'.
    """
    out = {}
    sources = {"issues": (gold.GOLD["issues"], "A1_issues_submission"),
               "corrections": (gold.GOLD["corrections"], "corrections_log")}  # pipeline tables, else legacy CSVs
    for label, (gname, csvname) in sources.items():
        if gname in gold.delta_tables():
            d, src = gold.frame(gname), f"gold.{gname}"
        elif (data.OUT / f"{csvname}.csv").exists():
            d, src = pd.read_csv(data.OUT / f"{csvname}.csv"), f"outputs/{csvname}.csv"
        else:
            out[label] = "not produced yet by the pipeline"
            continue
        if table and "table" in d.columns:
            d = d[d["table"].astype(str).str.contains(table, case=False)]
        if record_key and "record_key" in d.columns:
            d = d[d["record_key"].astype(str).str.startswith(record_key)]
        out[label] = {"source": src, "rows_matched": len(d), "rows": _records(d)}
    return out


def search_docs(query: str, k: int = 5) -> dict:
    """Search the framework and methodology documents (GHG Protocol, SBTi, SBTN, ESRS, EUDR, dataset docs,
    pipeline method note). Returns chunks with file and heading_path; cite them as [file#heading]."""
    try:
        hits, method = gold.search(query, int(k))
    except Exception as e:  # embedding quota/network: fall back is handled by the model re-asking
        return {"error": f"{type(e).__name__}: {e}"}
    cols = [c for c in ("file", "heading_path", "chunk_id", "text", "score") if c in hits.columns]
    return {"method": method, "chunks": _records(hits[cols], k)}


def sbti_target(base_value: float, annual_rate_pct: float, base_year: int, target_year: int) -> dict:
    """SBTi linear absolute-contraction target: base x (1 - rate x years).

    Args:
        base_value: base-year emissions in tCO2e.
        annual_rate_pct: linear annual reduction in percent of base, e.g. 4.2 (Scope 1+2), 2.5 (Scope 3 WB2C), 3.03 (FLAG).
        base_year: e.g. 2025.
        target_year: e.g. 2032.
    """
    years = target_year - base_year
    reduction = annual_rate_pct / 100 * years
    return {"target_tco2e": round(base_value * (1 - reduction), 2), "total_reduction_pct": round(100 * reduction, 2),
            "formula": f"{base_value} x (1 - {annual_rate_pct}% x {years})"}


_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow,
        ast.USub: op.neg, ast.UAdd: op.pos}


def _eval(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_eval(n.left), _eval(n.right))
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_eval(n.operand))
    raise ValueError("only numbers and + - * / ** ( ) allowed")


def calculate(expression: str) -> dict:
    """Evaluate arithmetic on numbers you got from other tools, e.g. '(1234.5 - 1000) / 1000 * 100'.
    Always use this instead of doing arithmetic yourself."""
    try:
        v = _eval(ast.parse(expression, mode="eval").body)
        return {"expression": expression, "result": v if math.isfinite(v) else None}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


TOOLS = [get_inventory, sql, get_records, data_quality, search_docs, sbti_target, calculate]
