"""Plain-language source names: map tables, files, docs and record keys to labels a non-technical reader understands,
and build the `sources` list of an answer from its tool trace and citations."""
from __future__ import annotations

import re
from functools import lru_cache

from . import data, gold

FILE_LABELS = {  # stem of every package data file -> plain label
    # 01_master
    "climate_grid_cells": "Climate grid cells", "emission_factor_library": "Emission factor library",
    "farm_registry": "Farm registry", "materials": "Materials list", "parcels": "Field parcels",
    "sites": "Company sites", "suppliers": "Supplier list",
    # 02_raw_feeds
    "capex_projects": "Investment projects", "commuting_survey_2025": "Employee commuting survey 2025",
    "energy_meter_readings": "Energy meter readings", "erp_purchase_lines_2021_2025": "Purchase records (ERP export)",
    "frozen_warehousing": "Frozen warehousing records", "fuel_deliveries": "Fuel deliveries",
    "fuel_stock_changes": "Fuel stock changes", "goo_cancellations": "Green electricity certificate cancellations",
    "goo_registry_statement": "Green electricity registry statement", "headcount": "Headcount",
    "heat_supplier_factors": "District heat supplier emission factors", "refrigerant_service_log": "Refrigerant service log",
    "sales_volumes": "Sales volumes", "shipments": "Freight shipments", "travel_bookings": "Business travel bookings",
    "waste_transfer_notes": "Waste transfer notes", "wastewater_third_party": "Wastewater (third-party treatment)",
    "water_balance": "Water balance", "supplier_pcfs": "Supplier product carbon footprints",
    # 03_farming
    "current_calculator_footprints": "Farm footprint calculator results", "farm_survey_fi": "Finnish contract-farm survey",
    "foodhills_odlingsdata_se": "Swedish (Foodhills) grower records", "parcel_crop_history_and_plan": "Crop history and plan per parcel",
    # 04_climate
    "climate_change_signals": "Climate change signals", "weather_monthly_1991_2060": "Monthly weather history and projections",
    # 05_scenarios
    "contract_prices_and_replacement_premiums": "Contract prices and replacement premiums",
    "decarbonisation_levers": "Decarbonisation options", "draft_report_summary_2025": "Draft 2025 report summary",
    "published_inventory_history": "Previously published inventories", "structural_events": "Company structural changes",
    "transition_scenarios": "Transition scenarios",
    # 06_nature
    "catchments": "Water catchments", "monitored_catchment_loads": "Monitored catchment nutrient loads",
    "origin_state_of_nature_indicative": "State of nature at sourcing origins",
    # 07_frameworks
    "source_registry": "Source registry",
}

GOLD_LABELS = {
    "gold_emission_line_items": "Emission calculation (data pipeline)", "gold_inventory_summary": "Inventory summary (data pipeline)",
    "gold_issues": "Data-quality findings (data pipeline)", "s2_issue_log": "Data-quality findings (data pipeline)",
    "s3_correction_log": "Data corrections log (data pipeline)", "gold_lineage": "Calculation trail (data pipeline)",
    "s4_lineage": "Calculation trail (data pipeline)", "review_decisions": "Expert review decisions",
    "gold_doc_chunks": "Document search index", "gold_export_manifest": "Report sign-off records",
    "gold_rule_catalog": "Data-quality rules", "gold_run_quality": "Pipeline run quality checks",
    "gold_farm_footprints": "Farm footprints (data pipeline)", "gold_boundary": "Reporting boundary", "gold_catalog": "Table catalogue",
    "gold_a1_submission": "Report export (data pipeline)", "gold_a2_submission": "Report export (data pipeline)",
}

DOC_TITLES = {  # override titles that are too long or odd
    "docs/METHODOLOGY.md": "Methodology guide", "docs/APETIT_DATA_RECONCILIATION.md": "Data reconciliation notes",
    "docs/ASSUMPTIONS_AND_LIMITATIONS.md": "Assumptions and limitations", "docs/DATA_DICTIONARY.md": "Data dictionary",
    "docs/GLOSSARY.md": "Glossary", "docs/NATURE_SBTN.md": "Nature assessment guide (SBTN)",
    "docs/SCENARIOS_AND_RISK.md": "Scenarios and climate risk guide", "docs/SIMULATION_DESIGN.md": "Simulation design",
    "docs/SOURCES_AND_LICENCES.md": "Sources and licences", "START_HERE.md": "Project overview",
    "data/07_frameworks/framework_digest.md": "Framework digest", "pipeline/README.md": "Data pipeline description",
}

_PIPE = re.compile(r"^(bronze|s1|s3|s4)_(.+)$")


def _stem_label(x: str) -> str | None:
    if x in FILE_LABELS:
        return FILE_LABELS[x]
    k = next((k for k in FILE_LABELS if k.startswith(x) or x.startswith(k)), None)
    return FILE_LABELS[k] if k else None


