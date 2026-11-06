"""Catalog of every table the run wrote: table, column, type, example, description. Generated from
the frames themselves plus the descriptions below, so it cannot drift from the schemas. The agent
(Part 2) reads it to write SQL."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .sources import SOURCE_BY_NAME

LAYER_DOC = {
    "raw": "Byte copy manifest of the challenge package files (Files/raw), with SHA-256.",
    "bronze": "Parsed source file, record key added, no values changed.",
    "s1": "Standardised (normalisations only: units, currency, decimals, Swedish headers).",
    "s2": "Validated: issue log only; no values change.",
    "s3": "Corrected: corrections and estimates applied, flagged issues marked, reviewer decisions applied.",
    "s4": "Canonical tables of docs/METHODOLOGY.md §2 (input to the GHG calculation).",
    "gold": "Data products for the agent and the dashboard.",
}

TABLE_DOC = {
    "s2_issue_log": "One row per detected issue: rule, issue type, action (correct/estimate/method/flag), confidence, evidence, proposed change.",
    "s3_correction_log": "Audit trail of every value change: record_key, field, old_value, new_value, rule_or_model, evidence, proposed_by, approved_by, timestamp, kind (correction/estimate/method), status.",
    "s3_issue_status": "Status of each issue after S3: auto_applied, open (flagged), accepted, rejected, overridden.",
    "s4_lineage": "Links each canonical record to the source records it was built from.",
    "gold_emission_line_items": "One row per source record x emission factor: tCO2e, FLAG part, biogenic CO2 memo, activity, factor and its source. Every inventory figure is a sum of these rows.",
    "gold_inventory_summary": "Inventory per year x scope x category (A2 categories), with flagged and estimated tCO2e and the flagged share.",
    "gold_lineage": "Lineage from emission line items and canonical records back to source record keys.",
    "gold_issues": "Issue log joined with status, for review in the dashboard.",
    "gold_a1_submission": "Rows of the A1 export (all years); the CSV export keeps only the submission year.",
    "gold_a2_submission": "Rows of the A2 export for the submission year.",
    "gold_reference_check": "Our line items summed per category vs ccn_tools.reference_calculator on the same canonical tables.",
    "gold_run_quality": "Self-check scores on the public dev keys (A1 2023-2024, A2 2023 and 2024).",
    "gold_rule_catalog": "Every detection rule: rule_id, table, issue type, action, description.",
    "gold_catalog": "This table: every table and column with type, example and description.",
    "gold_run_manifest": "Run id, git commit, timestamps, input file hashes, sign-off status.",
    "gold_export_manifest": "Exported files with their status (draft/published).",
    "gold_boundary": "Organisational boundary per site (from/to month).",
    "gold_farm_footprints": "Contract-farm footprints per farm x crop x year with components, organic share and delivered kg.",
    "gold_doc_chunks": "Document index for the agent: Markdown chunks (file, heading_path, text) with gemini-embedding-001 vectors (768-d, L2-normalised, RETRIEVAL_DOCUMENT). Query with RETRIEVAL_QUERY, same model and dimension, dot product.",
    "gold_index_manifest": "Embedding model, dimension, tasks and counts of the document index.",
    "review_decisions": "Written by the dashboard: reviewer decisions (accept/reject/override/sign_off) read by the next run.",
}

COLUMN_DOC = {
    "record_key": "Stable record identifier (challenge format, e.g. erp:{doc_no}:{line_no}).",
    "_source_file": "File below data/ the record came from.",
    "_source_row": "1-based data row in the source file (header excluded).",
    "is_excluded": "Record removed by a correction (e.g. duplicate).",
    "is_estimate": "Value created or replaced by an estimate.",
    "has_flag": "Record carries a flagged issue; original values kept.",
    "tco2e": "Tonnes CO2e (AR6 GWP100).",
    "flag_tco2e": "FLAG (land-based) part of tco2e (SBTi).",
    "biogenic_co2_t": "Biogenic CO2 memo item (t), not in Scope 1.",
    "flagged": "Line item comes from a record with a flagged issue.",
    "allocation": "How a non-linear step was shared out to records (direct if none).",
    "factor_id": "Emission factor id (ef library id, PCF record key, farm footprint key or method constant).",
    "factor_source": "Where the factor comes from (reference source, value status, version).",
    "issue_type": "One of the challenge ISSUE_TYPES (docs/TASKS_AND_SCORING.md).",
    "rule_id": "Detection rule (see gold_rule_catalog).",
    "flagged_share": "Share of tco2e coming from records with a flagged issue.",
}


def _data_dictionary(package_root: Path) -> dict[tuple[str, str], str]:
    """Column descriptions of the source files, parsed from the package's docs/DATA_DICTIONARY.md."""
    p = package_root / "docs" / "DATA_DICTIONARY.md"   # package_root here is the Raw copy (Files/raw)
    out, current = {}, None
    if not p.exists():
        return out
    by_file = {s.rel_path.split("/")[-1]: s.name for s in SOURCE_BY_NAME.values()}
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## `[^/]+/(.+?)`", line)
        if m:
            current = by_file.get(m.group(1))
            continue
        m = re.match(r"^\| `([^`]+)` \| [^|]+ \| [^|]* \| (.+) \|$", line)
        if m and current:
            out[(current, m.group(1))] = m.group(2).strip()
    return out


def build_catalog(frames: dict[str, pd.DataFrame], package_root: Path) -> pd.DataFrame:
    dd = _data_dictionary(package_root)
    rows = []
    for tname, df in sorted(frames.items()):
        layer = tname.split("_")[0]
        src = tname.split("_", 1)[1] if layer in ("bronze", "s1", "s3") else None
        tdoc = TABLE_DOC.get(tname) or (f"{LAYER_DOC.get(layer, '')} Source: {SOURCE_BY_NAME[src].description}."
                                        if src in SOURCE_BY_NAME else LAYER_DOC.get(layer, ""))
        for c in df.columns:
            ex = df[c].dropna()
            rows.append(dict(table=tname, layer=layer, table_description=tdoc, column=c, dtype=str(df[c].dtype),
                             example=str(ex.iloc[0])[:80] if len(ex) else None,
                             description=COLUMN_DOC.get(c) or dd.get((src, c)) if src else COLUMN_DOC.get(c)))
    return pd.DataFrame(rows)
