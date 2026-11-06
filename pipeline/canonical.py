"""S4 Canonical: the tables of docs/METHODOLOGY.md §2, built from S3. Excluded records are dropped,
the organisational boundary is applied, and every derived record is linked to its sources in the
lineage table (derived_key, source_key, stage)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .farm import INPUT_COLUMNS, organic_share
from .refdata import F, FARM_CROP_BY_MATERIAL, NCV_PER_UNIT, WASTE_EF_BY_TREATMENT
from .rules.feeds import registry_by_site_year


def _live(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df.is_excluded.astype(bool)].copy()


def _identity_lineage(df: pd.DataFrame, table: str) -> pd.DataFrame:
    return pd.DataFrame(dict(derived_key=df.record_key.values, source_key=df.record_key.values,
                             stage="s4", canonical_table=table))


def build_canonical(s3: dict[str, pd.DataFrame], boundary, submission_scope: dict | None = None):
    T: dict[str, pd.DataFrame] = {}
    lineage: list[pd.DataFrame] = []

    # master data
    T["sites"] = s3["sites"]
    T["materials"] = s3["materials"]
    T["ef_library"] = s3["emission_factor_library"]

    # energy: meter readings (monthly) + fuel consumption (annual = deliveries - stock change)
    em = _live(s3["energy_meter_readings"])
    em = em[[boundary.contains(s, y, m) for s, y, m in zip(em.site_id, em.year, em.month)]]
    em_c = em[["record_key", "site_id", "year", "month", "carrier", "mwh", "is_estimate", "has_flag"]].copy()
    lineage.append(_identity_lineage(em_c, "energy"))
    fd = _live(s3["fuel_deliveries"])
    fs = s3["fuel_stock_changes"]
    rows = []
    for (site, carrier, year, unit), g in fd.groupby(["site_id", "carrier", "year", "unit"]):
        st = fs[(fs.site_id == site) & (fs.carrier == carrier) & (fs.year == year)]
        stock = float(st.stock_change.sum()) if len(st) else 0.0
        ncv = NCV_PER_UNIT[(carrier, unit)]
        key = f"fuel_energy:{site}:{year}:{carrier}"
        rows.append(dict(record_key=key, site_id=site, year=int(year), month=0, carrier=carrier,
                         mwh=(g.quantity.sum() - stock) * ncv, is_estimate=bool(g.is_estimate.any()),
                         has_flag=bool(g.has_flag.any())))
        src = list(g.record_key) + list(st.record_key)
        lineage.append(pd.DataFrame(dict(derived_key=key, source_key=src, stage="s4", canonical_table="energy")))
    T["energy"] = pd.concat([em_c, pd.DataFrame(rows)], ignore_index=True)

    rf = _live(s3["refrigerant_service_log"])
    T["refrigerants"] = rf[["record_key", "site_id", "year", "refrigerant", "kg_added", "is_estimate", "has_flag"]]
    lineage.append(_identity_lineage(rf, "refrigerants"))

    # GoO: the national registry is authoritative (METHODOLOGY.md §2, `goo` row)
    reg = s3["goo_registry_statement"].copy()
    reg["vintage_year"] = reg.production_period_start.str[:4].astype(int)
    goo = registry_by_site_year(s3["goo_registry_statement"]).rename(columns={"mwh_registry": "mwh_cancelled"})
    goo["record_key"] = "goo_used:" + goo.site_id + ":" + goo.year.astype(str) + ":" + goo.vintage_year.astype(str)
    T["goo"] = goo
    for r in goo.itertuples():
        src = reg[(reg.beneficiary_site == r.site_id) & (reg.consumption_year == r.year) & (reg.vintage_year == r.vintage_year)]
        lineage.append(pd.DataFrame(dict(derived_key=r.record_key, source_key=list(src.record_key), stage="s4",
                                         canonical_table="goo")))
    T["heat_suppliers"] = s3["heat_supplier_factors"]

    # purchases
    erp = _live(s3["erp_purchase_lines"])
    T["purchases"] = erp[["record_key", "year", "posting_date", "material_id", "supplier_id", "qty_kg", "amount_eur",
                          "origin_country", "movement_type", "is_estimate", "has_flag"]]
    lineage.append(_identity_lineage(erp, "purchases"))

    # supplier PCFs: valid ones only (METHODOLOGY.md §4)
    p = s3["supplier_pcfs"].copy()
    valid = p.get("valid_for_year", pd.Series(True, index=p.index)).fillna(True).astype(bool)
    pu = p[valid].rename(columns={"pcf_excl_biogenic": "kgco2e_per_kg"})
    T["pcf_used"] = pu[["record_key", "year", "supplier_id", "material_id", "kgco2e_per_kg"]]
    lineage.append(_identity_lineage(pu, "pcf_used"))

    # contract-farm footprints (ADR 0003)
    ff, ff_lin = farm_footprints(s3, erp)
    T["farm_footprints"] = ff
    lineage.append(ff_lin)

    sh = _live(s3["shipments"])
    T["shipments"] = sh[["record_key", "year", "direction", "ref_doc", "ef_id", "mode", "t", "km", "tkm", "is_estimate", "has_flag"]]
    lineage.append(_identity_lineage(sh, "shipments"))
    T["warehousing"] = s3["frozen_warehousing"]

    w = _live(s3["waste_transfer_notes"])
    w = w[[boundary.contains(s, y, m) for s, y, m in zip(w.site_id, w.year, w.month)]]
    w["ef_id"] = w.treatment.map(WASTE_EF_BY_TREATMENT)
    w.loc[w.waste_stream == "plastic_waste", "ef_id"] = "EF-WASTE-PLASTIC-INC"
    T["waste"] = w[["record_key", "site_id", "year", "month", "waste_stream", "treatment", "ef_id", "t", "is_estimate", "has_flag"]]
    lineage.append(_identity_lineage(w, "waste"))
    T["wastewater"] = s3["wastewater_third_party"]

    tr = _live(s3["travel_bookings"])
    T["travel"] = tr[["record_key", "year", "traveller_id", "mode", "route", "pkm", "nights", "is_estimate", "has_flag"]]
    lineage.append(_identity_lineage(tr, "travel"))
    cs = _live(s3["commuting_survey"])
    T["commuting_survey"] = cs[["record_key", "site_id", "one_way_km", "mode", "days_on_site_per_week", "is_estimate", "has_flag"]]
    lineage.append(_identity_lineage(cs, "commuting_survey"))
    T["headcount"] = s3["headcount"]

    sa = s3["sales_volumes"]
    sa = sa[[boundary.contains(s, y, m) for s, y, m in zip(sa.site_id, sa.year, sa.month)]]
    T["sales"] = sa
    lineage.append(_identity_lineage(sa, "sales"))
    T["water_balance"] = s3["water_balance"]

    lin = pd.concat(lineage, ignore_index=True)
    return T, lin


def farm_footprints(s3: dict[str, pd.DataFrame], erp: pd.DataFrame, low_clay_probability: float | None = None):
    """Farm emissions per FI contract farm x crop x year (METHODOLOGY.md §5):
    per-ha footprint x declared parcel area; inputs from the survey (non-respondents: crop-year median
    of respondents' inputs, an estimate); organic-soil term weighted by the soil-map organic share."""
    from .farm import COMPONENTS, footprint_components_per_ha

    sv = _live(s3["farm_survey"])
    kw = {} if low_clay_probability is None else {"low_clay_probability": low_clay_probability}
    share = organic_share(s3["parcels"], s3["parcel_crop_history_and_plan"], **kw)
    d = erp[erp.material_id.isin(FARM_CROP_BY_MATERIAL)].copy()
    d["crop"] = d.material_id.map(FARM_CROP_BY_MATERIAL)
    deliv = d.groupby(["supplier_id", "crop", "year"]).agg(delivered_kg=("qty_kg", "sum")).reset_index() \
        .rename(columns={"supplier_id": "farm_id"})
    df = deliv.merge(share, on=["farm_id", "crop", "year"], how="left")
    df = df.merge(sv[["record_key", "farm_id", "crop", "year", "fertiliser_product", "irrigated", "yield_t_ha", "has_flag"]
                     + INPUT_COLUMNS], on=["farm_id", "crop", "year"], how="left")
    df["respondent"] = df.record_key.notna()
    med = sv.groupby(["crop", "year"])[INPUT_COLUMNS].median()
    for c in INPUT_COLUMNS:
        fill = pd.Series([med[c].get((cr, y), np.nan) for cr, y in zip(df.crop, df.year)], index=df.index)
        df[c] = df[c].fillna(fill)
    df["declared_area_ha"] = df.declared_area_ha.fillna(df.delivered_kg / 1000 / sv.yield_t_ha.median())
    df["organic_share"] = df.organic_share.fillna(0.0)
    df["organic_share_expected"] = df.organic_share_expected.fillna(0.0)
    df["yield_t_ha"] = df.yield_t_ha.fillna(df.delivered_kg / 1000 / df.declared_area_ha)
    df["irrigated"] = df.irrigated.fillna(False)
    grid = df.year.map(F.GRID_FI_LB).fillna(F.GRID_FI_LB[max(F.GRID_FI_LB)])
    comp = footprint_components_per_ha(df.assign(organic_share=df.organic_share_expected), grid.values)
    for c in COMPONENTS:
        df[f"{c}_tco2e"] = comp[c].values * df.declared_area_ha.values / 1000
    df["tco2e"] = df[[f"{c}_tco2e" for c in COMPONENTS]].sum(axis=1)
    df["kgco2e_per_kg_delivered"] = df.tco2e * 1000 / df.delivered_kg.where(df.delivered_kg > 0)
    df["region"] = "FI_SW"
    df["is_estimate"] = ~df.respondent
    df["has_flag"] = df.has_flag.fillna(False).astype(bool)
    df["footprint_key"] = "farm_footprint:" + df.farm_id + ":" + df.crop + ":" + df.year.astype(str)
    keys = df[["footprint_key", "farm_id", "crop", "year", "record_key"]]
    erp_src = keys.merge(d[["supplier_id", "crop", "year", "record_key"]].rename(
        columns={"supplier_id": "farm_id", "record_key": "source_key"}), on=["farm_id", "crop", "year"])
    lineage = pd.concat([
        pd.DataFrame(dict(derived_key=keys.footprint_key, source_key="farm:" + keys.farm_id)),
        pd.DataFrame(dict(derived_key=keys.footprint_key, source_key=keys.record_key)).dropna(),
        erp_src[["footprint_key", "source_key"]].rename(columns={"footprint_key": "derived_key"}),
    ], ignore_index=True).assign(stage="s4", canonical_table="farm_footprints")
    out = df.rename(columns={"record_key": "survey_record_key"}).rename(columns={"footprint_key": "record_key"})
    return out, lineage
