"""Data access for the copilot. Reads the unzipped hackathon package plus whatever the pipeline team
writes to outputs/. Never imports pipeline code, so the copilot works before the pipeline is done."""
from __future__ import annotations

import json
import re
import os
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "outputs"


def _load_env():
    f = REPO / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_load_env()
# PKG location: CCN_ROOT env, else the team spec's .tmp/ layout, else a sibling folder of the repo.
_PKG_CANDIDATES = [REPO / ".tmp" / "Apetit_SinceAI2026" / "APETIT_CLIMATE_NATURE_NAVIGATOR_2026" / "APETIT_CLIMATE_NATURE_NAVIGATOR_2026",
                   REPO.parent / "Apetit_SinceAI2026" / "APETIT_CLIMATE_NATURE_NAVIGATOR_2026"]
CCN_ROOT = Path(os.environ.get("CCN_ROOT") or next((p for p in _PKG_CANDIDATES if p.exists()), _PKG_CANDIDATES[-1])).resolve()
sys.path.insert(0, str(CCN_ROOT / "tools"))
from ccn_tools import io as ccn_io, reference_calculator as rc  # noqa: E402


def _is_semicolon(p: Path) -> bool:
    head = p.open(encoding="utf-8").readline()
    return head.count(";") > head.count(",")


def _read_csv(p: Path, **kw) -> pd.DataFrame:
    # The Swedish Foodhills file uses ';' and decimal commas.
    return pd.read_csv(p, sep=";", decimal=",", **kw) if _is_semicolon(p) else pd.read_csv(p, **kw)


@lru_cache(maxsize=None)
def table_paths() -> dict[str, Path]:
    """Table name (file stem) -> path. Pipeline outputs are added on top of the raw package."""
    paths = {p.stem: p for p in sorted((CCN_ROOT / "data").rglob("*.csv"))}
    if OUT.exists():
        paths.update({p.stem: p for p in sorted(OUT.glob("*.csv"))})
    return paths


def rel(p: Path) -> str:
    for base in (CCN_ROOT, REPO):
        try:
            return str(p.relative_to(base))
        except ValueError:
            pass
    return str(p)


@lru_cache(maxsize=None)
def table(name: str) -> pd.DataFrame:
    p = table_paths().get(name)
    if p is None:
        raise KeyError(f"Unknown table {name!r}. Known: {', '.join(table_paths())}")
    df = _read_csv(p, dtype={"doc_no": str, "reference_doc": str, "ref_doc": str})
    for c in [c for c in df.columns if c.endswith("_date")]:  # real dates, so filters like posting_date >= '2025-01-01' work
        df[c] = pd.to_datetime(df[c], errors="coerce")
        if "year" not in df.columns:
            df["year"] = df[c].dt.year
    return df


@lru_cache(maxsize=None)
def schema_text() -> str:
    lines = []
    for name, p in table_paths().items():
        cols = list(_read_csv(p, nrows=0).columns)
        with p.open(encoding="utf-8") as fh:
            n = sum(1 for _ in fh) - 1
        lines.append(f"- {name} ({rel(p)}, {n} rows): {', '.join(cols)}")
    return "\n".join(lines)


# ---- inventory --------------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _naive_T() -> dict:
    return ccn_io.naive_canonical(ccn_io.load_raw(CCN_ROOT))


@lru_cache(maxsize=None)
def inventory(year: int) -> tuple[pd.DataFrame, str]:
    """(line items, status). status = 'pipeline' if outputs/inventory_{year}.csv exists, else 'naive'."""
    p = OUT / f"inventory_{year}.csv"
    if p.exists():
        return pd.read_csv(p), "pipeline"
    inv = rc.compute_inventory(_naive_T(), year)
    memo = pd.DataFrame([dict(year=year, scope="memo", category="biogenic_co2_scope1", line_item="biogenic CO2 (t, outside scopes)",
                              tco2e=inv.attrs.get("biogenic_co2_t", float("nan")), basis="memo")])
    return pd.concat([inv, memo], ignore_index=True), "naive"


