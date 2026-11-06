"""Unit tests per rule: each rule fires on a hand-made planted issue and stays silent on the
legitimate oddities named in docs/TASKS_AND_SCORING.md (A1): credit notes, vessel lots in tonnes,
seasonal meter peaks and ammonia systems."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.boundary import Boundary
from pipeline.rules import Context
from pipeline.rules import farming as fr
from pipeline.rules import feeds as fe
from pipeline.standardise import standardise

SITES = pd.DataFrame(dict(site_id=["S-SAK", "S-BJU", "S-HQ"], name=["Säkylä plant", "Bjuv plant (Foodhills)", "Helsinki head office"],
                          country=["FI", "SE", "FI"], in_group_from=[1990, 2025, 1990], in_group_to=[np.nan, np.nan, np.nan]))
EVENTS = pd.DataFrame(dict(date=["2025-11-27"], event=["Foodhills AB (Bjuv, Sweden; frozen peas) acquired"],
                           type=["acquisition"], relevance=[""], source=["public"]))
MATERIALS = pd.DataFrame(dict(material_id=["M120", "M126", "M102", "M900"],
                              erp_name=["Maissi pakaste", "Vihannessekoitus raaka-aine, tuonti", "Rapsi siemen, tuonti EE", "Ostopalvelut"],
                              default_ef_id=["EF-A", "EF-B", "EF-C", "EF-S"], material_group=["vegetable_bought"] * 2 + ["oilseed", "service"]))


def ctx_with(**tables) -> Context:
    t = dict(sites=SITES, structural_events=EVENTS, materials=MATERIALS)
    t.update(tables)
    return Context(tables=t, boundary=Boundary(SITES, EVENTS))


def keys(issues):
    return sorted(i["record_key"] for i in issues)


# ------------------------------------------------------------------------------------------------ ERP

def erp_frame(rows):
    base = dict(line_no=10, company_code="C100", plant="S-SAK", origin_country="FI", lot_id=None, reference_doc=None,
                wbs_element=None, movement_type=101, uom="KG", currency="EUR", material_id="M120",
                material_text="Maissi pakaste", supplier_id="SUP024")
    df = pd.DataFrame([{**base, **r} for r in rows])
    df["record_key"] = "erp:" + df.doc_no + ":" + df.line_no.astype(str)
    return standardise("erp_purchase_lines", df)


def normal_lines(n=12, **kw):
    return [dict(doc_no=f"45{i:08d}", posting_date=f"2025-0{1 + i % 9}-1{i % 9}", quantity=1000.0 + 10 * i,
                 net_amount=1300.0 + 13 * i, **kw) for i in range(n)]


def test_erp_unit_error_fires_and_credit_note_and_vessel_lot_do_not():
    rows = normal_lines()
    rows.append(dict(doc_no="4599999901", posting_date="2025-05-05", quantity=1.2, net_amount=1560.0))        # tonnes as KG
    rows.append(dict(doc_no="5199999901", posting_date="2025-05-06", quantity=-500.0, net_amount=-650.0,
                     movement_type=122, reference_doc="4500000001"))                                          # credit note
    rows.append(dict(doc_no="4599999902", posting_date="2025-05-07", quantity=2.0, net_amount=2600.0, uom="TO"))  # vessel lot
    issues = fe.erp_unit(ctx_with(erp_purchase_lines=erp_frame(rows)))
    assert keys(issues) == ["erp:4599999901:10"]
    assert issues[0]["changes"]["qty_kg"] == pytest.approx(1200.0)


def test_erp_decimal_shift():
    rows = normal_lines() + [dict(doc_no="4599999903", posting_date="2025-05-05", quantity=120.0, net_amount=1560.0)]
    issues = fe.erp_decimal(ctx_with(erp_purchase_lines=erp_frame(rows)))
    assert keys(issues) == ["erp:4599999903:10"]
    assert issues[0]["changes"]["quantity"] == pytest.approx(1200.0)


def test_erp_currency_from_supplier_pattern():
    rows = normal_lines(10, currency="USD", supplier_id="SUP036") + \
        [dict(doc_no="4599999904", posting_date="2025-03-03", quantity=1000.0, net_amount=1400.0, supplier_id="SUP036")]
    issues = fe.erp_currency(ctx_with(erp_purchase_lines=erp_frame(rows)))
    assert keys(issues) == ["erp:4599999904:10"]
    assert issues[0]["changes"]["currency"] == "USD"


def test_erp_duplicate_later_row_only():
    rows = normal_lines(3)
    rows.append(dict(doc_no="5100000351", posting_date="2025-01-12", quantity=1000.0, net_amount=1300.0))  # copy of first
    issues = fe.erp_duplicate(ctx_with(erp_purchase_lines=erp_frame(rows)))
    assert keys(issues) == ["erp:5100000351:10"] and issues[0]["drop"]


def test_erp_material_mismatch_uses_text():
    rows = normal_lines(3) + [dict(doc_no="4599999905", posting_date="2025-02-02", quantity=1000.0, net_amount=1300.0,
                                   material_id="M126", material_text="Maissi pakaste")]
    issues = fe.erp_material(ctx_with(erp_purchase_lines=erp_frame(rows)))
    assert keys(issues) == ["erp:4599999905:10"] and issues[0]["changes"]["material_id"] == "M120"


# --------------------------------------------------------------------------------------------- energy

PROFILE = np.array([8, 8, 9, 9, 10, 12, 16, 16, 12, 10, 9, 8], dtype=float)   # summer pea-season peak


def meter_frame(site="S-SAK", years=(2021, 2022, 2023, 2024, 2025), edit=None, drop=()):
    rows = []
    for y in years:
        for m in range(1, 13):
            if (y, m) in drop:
                continue
            v = PROFILE[m - 1] * 100 * (1 + 0.02 * (y - 2021))
            if edit and (y, m) in edit:
                v = edit[(y, m)](v)
            rows.append(dict(site_id=site, year=y, month=m, carrier="electricity", value=v, unit="MWh"))
    df = pd.DataFrame(rows)
    df["record_key"] = "energy:" + df.site_id + ":" + df.year.astype(str) + "-" + df.month.map("{:02d}".format) + ":" + df.carrier
    return standardise("energy_meter_readings", df)


def fresh(df):
    return ctx_with(energy_meter_readings=df)


def test_energy_seasonal_peak_is_not_a_spike_but_a_real_spike_is():
    ctx = fresh(meter_frame(edit={(2024, 3): lambda v: v * 3.5}))
    spikes = fe.energy_spike(ctx)
    assert keys(spikes) == ["energy:S-SAK:2024-03:electricity"]
    assert spikes[0]["changes"]["mwh"] == pytest.approx(PROFILE[2] * 100 * 1.06, rel=0.02)


def test_energy_unit_error_kwh():
    issues = fe.energy_unit(fresh(meter_frame(edit={(2023, 5): lambda v: v * 1000})))
    assert keys(issues) == ["energy:S-SAK:2023-05:electricity"]


def test_energy_missing_month_estimated_with_seasonal_profile_incl_december():
    ctx = fresh(meter_frame(drop={(2024, 7), (2025, 12)}))
    issues = fe.energy_missing(ctx)
    assert keys(issues) == ["energy:S-SAK:2024-07:electricity", "energy:S-SAK:2025-12:electricity"]
    jul = [i for i in issues if "2024-07" in i["record_key"]][0]
    assert jul["new_row"]["mwh"] == pytest.approx(PROFILE[6] * 100 * 1.06, rel=0.02)


def test_no_estimates_outside_the_organisational_boundary():
    # Bjuv joins in Dec 2025: Jan-Nov 2025 are outside the boundary, not missing.
    df = meter_frame(site="S-BJU", years=(2025,), drop={(2025, m) for m in range(1, 12)})
    assert fe.energy_missing(fresh(df)) == []


# ------------------------------------------------------------------------------------- refrigerants etc.

def test_refrigerant_ammonia_system_is_legitimate_but_r717_on_hfc_system_is_not():
    rf = pd.DataFrame(dict(site_id="S-SAK", system=["Main freezing plant"] * 3 + ["Cold store 2"] * 4,
                           refrigerant=["R717_ammonia"] * 3 + ["R404A", "R404A", "R404A", "R717_ammonia"],
                           year=2025, kg_added=[50.0, 60.0, 55.0, 10.0, 12.0, 11.0, 9.0],
                           event_id=[f"RS{i}" for i in range(7)]))
    rf["record_key"] = "refrigerant:" + rf.event_id
    issues = fe.refrigerant_gas(ctx_with(refrigerant_service_log=rf))
    assert keys(issues) == ["refrigerant:RS6"] and issues[0]["changes"]["refrigerant"] == "R404A"


def test_travel_duplicate_flags_later_row():
    t = pd.DataFrame(dict(year=2025, traveller_id=["E1", "E1", "E2"], travel_date="2025-03-01", mode="flight",
                          route="HEL-AMS", pkm=3000.0, nights=1, booking_id=["B1", "B2", "B3"]))
    t["record_key"] = "travel:" + t.booking_id
    assert keys(fe.travel_duplicate(ctx_with(travel_bookings=t))) == ["travel:B2"]


def test_commuting_labels_and_metres():
    c = pd.DataFrame(dict(response_id=["C1", "C2", "C3", "C4"], site_id="S-SAK", one_way_km=[12.0, 25300.0, 9.0, 15.0],
                          mode=["car", "car", "henkilöauto", "linja-auto"], days_on_site_per_week=5, shift_worker=False))
    c["record_key"] = "commute:" + c.response_id
    ctx = ctx_with(commuting_survey=standardise("commuting_survey", c))
    assert keys(fe.commute_unit(ctx)) == ["commute:C2"]
    m = {i["record_key"]: i["changes"].get("mode") for i in fe.commute_mode(ctx)}
    assert m == {"commute:C3": "car", "commute:C4": "bus"}


# ------------------------------------------------------------------------------------- PCFs and report

def test_pcf_unit_and_stale_period():
    p = pd.DataFrame(dict(supplier_id="SUP011", material_id="M104", year=[2024, 2025, 2025],
                          pcf_excl_biogenic=[1.35, 1409.1, 1.2], pcf_incl_biogenic=[1.35, 1409.1, 1.2], declared_unit="kilogram",
                          ref_start=["2024-01-01", "2025-01-01", "2022-01-01"], ref_end=["2025-01-01", "2026-01-01", "2023-01-01"]))
    p.loc[2, "supplier_id"] = "SUP022"
    p["record_key"] = "pcf:" + p.supplier_id + ":" + p.material_id + ":" + p.year.astype(str)
    ctx = ctx_with(supplier_pcfs=p)
    assert keys(fr.pcf_unit(ctx)) == ["pcf:SUP011:M104:2025"]
    assert keys(fr.pcf_stale(ctx)) == ["pcf:SUP022:M104:2025"]


def test_report_total_mismatch_finds_transposed_digits():
    r = pd.DataFrame(dict(year=2025, line=["scope1", "scope2_market", "scope3", "total_market_based"],
                          tco2e=[132163, 1117417, 71534593, 18784173], status="preliminary"))
    r["record_key"] = "report:2025:" + r.line
    issues = fr.report_total(ctx_with(draft_report_summary=r))
    assert keys(issues) == ["report:2025:scope3", "report:2025:total_market_based"]
    assert issues[0]["changes"]["tco2e"] == 17534593


def test_coordinate_swap():
    f = pd.DataFrame(dict(farm_id=["F1", "F2"], lat=[61.0, 22.5], lon=[22.5, 61.0], country="FI"))
    f["record_key"] = "farm:" + f.farm_id
    assert keys(fr.coordinate_swap(ctx_with(farm_registry=f))) == ["farm:F2"]
