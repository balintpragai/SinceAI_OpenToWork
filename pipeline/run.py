"""One deterministic run: Raw -> Bronze -> S1 -> S2 -> S3 -> S4 -> Gold, plus exports and checks."""
from __future__ import annotations

import hashlib
import os
import json
import subprocess
import time
from datetime import datetime, timezone

import pandas as pd

from . import stages
from .canonical import build_canonical
from .catalog import build_catalog
from .checks import reference_check, self_check
from .config import DEV_YEARS, REPO_ROOT, SUBMISSION_YEAR, Config
from .as_recorded import as_recorded_line_items, issue_effects
from .correct import empty_review_decisions, stage_s3
from .emissions import emission_line_items, summarise
from .exports import a1_export, a1_rows, a2_export, write_csv
from .index import CHUNK_SCHEMA, build_index
from .lakehouse import Lakehouse
from .rules import RULES

INVENTORY_YEARS = [2021, 2022, 2023, 2024, 2025]   # canonical 2021-2025 inventory (METHODOLOGY.md §1)


def _git_commit(cfg: Config) -> str:
    if os.environ.get("GIT_COMMIT"):              # set at docker build time; no git inside the image
        return os.environ["GIT_COMMIT"]
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                              timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _issues_for_delta(issues: pd.DataFrame) -> pd.DataFrame:
    d = issues.copy()
    d["changes"] = d.changes.map(lambda c: json.dumps(c, default=str) if c else None)
    d["new_row"] = d.new_row.map(lambda r: json.dumps(r, default=str) if isinstance(r, dict) else None)
    return d


def _sign_off_status(reviews: pd.DataFrame, year: int) -> tuple[str, str | None]:
    if reviews is None or reviews.empty:
        return "draft", None
    so = reviews[(reviews.decision == "sign_off") & (reviews.override_value.astype(str) == str(year))]
    if so.empty:
        return "draft", None
    last_so = so.sort_values("decided_at").iloc[-1]
    later = reviews[(reviews.decision != "sign_off") & (reviews.decided_at > last_so.decided_at)]
    return ("draft", None) if len(later) else ("published", last_so.reviewer)


