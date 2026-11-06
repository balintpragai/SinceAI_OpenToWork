"""Source registry: every in-scope file of the challenge package, how to parse it (Bronze) and how
to build its record key. Record-key formats for A1 tables follow docs/TASKS_AND_SCORING.md (A1,
"Record keys"); the other keys are ours and follow the same `prefix:part:part` pattern."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


def _csv(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8", **kw)


def _join(df: pd.DataFrame, prefix: str, *cols: str) -> pd.Series:
    parts = [df[c].astype(str) for c in cols]
    out = pd.Series(prefix, index=df.index)
    for p in parts:
        out = out + ":" + p
    return out


def _read_pcfs(path: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(path.glob("*.json")):
        js = json.loads(f.read_text(encoding="utf-8"))
        sup, mat, year = f.stem.split("_")
        p = js["pcf"]
        rows.append(dict(
            file=f.name, supplier_id=sup, material_id=mat, year=int(year), pcf_id=js.get("id"),
            status=js.get("status"), created=js.get("created"), product_description=js.get("productDescription"),
            declared_unit=p.get("declaredUnit"), unitary_product_amount=p.get("unitaryProductAmount"),
            pcf_excl_biogenic=p.get("pCfExcludingBiogenic"), pcf_incl_biogenic=p.get("pCfIncludingBiogenic"),
            fossil_ghg=p.get("fossilGhgEmissions"), dluc_ghg=p.get("dLucGhgEmissions"),
            land_management_ghg=p.get("landManagementGhgEmissions"),
            reference_period_start=p.get("referencePeriodStart"), reference_period_end=p.get("referencePeriodEnd"),
            geography_country=p.get("geographyCountry"), primary_data_share=p.get("primaryDataShare"),
            characterization_factors=p.get("characterizationFactors"),
        ))
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class Source:
    name: str                      # table name (A1 `table` value where applicable)
    rel_path: str                  # path below data/ (file or directory)
    key: Callable[[pd.DataFrame], pd.Series]
    reader: Callable[[Path], pd.DataFrame] = _csv
    description: str = ""

    def read(self, root: Path) -> pd.DataFrame:
        return self.reader(root / "data" / self.rel_path)


def _ym(df):
    return df.year.astype(str) + "-" + df.month.astype(int).map("{:02d}".format)


SOURCES: list[Source] = [
    # 01 master data
    Source("sites", "01_master/sites.csv", lambda d: _join(d, "site", "site_id"), description="Group sites"),
    Source("materials", "01_master/materials.csv", lambda d: _join(d, "material", "material_id"), description="Material master"),
    Source("suppliers", "01_master/suppliers.csv", lambda d: _join(d, "supplier", "supplier_id"), description="Supplier master"),
    Source("emission_factor_library", "01_master/emission_factor_library.csv", lambda d: _join(d, "ef", "ef_id"),
           description="Emission-factor library with provenance"),
    Source("farm_registry", "01_master/farm_registry.csv", lambda d: _join(d, "farm", "farm_id"), description="Contract-farm registry"),
    Source("parcels", "01_master/parcels.csv", lambda d: _join(d, "parcel", "parcel_id"), description="Field parcels with soil-map attributes"),
    Source("climate_grid_cells", "01_master/climate_grid_cells.csv", lambda d: _join(d, "cell", "cell_id"), description="Climate grid cells"),
    # 02 raw feeds
    Source("erp_purchase_lines", "02_raw_feeds/erp_purchase_lines_2021_2025.csv", lambda d: _join(d, "erp", "doc_no", "line_no"),
           reader=lambda p: _csv(p, dtype={"doc_no": str, "reference_doc": str}), description="ERP purchase lines"),
    Source("energy_meter_readings", "02_raw_feeds/energy_meter_readings.csv",
           lambda d: "energy:" + d.site_id + ":" + _ym(d) + ":" + d.carrier, description="Monthly energy meter readings"),
    Source("fuel_deliveries", "02_raw_feeds/fuel_deliveries.csv", lambda d: _join(d, "fuel", "delivery_id"), description="Fuel deliveries"),
    Source("fuel_stock_changes", "02_raw_feeds/fuel_stock_changes.csv", lambda d: _join(d, "fuel_stock", "site_id", "carrier", "year"),
           description="Year-end fuel stock changes"),
    Source("goo_cancellations", "02_raw_feeds/goo_cancellations.csv", lambda d: _join(d, "goo", "site_id", "year"),
           description="Internal GoO cancellation log"),
    Source("goo_registry_statement", "02_raw_feeds/goo_registry_statement.csv", lambda d: _join(d, "goo_registry", "cancellation_id"),
           description="National registry GoO statement (authoritative)"),
    Source("heat_supplier_factors", "02_raw_feeds/heat_supplier_factors.csv", lambda d: _join(d, "heat_factor", "site_id", "year"),
           description="Supplier-specific heat/steam factors"),
    Source("refrigerant_service_log", "02_raw_feeds/refrigerant_service_log.csv", lambda d: _join(d, "refrigerant", "event_id"),
           description="Refrigerant top-ups"),
    Source("waste_transfer_notes", "02_raw_feeds/waste_transfer_notes.csv", lambda d: _join(d, "waste", "transfer_note"),
           description="Waste transfer notes"),
    Source("wastewater_third_party", "02_raw_feeds/wastewater_third_party.csv", lambda d: _join(d, "wastewater", "year", "site_id"),
           description="Wastewater to municipal treatment"),
    Source("water_balance", "02_raw_feeds/water_balance.csv",
           lambda d: _join(d, "water", "site_id", "year", "flow", "source_or_destination"), description="Water withdrawals and discharges"),
    Source("travel_bookings", "02_raw_feeds/travel_bookings.csv", lambda d: _join(d, "travel", "booking_id"), description="Business travel"),
    Source("commuting_survey", "02_raw_feeds/commuting_survey_2025.csv", lambda d: _join(d, "commute", "response_id"),
           description="Commuting survey 2025"),
    Source("headcount", "02_raw_feeds/headcount.csv", lambda d: _join(d, "headcount", "year", "site_id"), description="Year-end headcount"),
    Source("shipments", "02_raw_feeds/shipments.csv", lambda d: _join(d, "shipment", "shipment_id"),
           reader=lambda p: _csv(p, dtype={"ref_doc": str}), description="Transport legs"),
    Source("frozen_warehousing", "02_raw_feeds/frozen_warehousing.csv", lambda d: _join(d, "warehousing", "year"),
           description="Third-party frozen warehousing"),
    Source("sales_volumes", "02_raw_feeds/sales_volumes.csv",
           lambda d: _join(d, "sales", "year", "month", "product_group", "site_id", "market"), description="Monthly sales"),
    Source("capex_projects", "02_raw_feeds/capex_projects.csv", lambda d: _join(d, "capex", "year", "site_id", "project"),
           description="Capital projects"),
    Source("supplier_pcfs", "02_raw_feeds/supplier_pcfs", lambda d: _join(d, "pcf", "supplier_id", "material_id", "year"),
           reader=_read_pcfs, description="Supplier PCFs (PACT v2 JSON), one row per file"),
    # 03 farming
    Source("farm_survey", "03_farming/farm_survey_fi.csv", lambda d: _join(d, "farm_survey", "survey_id"), description="Finnish farm survey"),
    Source("foodhills_odlingsdata", "03_farming/foodhills_odlingsdata_se.csv",
           lambda d: "foodhills:" + d["odlar_id"].astype(str) + ":" + d["skördeår"].astype(str) + ":" + d.index.astype(str),
           reader=lambda p: _csv(p, sep=";", dtype=str), description="Foodhills (SE) grower data, Swedish format"),
    Source("parcel_crop_history_and_plan", "03_farming/parcel_crop_history_and_plan.csv",
           lambda d: _join(d, "crop_plan", "parcel_id", "year"), description="Crop per parcel and year"),
    Source("current_calculator_footprints", "03_farming/current_calculator_footprints.csv",
           lambda d: _join(d, "current_footprint", "farm_id", "crop", "year"), description="Current-practice footprints (mineral soil assumed)"),
    # 05 scenarios
    Source("structural_events", "05_scenarios/structural_events.csv", lambda d: "event:" + d.date.astype(str) + ":" + d.index.astype(str),
           description="Dated structural and regulatory events"),
    Source("published_inventory_history", "05_scenarios/published_inventory_history.csv", lambda d: _join(d, "published", "year"),
           description="Published inventory totals"),
    Source("draft_report_summary", "05_scenarios/draft_report_summary_2025.csv", lambda d: _join(d, "report", "year", "line"),
           description="Draft 2025 report summary (raw)"),
    Source("transition_scenarios", "05_scenarios/transition_scenarios.csv", lambda d: _join(d, "scenario", "scenario", "year"),
           description="NGFS-style transition scenarios"),
    Source("decarbonisation_levers", "05_scenarios/decarbonisation_levers.csv", lambda d: _join(d, "lever", "lever_id"),
           description="Lever catalogue"),
    Source("contract_prices_and_replacement_premiums", "05_scenarios/contract_prices_and_replacement_premiums.csv",
           lambda d: "price:" + d.index.astype(str), description="Contract prices and replacement premiums"),
    # 07 frameworks
    Source("source_registry", "07_frameworks/source_registry.csv", lambda d: "source:" + d.index.astype(str),
           description="Framework sources with licences"),
]

SOURCE_BY_NAME = {s.name: s for s in SOURCES}

# Files copied to Raw but not parsed into tables (documents for the index), relative to the package root.
RAW_DOCUMENT_GLOBS = ["data/07_frameworks/framework_digest.md", "docs/*.md"]
