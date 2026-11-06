"""Document index for the Gemini agent (Part 2).

Documents (spec "Index"): the framework digest and the package docs (from Files/raw), our GLOSSARY,
the pipeline description (pipeline/README.md), our ADRs, and two documents generated on every run: the
rule catalogue and the table catalog. The challenge brief is excluded.

Chunks follow Markdown headings, so every chunk can be cited as file + section. Embeddings come from
`gemini-embedding-001` (task RETRIEVAL_DOCUMENT, 768 dimensions, L2-normalised) when GEMINI_API_KEY is
set. They are cached by text hash, so unchanged chunks are not re-embedded. Contract for Part 2: embed
queries with the same model, task RETRIEVAL_QUERY, the same dimension, normalise, and use cosine/dot
product. The model, dimension and task are stored on every row and in gold_index_manifest.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pyarrow as pa

from .config import REPO_ROOT

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768
DOC_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
BATCH = 100
MAX_CHARS = 3000

CHUNK_SCHEMA = pa.schema([
    ("chunk_id", pa.string()), ("doc_id", pa.string()), ("source_kind", pa.string()), ("file", pa.string()),
    ("heading_path", pa.string()), ("line_start", pa.int64()), ("text", pa.string()), ("n_chars", pa.int64()),
    ("text_sha256", pa.string()), ("embedding", pa.list_(pa.float32())), ("embedding_model", pa.string()),
    ("embedding_dim", pa.int64()), ("embedding_task", pa.string()), ("run_id", pa.string()),
])


# ------------------------------------------------------------------------------------------- documents

def collect_documents(raw_dir: Path, generated: dict[str, str]) -> list[dict]:
    docs = []
    fd = raw_dir / "data" / "07_frameworks" / "framework_digest.md"
    if fd.exists():
        docs.append(dict(doc_id="pkg:data/07_frameworks/framework_digest.md", kind="framework",
                         file="data/07_frameworks/framework_digest.md", text=fd.read_text(encoding="utf-8")))
    for p in sorted((raw_dir / "docs").glob("*.md")):
        docs.append(dict(doc_id=f"pkg:docs/{p.name}", kind="package_doc", file=f"docs/{p.name}",
                         text=p.read_text(encoding="utf-8")))
    ours = [("GLOSSARY.md", "glossary"), ("pipeline/README.md", "pipeline_doc")]
    ours += [(p.relative_to(REPO_ROOT).as_posix(), "adr") for p in sorted((REPO_ROOT / "docs" / "adr").glob("*.md"))]
    for rel, kind in ours:
        p = REPO_ROOT / rel
        if p.exists():
            docs.append(dict(doc_id=f"repo:{rel}", kind=kind, file=rel, text=p.read_text(encoding="utf-8")))
    for name, text in generated.items():
        docs.append(dict(doc_id=f"gen:{name}", kind="generated", file=f"(generated) {name}", text=text))
    return docs


def rule_catalog_markdown(rules: pd.DataFrame) -> str:
    out = ["# Rule catalogue (generated each run)", "",
           "Every data-quality rule of the pipeline. action: correct = value fixed, estimate = value created for "
           "a missing/unusable record, method = recorded, emissions use a method instead, flag = record keeps its values.", ""]
    for table, g in rules.groupby("table"):
        out.append(f"## {table}")
        for r in g.itertuples():
            out.append(f"- **{r.rule_id}** ({r.issue_type}, {r.action}): {r.description}")
        out.append("")
    return "\n".join(out)


def table_catalog_markdown(catalog: pd.DataFrame) -> str:
    out = ["# Table catalog (generated each run)", "",
           "Gold and log tables the agent can query with SQL, with their columns.", ""]
    keep = catalog[catalog.layer.isin(["gold", "s2", "s3", "s4", "review"]) & ~catalog.table.str.match(r"^s[34]_(?!correction_log|issue_status|lineage)")]
    for table, g in keep.groupby("table"):
        out.append(f"## {table}")
        out.append(str(g.table_description.iloc[0] or ""))
        for r in g.itertuples():
            desc = f": {r.description}" if isinstance(r.description, str) and r.description else ""
            out.append(f"- `{r.column}` ({r.dtype}){desc}")
        out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------------------------- chunking

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def chunk_markdown(text: str, max_chars: int = MAX_CHARS) -> list[dict]:
    """Split on headings (outside code fences); long sections are split on blank lines."""
    sections, stack, buf, start, in_code = [], [], [], 1, False

    def flush(end_line):
        body = "\n".join(buf).strip()
        if body:
            sections.append(dict(heading_path=" > ".join(stack), line_start=start, body=body))

    for i, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else HEADING.match(line)
        if m:
            flush(i)
            level = len(m.group(1))
            stack = stack[:level - 1] + [m.group(2).strip()]
            buf, start = [], i
        else:
            buf.append(line)
    flush(None)
    out = []
    for s in sections:
        if len(s["body"]) <= max_chars:
            out.append(s)
            continue
        part, n = [], 0
        for para in re.split(r"\n\s*\n", s["body"]):
            if n + len(para) > max_chars and part:
                out.append(dict(s, body="\n\n".join(part)))
                part, n = [], 0
            part.append(para)
            n += len(para) + 2
        if part:
            out.append(dict(s, body="\n\n".join(part)))
    return out


def build_chunks(docs: list[dict]) -> pd.DataFrame:
    rows = []
    for d in docs:
        for i, c in enumerate(chunk_markdown(d["text"])):
            text = (f"[{d['file']}" + (f" > {c['heading_path']}" if c["heading_path"] else "") + "]\n" + c["body"])
            rows.append(dict(chunk_id=f"{d['doc_id']}#{i:03d}", doc_id=d["doc_id"], source_kind=d["kind"], file=d["file"],
                             heading_path=c["heading_path"], line_start=c["line_start"], text=text, n_chars=len(text),
                             text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------- embedding

def gemini_transport(api_key: str) -> Callable[[list[dict]], list[list[float]]]:
    def call(requests_: list[dict]) -> list[list[float]]:
        body = json.dumps({"requests": requests_}).encode("utf-8")
        url = API_URL.format(model=EMBEDDING_MODEL)
        for attempt in range(5):
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return [e["values"] for e in json.loads(r.read())["embeddings"]]
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 503) and attempt < 4:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise RuntimeError(f"Gemini embedding call failed: HTTP {e.code} {e.read()[:300]!r}") from None
        raise RuntimeError("Gemini embedding call failed after retries")
    return call


def embed_requests(chunks: pd.DataFrame) -> list[dict]:
    return [{"model": f"models/{EMBEDDING_MODEL}", "content": {"parts": [{"text": t}]}, "taskType": DOC_TASK,
             "title": h or f, "outputDimensionality": EMBEDDING_DIM}
            for t, h, f in zip(chunks.text, chunks.heading_path, chunks.file)]


def _normalise(v) -> list[float]:
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return (a / n if n else a).tolist()


def embed_chunks(chunks: pd.DataFrame, previous: pd.DataFrame | None,
                 transport: Callable[[list[dict]], list[list[float]]] | None) -> tuple[pd.DataFrame, dict]:
    """Fill `embedding`; reuse vectors of unchanged chunks from the previous index."""
    c = chunks.copy()
    cache = {}
    if previous is not None and len(previous):
        ok = previous[(previous.embedding_model == EMBEDDING_MODEL) & (previous.embedding_dim == EMBEDDING_DIM)
                      & previous.embedding.notna()]
        cache = {h: list(v) for h, v in zip(ok.text_sha256, ok.embedding)}
    c["embedding"] = pd.Series([cache.get(h) for h in c.text_sha256], index=c.index, dtype=object)
    reused = int(c.embedding.notna().sum())
    todo = c[c.embedding.isna()]
    if transport is not None and len(todo):
        reqs = embed_requests(todo)
        vecs = []
        for i in range(0, len(reqs), BATCH):
            vecs += transport(reqs[i:i + BATCH])
        c.loc[todo.index, "embedding"] = pd.Series([_normalise(v) for v in vecs], index=todo.index, dtype=object)
    n_emb = int(c.embedding.notna().sum())
    c["embedding_model"] = EMBEDDING_MODEL
    c["embedding_dim"] = EMBEDDING_DIM
    c["embedding_task"] = DOC_TASK
    status = "embedded" if n_emb == len(c) else ("partial" if n_emb else "not_embedded (set GEMINI_API_KEY)")
    return c, dict(n_chunks=len(c), n_embedded=n_emb, n_reused=reused, status=status)


def build_index(raw_dir: Path, rules: pd.DataFrame, catalog: pd.DataFrame, previous: pd.DataFrame | None,
                run_id: str, transport=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if transport is None and os.environ.get("GEMINI_API_KEY"):
        transport = gemini_transport(os.environ["GEMINI_API_KEY"])
    docs = collect_documents(raw_dir, {"rule_catalog": rule_catalog_markdown(rules),
                                       "table_catalog": table_catalog_markdown(catalog)})
    chunks, stats = embed_chunks(build_chunks(docs), previous, transport)
    chunks["run_id"] = run_id
    manifest = pd.DataFrame([dict(run_id=run_id, embedding_model=EMBEDDING_MODEL, embedding_dim=EMBEDDING_DIM,
                                  document_task=DOC_TASK, query_task=QUERY_TASK, normalised=True, similarity="dot_product",
                                  n_documents=len(docs), documents=json.dumps([d["doc_id"] for d in docs]), **stats)])
    return chunks[[f.name for f in CHUNK_SCHEMA]], manifest
