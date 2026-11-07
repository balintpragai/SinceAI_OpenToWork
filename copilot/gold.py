"""Gold layer (pipeline Part 1, .scratch/part1-pipeline/spec.md): read-only SQL over the lakehouse Delta tables,
with the raw package CSVs registered alongside so the copilot works before the pipeline has run."""
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import data

LAKEHOUSE = Path(os.environ.get("LAKEHOUSE_DIR") or os.environ.get("CCN_LAKEHOUSE") or data.REPO / "lakehouse").resolve()
TABLES = LAKEHOUSE / "Tables"
# Query embeddings must match the pipeline's index (pipeline/README.md, "Contract for Part 2").
EMBED_MODEL, EMBED_DIM, EMBED_TASK = "gemini-embedding-001", 768, "RETRIEVAL_QUERY"

# Pipeline table names (pipeline/README.md). Change here if the pipeline renames them.
GOLD = {"line_items": "gold_emission_line_items", "summary": "gold_inventory_summary", "issues": "gold_issues",
        "corrections": "s3_correction_log", "lineage": "gold_lineage", "reviews": "review_decisions",
        "catalog": "gold_catalog", "run_quality": "gold_run_quality", "index": "gold_doc_chunks",
        "exports": "gold_export_manifest", "rules": "gold_rule_catalog"}

SQL_TIMEOUT_S = 20
_lock = threading.Lock()  # one DuckDB connection, serialised (registered objects are per connection)


def delta_tables() -> dict[str, Path]:
    if not TABLES.exists():
        return {}
    return {p.name: p for p in sorted(TABLES.iterdir()) if (p / "_delta_log").exists()}


def has(key: str) -> bool:
    return GOLD[key] in delta_tables()


@lru_cache(maxsize=None)
def frame(name: str) -> pd.DataFrame:
    from deltalake import DeltaTable
    return DeltaTable(str(delta_tables()[name])).to_pandas()


@lru_cache(maxsize=None)
def connection() -> duckdb.DuckDBPyConnection:
    from deltalake import DeltaTable
    con = duckdb.connect()
    lake = delta_tables()
    for name, path in lake.items():  # lazy Arrow datasets: nothing is loaded until a query touches it
        con.register(name, DeltaTable(str(path)).to_pyarrow_dataset())
    if not lake:  # no pipeline yet: the raw package CSVs
        for name in data.table_paths():
            con.register(name, data.table(name))
    # Read-only sandbox: no file or network access from SQL, and the setting cannot be changed back.
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def layer(name: str) -> str:
    return name.split("_", 1)[0] if name in delta_tables() else "raw package"


_SQL_OK = re.compile(r"^\s*(select|with)\b", re.I | re.S)


def run_sql(query: str, limit: int) -> pd.DataFrame:
    q = query.strip().rstrip(";").strip()
    if ";" in q or not _SQL_OK.match(q):
        raise ValueError("Only one SELECT or WITH statement is allowed.")
    with _lock:
        con = connection()
        timer = threading.Timer(SQL_TIMEOUT_S, con.interrupt)  # a runaway query must not block every other call
        timer.start()
        try:
            return con.execute(f"SELECT * FROM ({q}) AS _q LIMIT {int(limit) + 1}").fetch_df()
        finally:
            timer.cancel()


@lru_cache(maxsize=None)
def schema_text() -> str:
    """Tables for the system prompt: Gold first (with catalog descriptions if the pipeline wrote them), then raw."""
    lake = delta_tables()
    if not lake:
        return "Raw package tables (the pipeline has not run: uncleaned):\n" + data.schema_text()
    cat = frame(GOLD["catalog"]) if has("catalog") else pd.DataFrame(columns=["table", "table_description", "column"])
    lines = ["Lakehouse tables from the data pipeline. Layers: bronze_* (parsed), s1_* (standardised), s3_* (corrected),",
             "s4_* (canonical), gold_* (results). Prefer gold_*; use s3_*/s4_* for record-level corrected data.",
             "For columns of non-gold tables run: SELECT \"column\", dtype, description FROM gold_catalog WHERE \"table\" = '<name>'.",
             "", "Gold tables (name: description; columns):"]
    for name in [n for n in lake if n.startswith("gold_") or n == GOLD["reviews"]]:
        c = cat[cat["table"] == name]
        desc = c["table_description"].dropna().iloc[0] if len(c) and c["table_description"].notna().any() else ""
        cols = c["column"].dropna().tolist() if len(c) else [f.name for f in __import__("deltalake").DeltaTable(str(lake[name])).schema().fields]
        lines.append(f"- {name}: {desc}; columns: {', '.join(cols)}")
    for prefix in ("s4_", "s3_", "s1_", "bronze_"):
        lines.append(f"\n{prefix}* tables: " + ", ".join(n for n in lake if n.startswith(prefix)))
    return "\n".join(lines)


