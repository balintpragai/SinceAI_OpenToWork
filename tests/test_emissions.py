"""Allocation and S3 tests: non-linear steps shared out to records must sum to the site-level
result (ADR 0001); review decisions change what S3 applies."""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.correct import stage_s3
from pipeline.farm import COMPONENTS, footprint_components_per_ha, organic_share


def test_goo_cover_allocation_sums_to_site_level():
    from pipeline.emissions import emission_line_items
    from pipeline.refdata import F
    el = pd.DataFrame(dict(record_key=["e1", "e2", "e3"], site_id="S-SAK", year=2025, month=[1, 2, 3], carrier="electricity",
                           mwh=[100.0, 200.0, 300.0], is_estimate=False, has_flag=False))
    ids = ["EF-ELEC-UPSTREAM-FI", "EF-HEAT-UPSTREAM", "EF-PALLETDAY-FROZEN", "EF-WASTEWATER-MUNI", "EF-PKM-FLIGHT-SHORT",
           "EF-PKM-TRAIN", "EF-HOTEL-NIGHT", "EF-PKM-CAR", "EF-PKM-BUS"]
    efl = pd.DataFrame(dict(ef_id=ids, kgco2e_per_unit=10.0, reference_source="x", value_status="y", version=2025, flag_share=0.0))
    text = {"record_key", "site_id", "carrier", "unit", "refrigerant", "material_id", "supplier_id", "farm_id", "crop",
            "region", "direction", "ef_id", "waste_stream", "mode", "product_group", "market"}
    empty = lambda cols: pd.DataFrame({c: pd.Series(dtype=object if c in text else float) for c in cols})  # noqa: E731
    T = dict(energy=el, sites=pd.DataFrame(dict(site_id=["S-SAK"], country=["FI"])), ef_library=efl,
             goo=pd.DataFrame(dict(site_id=["S-SAK"], year=[2025], vintage_year=[2025], mwh_cancelled=[450.0])),
             heat_suppliers=empty(["site_id", "year", "t_per_mwh"]),
             refrigerants=empty(["record_key", "site_id", "year", "refrigerant", "kg_added"]),
             purchases=empty(["record_key", "year", "material_id", "supplier_id", "qty_kg", "amount_eur", "is_estimate", "has_flag"]),
             materials=pd.DataFrame(dict(material_id=["M900"], material_group=["service"], default_ef_id=["EF-S"])),
             pcf_used=empty(["record_key", "year", "supplier_id", "material_id", "kgco2e_per_kg"]),
             farm_footprints=empty(["year", "farm_id", "crop", "delivered_kg", "region", "record_key", "is_estimate"]
                                   + [f"{c}_tco2e" for c in COMPONENTS]),
             shipments=empty(["record_key", "year", "direction", "ef_id", "tkm"]), warehousing=empty(["record_key", "year", "pallet_days"]),
             waste=empty(["record_key", "year", "site_id", "waste_stream", "ef_id", "t"]), wastewater=empty(["record_key", "year", "m3"]),
             travel=empty(["record_key", "year", "mode", "pkm", "nights"]),
             commuting_survey=empty(["record_key", "site_id", "one_way_km", "days_on_site_per_week", "mode"]),
             headcount=empty(["year", "site_id", "headcount"]), sales=empty(["record_key", "year", "product_group", "market", "t_sold"]))
    s3 = dict(fuel_deliveries=empty(["record_key", "year", "site_id", "carrier", "unit", "quantity", "is_excluded"]),
              fuel_stock_changes=empty(["record_key", "year", "site_id", "carrier", "unit", "stock_change"]))
    s3["fuel_deliveries"]["is_excluded"] = s3["fuel_deliveries"].is_excluded.astype(bool)
    eli = emission_line_items(T, s3, [2025])
    mb = eli[eli.scope == "scope2_market"]
    assert mb.tco2e.sum() == pytest.approx((600 - 450) * F.RESIDUAL_FI[2025])
    assert set(mb.allocation) == {"goo_cover_pro_rata"}


def test_organic_share_counts_only_declared_parcels_and_weights_low_clay():
    parcels = pd.DataFrame(dict(parcel_id=["P1", "P2", "P3"], area_ha=[10.0, 10.0, 20.0],
                                soil_class_soilmap=["organic", "clay", "clay"], clay_pct_soilmap=[12.0, 5.0, 45.0]))
    ch = pd.DataFrame(dict(parcel_id=["P1", "P2", "P3"], farm_id="F1", year=2025, crop="pea", status="declared"))
    g = organic_share(parcels, ch, low_clay_probability=0.5).iloc[0]
    assert g.declared_area_ha == 40 and g.organic_share == pytest.approx(0.25)
    assert g.organic_share_expected == pytest.approx((10 + 0.5 * 10) / 40)


def test_organic_soil_component_scales_with_share():
    df = pd.DataFrame(dict(crop="pea", n_mineral_kg_ha=0, n_manure_kg_ha=0, p_kg_ha=0, diesel_l_ha=0, lime_t_ha=0, sprays=0,
                           yield_t_ha=0, irrigated=False, organic_share=[0.0, 0.5, 1.0]))
    c = footprint_components_per_ha(df, 0.03)
    assert c.organic_soil.iloc[0] == 0 and c.organic_soil.iloc[2] == pytest.approx(2 * c.organic_soil.iloc[1])


def _s1_and_issues():
    s1 = {"t": pd.DataFrame(dict(record_key=["k1", "k2"], v=[1.0, 2.0]))}
    issues = pd.DataFrame([
        dict(issue_id="i1", table="t", record_key="k1", year=2025, issue_type="unit_error", rule_id="R1", action="correct",
             confidence=0.9, field="v", observed_value="1.0", proposed_value="1000.0", evidence="e", changes={"v": 1000.0},
             drop=False, new_row=None),
        dict(issue_id="i2", table="t", record_key="k2", year=2025, issue_type="outlier_implausible", rule_id="R2",
             action="flag", confidence=0.8, field="v", observed_value="2.0", proposed_value=None, evidence="e", changes={},
             drop=False, new_row=None)])
    return s1, issues


def test_s3_applies_correction_and_marks_flag():
    s1, issues = _s1_and_issues()
    t, corr, st = stage_s3(s1, issues, None, "run-x")
    assert t["t"].v.tolist() == [1000.0, 2.0] and t["t"].has_flag.tolist() == [False, True]
    assert corr.iloc[0][["old_value", "new_value", "kind", "status"]].tolist() == ["1.0", "1000.0", "correction", "auto_applied"]
    assert dict(zip(st.issue_id, st.status)) == {"i1": "auto_applied", "i2": "open"}


def test_s3_review_reject_and_override():
    s1, issues = _s1_and_issues()
    reviews = pd.DataFrame([
        dict(decision_id="d1", issue_id="i1", decision="reject", override_field=None, override_value=None, reviewer="minna",
             decided_at="2026-11-07T10:00:00", comment=""),
        dict(decision_id="d2", issue_id="i2", decision="override", override_field="v", override_value="0.2", reviewer="minna",
             decided_at="2026-11-07T10:01:00", comment="")])
    t, corr, st = stage_s3(s1, issues, reviews, "run-x")
    assert t["t"].v.tolist() == [1.0, 0.2]
    assert dict(zip(st.issue_id, st.status)) == {"i1": "rejected", "i2": "overridden"}
    assert corr.iloc[0][["proposed_by", "approved_by", "rule_or_model"]].tolist() == ["minna", "minna", "reviewer_override"]