def table_label(name: str) -> str:
    name = name.removeprefix("gold.")
    if name in FILE_LABELS or name in GOLD_LABELS:
        return FILE_LABELS.get(name) or GOLD_LABELS[name]
    if name.startswith("gold_dim_"):
        return "Reference list: " + (_stem_label(name[9:]) or name[9:].replace("_", " ")).lower()
    if m := _PIPE.match(name):
        base = _stem_label(m[2]) or m[2].replace("_", " ").capitalize()
        return base if m[1] in ("bronze", "s1") else f"{base} (cleaned by the data pipeline)"
    try:
        if name in gold.delta_tables() and gold.has("catalog"):
            c = gold.frame(gold.GOLD["catalog"])
            col = next((c_ for c_ in ("table_name", "table") if c_ in c.columns), None)
            if col and "table_description" in c.columns:
                d = c.loc[c[col] == name, "table_description"]
                if len(d) and str(d.iloc[0]).strip():
                    return str(d.iloc[0]).strip().split(".")[0][:80]
    except Exception:
        pass
    return name.replace("_", " ").capitalize()


@lru_cache(maxsize=None)
def doc_label(path: str) -> str:
    if path in DOC_TITLES:
        return DOC_TITLES[path]
    f = (data.REPO / path) if path.startswith("pipeline") else data.CCN_ROOT / path
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip().split(":")[0]
    except OSError:
        pass
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("_", " ").capitalize()


def table_file(name: str) -> str:
    name = name.removeprefix("gold.")
    p = data.table_paths().get(name)
    return data.rel(p) if p and name in FILE_LABELS else f"lakehouse: {name}"


def key_file(key: str) -> str | None:
    prefix = key.partition(":")[0]
    if prefix in data.KEYS:
        return data.rel(data.table_paths()[data.KEYS[prefix][0]]) if data.KEYS[prefix][0] in data.table_paths() else None
    return "data/02_raw_feeds/supplier_pcfs" if prefix == "pcf" else None


def file_label(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if path.endswith(".md"):
        return doc_label(path)
    return FILE_LABELS.get(stem) or table_label(stem)


def prompt_section() -> str:
    lines = [f"- {l} — {f}" for l, f in dict.fromkeys(
        (file_label(f), f) for f in {data.rel(p) for n, p in data.table_paths().items() if n in FILE_LABELS})]
    lines += [f"- {l} — {n}" for n, l in GOLD_LABELS.items() if n in gold.delta_tables()]
    lines += [f"- {l} — {p}" for p, l in DOC_TITLES.items()]
    return "\n".join(sorted(set(lines)))


_KEY = re.compile(r"\b(" + "|".join([*data.KEYS, "pcf"]) + r"):[\w.:-]*\w")
_CITE = re.compile(r"\[([\w./-]+\.(?:md|csv))#([^\]]+)\]")


def build_sources(trace: list[dict], technical_text: str = "", cap: int = 8) -> list[dict]:
    found: dict[str, dict] = {}  # file -> source; insertion order = importance

    def add(file: str | None, label: str | None = None, detail: str = ""):
        if not file:
            return
        s = found.setdefault(file, {"label": label or file_label(file), "file": file, "detail": ""})
        if detail and detail not in s["detail"]:
            if detail.startswith("rows ") and s["detail"].startswith("rows "):  # merge: "rows 32, 42, 81"
                s["detail"] += ", " + detail[5:]
            else:
                s["detail"] = f"{s['detail']}; {detail}" if s["detail"] else detail

    docs = []
    for step in trace:
        r, tool = step.get("result"), step.get("tool")
        if not isinstance(r, dict) or "error" in r and tool == "sql":
            continue
        if tool == "sql":
            for t in r.get("tables", {}):
                add(table_file(t), table_label(t))
        elif tool == "get_inventory" and r.get("source"):
            src = r["source"]
            if src.startswith("gold."):
                add(table_file(src), table_label(src), f"{r.get('year')}")
            else:
                add("data/02_raw_feeds", "Raw company records (uncleaned calculation)", f"{r.get('year')}")
        elif tool in ("get_records", "lookup_record"):
            for rec in r.get("records", [r]):
                for s in rec.get("sources", [rec]):
                    if isinstance(s, dict) and s.get("source"):
                        rows = s.get("csv_rows") or []
                        add(s["source"], None, f"rows {', '.join(map(str, rows[:5]))}" if rows else "")
        elif tool == "data_quality":
            for k in ("issues", "corrections"):
                if isinstance(r.get(k), dict):
                    src = str(r[k].get("source", ""))
                    detail = f"{r[k].get('rows_matched')} {'findings' if k == 'issues' else 'corrections'}"
                    if src.startswith("gold."):  # pipeline table, e.g. gold.gold_issues / gold.s3_correction_log
                        add(table_file(src), table_label(src), detail)
                    else:
                        add(src, None, detail)
        elif tool == "show_chart":
            for t in r.get("tables", []):
                add(table_file(t), table_label(t), f"{r.get('year') or ''}")
        elif tool == "search_docs":
            for c in r.get("chunks", []):
                docs.append((c.get("file"), c.get("heading_path")))
    for k in _KEY.finditer(technical_text):
        add(key_file(k.group(0)))
    cited = _CITE.findall(technical_text)
    docs = cited or docs  # the answer's own citations beat everything search returned
    for f, h in docs:
        if f:
            add(f, None, f"section “{str(h).split(' > ')[-1]}”" if h else "")
    return list(found.values())[:cap]