# ---- lineage ------------------------------------------------------------------------------------

def trace(key: str, max_depth: int = 8) -> list[dict]:
    """Follow lineage (derived_key -> source_key) back to source records. Returns the edges walked."""
    if not has("lineage"):
        return []
    lin = frame(GOLD["lineage"])
    edges, frontier, seen = [], [key], set()
    for _ in range(max_depth):
        hits = lin[lin.derived_key.isin(frontier) & ~lin.derived_key.isin(seen)]
        if hits.empty:
            break
        seen.update(frontier)
        edges += hits[["derived_key", "source_key", "stage"]].to_dict("records")
        frontier = hits.source_key.unique().tolist()
    return edges


def leaves(edges: list[dict]) -> list[str]:
    derived = {e["derived_key"] for e in edges if e["derived_key"] != e["source_key"]}  # s4 has identity edges
    return sorted({e["source_key"] for e in edges} - derived)


# ---- document search ----------------------------------------------------------------------------

def _col(df: pd.DataFrame, *names: str) -> str | None:
    return next((n for n in names if n in df.columns), None)


@lru_cache(maxsize=None)
def _corpus_chunks() -> pd.DataFrame:
    """Fallback index: the in-package docs split on Markdown headings, same shape as the pipeline's index."""
    rows = []
    for path, text in data.corpus().items():
        heads, buf = [], []

        def flush():
            if buf and "".join(buf).strip():
                rows.append({"file": path, "heading_path": " > ".join(h for _, h in heads) or path,
                             "chunk_id": f"{path}#{len(rows)}", "text": "\n".join(buf).strip()})
        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(.*)", line)
            if m:
                flush()
                buf = []
                lvl = len(m.group(1))
                heads = [h for h in heads if h[0] < lvl] + [(lvl, m.group(2).strip())]
            else:
                buf.append(line)
        flush()
    return pd.DataFrame(rows)


def embed(text: str) -> np.ndarray:
    from google import genai
    from google.genai import types
    r = genai.Client().models.embed_content(model=EMBED_MODEL, contents=text, config=types.EmbedContentConfig(
        task_type=EMBED_TASK, output_dimensionality=EMBED_DIM))
    v = np.asarray(r.embeddings[0].values, dtype=float)
    return v / (np.linalg.norm(v) or 1.0)  # index vectors are L2-normalised: rank by dot product


def search(query: str, k: int = 5) -> tuple[pd.DataFrame, str]:
    """Top-k chunks: vector search over the pipeline index if present, else keyword overlap over the docs."""
    ch, method = _corpus_chunks(), "keyword over package docs (no pipeline index)"
    if has("index"):
        idx = frame(GOLD["index"])
        emb = idx["embedding"] if "embedding" in idx.columns else pd.Series(dtype=object)
        if emb.notna().all() and len(emb) and os.environ.get("GEMINI_API_KEY"):
            m = np.vstack(emb.to_numpy())
            return idx.assign(score=m @ embed(query)).nlargest(k, "score"), "vector (pipeline index)"
        ch, method = idx, "keyword over pipeline index (not embedded)"
    terms = set(re.findall(r"\w{3,}", query.lower()))
    score = ch.apply(lambda r: sum(t in (r.text + " " + r.heading_path).lower() for t in terms), axis=1)
    return ch.assign(score=score).nlargest(k, "score"), method


def known_headings() -> dict[str, list[str]]:
    """file -> heading paths, from the pipeline index if present, else from the docs."""
    src = frame(GOLD["index"]) if has("index") else _corpus_chunks()
    return src.groupby("file")["heading_path"].apply(lambda s: [h.lower() for h in s]).to_dict()


def reset():
    for f in (frame, connection, schema_text, _corpus_chunks):
        f.cache_clear()