# ---- record keys (A1 format, plus ef:{ef_id}) --------------------------------------------------

KEYS = {
    "erp": ("erp_purchase_lines_2021_2025", ["doc_no", "line_no"]),
    "energy": ("energy_meter_readings", ["site_id", "year", "month", "carrier"]),
    "fuel": ("fuel_deliveries", ["delivery_id"]),
    "goo": ("goo_cancellations", ["site_id", "year"]),
    "refrigerant": ("refrigerant_service_log", ["event_id"]),
    "waste": ("waste_transfer_notes", ["transfer_note"]),
    "travel": ("travel_bookings", ["booking_id"]),
    "commute": ("commuting_survey_2025", ["response_id"]),
    "ship": ("shipments", ["ref_doc", "ef_id"]),
    "farm_survey": ("farm_survey_fi", ["survey_id"]),
    "farm": ("farm_registry", ["farm_id"]),
    "report": ("draft_report_summary_2025", ["year", "line"]),
    "ef": ("emission_factor_library", ["ef_id"]),
}


def _norm(v) -> str:
    s = str(v)
    return str(int(s)) if s.isdigit() else s  # '03' == '3' for months/line numbers


_PART = re.compile(r"[\w.-]+")


def lookup(record_key: str) -> dict:
    try:
        return _lookup(record_key)
    except (ValueError, IndexError, KeyError) as e:  # malformed key: report, do not crash
        return {"record_key": record_key, "error": f"malformed record key: {e}"}


def _lookup(record_key: str) -> dict:
    prefix, _, rest = record_key.partition(":")
    if prefix == "pcf":
        parts = rest.split(":")
        if len(parts) != 3 or not all(_PART.fullmatch(x) and ".." not in x for x in parts):  # no path traversal
            return {"record_key": record_key, "error": "expected pcf:<supplier>:<material>:<year>"}
        sup, mat, year = parts
        f = CCN_ROOT / "data" / "02_raw_feeds" / "supplier_pcfs" / f"{sup}_{mat}_{year}.json"
        return {"record_key": record_key, "source": rel(f), "rows": [json.loads(f.read_text())] if f.exists() else []}
    if prefix not in KEYS:
        return {"record_key": record_key, "error": f"unknown prefix {prefix!r}"}
    name, cols = KEYS[prefix]
    parts = rest.split(":")
    if prefix == "energy":  # energy:{site}:{YYYY-MM}:{carrier}
        y, m = parts[1].split("-")
        parts = [parts[0], y, m, parts[2]]
    df = table(name)
    mask = pd.Series(True, index=df.index)
    for c, v in zip(cols, parts):
        mask &= df[c].map(_norm) == _norm(v)
    hit = df[mask]
    return {"record_key": record_key, "source": rel(table_paths()[name]),
            "csv_rows": [int(i) + 2 for i in hit.index],  # 1-based incl. header, as in a spreadsheet
            "rows": hit.head(10).to_dict("records")}


def record_keys(name: str, df: pd.DataFrame, limit: int = 20) -> list[str]:
    for prefix, (t, cols) in KEYS.items():
        if t == name and prefix not in ("energy",) and all(c in df.columns for c in cols):
            return [f"{prefix}:" + ":".join(str(r[c]) for c in cols) for _, r in df.head(limit).iterrows()]
    return []


# ---- docs corpus ------------------------------------------------------------------------------

def corpus_files() -> list[Path]:
    return [CCN_ROOT / "START_HERE.md", *sorted((CCN_ROOT / "docs").glob("*.md")),
            CCN_ROOT / "data" / "07_frameworks" / "framework_digest.md",
            CCN_ROOT / "data" / "07_frameworks" / "source_registry.csv"]


@lru_cache(maxsize=None)
def corpus() -> dict[str, str]:
    return {rel(p): p.read_text(encoding="utf-8") for p in corpus_files() if p.exists()}


def reset_caches():
    """Call after the pipeline writes new outputs."""
    for f in (table_paths, table, schema_text, inventory):
        f.cache_clear()