def run(cfg: Config | None = None, log=print) -> dict:
    cfg = cfg or Config()
    t0 = time.time()
    started = datetime.now(timezone.utc)
    commit = _git_commit(cfg)

    log("raw: copying package files")
    manifest = stages.stage_raw(cfg)
    inputs_hash = hashlib.sha256("".join(manifest.sha256).encode()).hexdigest()[:16]
    run_id = f"run-{started.strftime('%Y%m%dT%H%M%SZ')}-{inputs_hash[:8]}"
    lh = Lakehouse(cfg, dict(run_id=run_id, git_commit=commit, inputs_sha256=inputs_hash))
    lh.write("raw", "file_manifest", manifest.assign(run_id=run_id))

    log("bronze: parsing")
    bronze = stages.stage_bronze(cfg)
    for name, df in bronze.items():
        lh.write("bronze", name, df)

    log("s1: standardising")
    s1 = stages.stage_s1(bronze)
    for name, df in s1.items():
        lh.write("s1", name, df)

    log("s2: detecting issues")
    ctx = stages.make_context(s1)
    issues = stages.stage_s2(ctx)
    issues["run_id"] = run_id
    lh.write("s2", "issue_log", _issues_for_delta(issues))

    reviews = lh.read("review", "decisions") if lh.exists("review", "decisions") else None
    if reviews is None:
        lh.write("review", "decisions", empty_review_decisions())
        reviews = empty_review_decisions()

    log("s3: applying corrections, estimates and review decisions")
    s3, corr, status = stage_s3(s1, issues, reviews, run_id)
    for name, df in s3.items():
        lh.write("s3", name, df)
    lh.write("s3", "correction_log", corr)
    lh.write("s3", "issue_status", status)

    log("s4: canonical tables")
    T, lineage = build_canonical(s3, ctx.boundary)
    lineage["run_id"] = run_id
    for name, df in T.items():
        lh.write("s4", name, df)
    lh.write("s4", "lineage", lineage)

    log("gold: emission line items")
    eli = emission_line_items(T, s3, INVENTORY_YEARS)
    eli["run_id"] = run_id
    lh.write("gold", "emission_line_items", eli)
    summary = pd.concat([summarise(eli, y) for y in INVENTORY_YEARS], ignore_index=True)
    lh.write("gold", "inventory_summary", summary)

    log("gold: as recorded (no issue applied) and the effect of each issue")
    raw = as_recorded_line_items(s1, ctx.boundary, INVENTORY_YEARS, log)
    if raw is not None:
        raw["run_id"] = run_id
        lh.write("gold", "emission_line_items_as_recorded", raw)
        lh.write("gold", "inventory_summary_as_recorded",
                 pd.concat([summarise(raw, y) for y in INVENTORY_YEARS], ignore_index=True).assign(run_id=run_id))
        lh.write("gold", "issue_effects", issue_effects(eli, raw, issues, s3).assign(run_id=run_id))
    eli_lin = pd.DataFrame(dict(derived_key=eli.eli_key, source_key=eli.record_key, stage="gold",
                                canonical_table="emission_line_items"))
    farm = eli[eli.factor_id.astype(str).str.startswith("farm_footprint:")]
    eli_lin = pd.concat([eli_lin, pd.DataFrame(dict(derived_key=farm.eli_key, source_key=farm.factor_id, stage="gold",
                                                    canonical_table="emission_line_items"))], ignore_index=True)
    lh.write("gold", "lineage", pd.concat([lineage, eli_lin.assign(run_id=run_id)], ignore_index=True))
    lh.write("gold", "farm_footprints", T["farm_footprints"])
    lh.write("gold", "boundary", ctx.boundary.describe())
    for dim in ("sites", "materials", "suppliers", "emission_factor_library", "farm_registry", "parcels"):
        lh.write("gold", f"dim_{dim}", s3[dim])
    gi = issues.drop(columns=["changes", "new_row"]).merge(status, on="issue_id", how="left")
    lh.write("gold", "issues", gi)
    rule_cat = pd.DataFrame([dict(rule_id=r.rule_id, table=r.table, issue_type=r.issue_type, action=r.action,
                                  description=r.description) for r in RULES])
    lh.write("gold", "rule_catalog", rule_cat)

    log("checks: reference calculator and dev keys")
    ref = reference_check(T, eli, INVENTORY_YEARS)
    lh.write("gold", "reference_check", ref)
    pk = cfg.package_root / "tasks"
    a1_all = a1_rows(issues, status)
    a1_key = pd.read_csv(pk / "dev" / "A1_dev_issue_labels_2023_2024.csv")
    a2_keys = {y: pd.read_csv(pk / "dev" / f"A2_dev_inventory_{y}.csv") for y in DEV_YEARS}
    quality = self_check(a1_all, eli, a1_key, a2_keys, DEV_YEARS)
    quality["reference_check_ok"] = bool(ref.ok.all())
    quality["run_id"] = run_id
    lh.write("gold", "run_quality", quality)

    log("exports")
    sign, signer = _sign_off_status(reviews, SUBMISSION_YEAR)
    a1 = a1_export(issues, status, SUBMISSION_YEAR)
    a2 = a2_export(eli, pd.read_csv(pk / "templates" / "A2_inventory_2025_submission.csv"), SUBMISSION_YEAR)
    lh.write("gold", "a1_submission", a1_all)
    lh.write("gold", "a2_submission", a2)
    out_dir = cfg.exports_dir / sign
    import shutil
    for other in ("draft", "published"):          # only the current status folder may hold exports
        if other != sign:
            shutil.rmtree(cfg.exports_dir / other, ignore_errors=True)
    write_csv(a1, out_dir / "A1_issues_submission.csv")
    write_csv(a2, out_dir / "A2_inventory_2025_submission.csv")
    lh.write("gold", "export_manifest", pd.DataFrame([
        dict(file="Files/" + (out_dir / f).relative_to(cfg.files_dir).as_posix(), status=sign, signed_off_by=signer,
             year=SUBMISSION_YEAR, rows=n, run_id=run_id)
        for f, n in (("A1_issues_submission.csv", len(a1)), ("A2_inventory_2025_submission.csv", len(a2)))]))
    finished = datetime.now(timezone.utc)
    lh.write("gold", "run_manifest", pd.DataFrame([dict(
        run_id=run_id, git_commit=commit, started=started.isoformat(timespec="seconds"),
        finished=finished.isoformat(timespec="seconds"), inputs_sha256=inputs_hash, n_input_files=len(manifest),
        n_issues=len(issues), n_corrections=len(corr), sign_off_status=sign, signed_off_by=signer,
        reference_check_ok=bool(ref.ok.all()))]))

    log("index: chunking documents" + (" and embedding with Gemini" if os.environ.get("GEMINI_API_KEY") else
                                        " (no GEMINI_API_KEY: embeddings skipped)"))
    cat_cols = ["table", "layer", "table_description", "column", "dtype", "example", "description"]
    cat = build_catalog({**lh.frames, "gold_catalog": pd.DataFrame(columns=cat_cols)}, cfg.raw_dir)
    previous = lh.read("gold", "doc_chunks") if lh.exists("gold", "doc_chunks") else None
    chunks, index_manifest = build_index(cfg.raw_dir, rule_cat, cat, previous, run_id)
    lh.write("gold", "doc_chunks", chunks, schema=CHUNK_SCHEMA)
    lh.write("gold", "index_manifest", index_manifest)
    cat = build_catalog({**lh.frames, "gold_catalog": pd.DataFrame(columns=cat_cols)}, cfg.raw_dir)
    lh.write("gold", "catalog", cat)
    n_files = cfg.storage.publish_files()
    result = dict(lakehouse=cfg.storage.describe(), files_published=n_files,
                  index=index_manifest.status.iloc[0], run_id=run_id, seconds=round(time.time() - t0, 1), issues=len(issues), corrections=len(corr),
                  reference_check_ok=bool(ref.ok.all()), quality=quality, sign_off=sign, tables=len(lh.written))
    return result
