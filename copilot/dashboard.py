"""Dashboard charts (Part 3). One function per chart; the dashboard API and the copilot's show_chart tool share them,
so a chart shows the same numbers in both places. Each returns
{id, title (the finding, with its figure), kind, unit, rows, status, sources, note?, trust?, series?}."""
from __future__ import annotations

import pandas as pd

from . import data, gold, tools

PLAIN = {  # category -> GHG Protocol name
    "cat01_purchased_goods": "Purchased goods", "cat01_purchased_services": "Purchased services",
    "cat02_capital_goods": "Capital goods", "cat03_fuel_energy": "Fuel- and energy-related activities",
    "cat04_upstream_transport": "Upstream transportation", "cat05_waste": "Waste from operations",
    "cat06_business_travel": "Business travel", "cat07_employee_commuting": "Employee commuting",
    "cat09_downstream_transport": "Downstream transportation", "cat11_use_of_sold_products": "Use of sold products",
    "cat12_end_of_life": "End-of-life of sold products", "fugitive_refrigerants": "Refrigerant leakage",
    "stationary_and_mobile_combustion": "Fuel combustion (sites and vehicles)",
    "purchased_electricity": "Purchased electricity", "purchased_heat_steam": "Purchased heat and steam",
}
ISSUES = {
    "unit_error": "Unit error", "decimal_shift": "Decimal error", "duplicate_record": "Duplicate record",
    "currency_error": "Currency error", "soil_misreport": "Soil type misreported", "material_mismatch": "Material code mismatch",
    "area_mismatch": "Field area mismatch", "outlier_implausible": "Implausible value", "missing_record": "Missing meter reading",
    "missing_leg": "Missing transport leg", "meter_spike": "Meter reading spike", "wrong_gas_code": "Incorrect refrigerant code",
    "mode_mislabel": "Commute mode mislabelled", "pcf_stale_period": "Outdated supplier carbon footprint",
    "certificate_mismatch": "Renewable certificate mismatch", "coordinate_swap": "Coordinate error",
    "pcf_unit_error": "Supplier footprint unit error", "total_mismatch": "Totals mismatch",
}
GROUPS = {"scope1": "Scope 1 – Direct operations", "scope2_market": "Scope 2 – Purchased energy", "scope3": "Scope 3 – Value chain"}
SHORT = {"scope1": "Scope 1 (direct operations)", "scope2_market": "Scope 2 (purchased energy)", "scope3": "Scope 3 (value chain)"}
ACTION = {"correct": "Corrected automatically", "method": "Corrected automatically", "estimate": "Estimated",
          "flag": "Pending expert review"}
SRC = {"li": "Emission calculation (data pipeline)", "issues": "Data-quality findings (data pipeline)",
       "sales": "Sales volumes", "history": "Previously published inventories", "farms": "Farm footprints (data pipeline)",
       "draft": "Draft 2025 report summary", "levers": "Decarbonisation options", "scen": "Transition scenarios",
       "mat": "Materials list", "sup": "Supplier list"}
BASE_YEAR, SBTI_RATE = 2021, 4.2  # approved 2026-11-07: first pipeline year; 1.5 °C linear rate for Scope 1+2


def _t(name: str) -> pd.DataFrame:
    return gold.frame(name)


def _li(year: int | None = None) -> pd.DataFrame:
    """Market-based line items (location-based Scope 2 dropped so nothing is counted twice)."""
    li = _t(gold.GOLD["line_items"])
    li = li[li["scope"] != "scope2_location"]
    return li if year is None else li[li["year"] == year]


def _pct(a: float, b: float) -> float:
    return round(100 * a / b, 1) if b else 0.0


def _big(x: float) -> str:
    return f"{x / 1e6:.1f} million" if abs(x) >= 1e6 else f"{x:,.0f}"


def _out(id, title, kind, rows, sources, year=None, unit="t CO₂e", **extra) -> dict:
    status = tools.signoff_status(year).split(" (")[0] if year else None
    return {"id": id, "title": title, "kind": kind, "unit": unit, "rows": rows, "year": year,
            "status": status, "sources": [SRC[s] for s in sources], **extra}


def _trust(d: pd.DataFrame) -> dict:
    total = float(d["tco2e"].sum())
    est = float(d.loc[d["is_estimate"].astype(bool), "tco2e"].sum())
    flag = float(d.loc[d["flagged"].astype(bool) & ~d["is_estimate"].astype(bool), "tco2e"].sum())
    return {"measured_pct": _pct(total - est - flag, total), "estimated_pct": _pct(est, total), "review_pct": _pct(flag, total)}


# ---- Executive summary ---------------------------------------------------------------------------------------

def kpis(year: int) -> dict:
    d, prev = _li(year), _li(year - 1)
    total, before = float(d["tco2e"].sum()), float(prev["tco2e"].sum())
    s = _t("s4_sales")
    tonnes = float(s.loc[(s["year"] == year) & ~s["is_excluded"].astype(bool), "t_sold"].sum())
    iss = _t(gold.GOLD["issues"])
    open_n = int(((iss["year"] == year) & (iss["status"] == "open")).sum())
    rows = [{"label": "Total emissions (market-based)", "value": round(total), "unit": "t CO₂e"},
            {"label": f"Change vs {year - 1}", "value": _pct(total - before, before) if before else None, "unit": "%"},
            {"label": "Emission intensity", "value": round(total * 1000 / tonnes) if tonnes else None, "unit": "kg CO₂e per tonne sold"},
            {"label": "Findings pending expert review", "value": open_n, "unit": "findings"}]
    return _out("kpis", f"{year} total emissions: {total:,.0f} t CO₂e", "kpis", rows, ["li", "sales", "issues"], year,
                trust=_trust(d))


def scope_split(year: int) -> dict:
    g = _li(year).groupby("scope")["tco2e"].sum()
    total = float(g.sum())
    rows = [{"label": v, "value": round(float(g.get(k, 0))), "pct": _pct(float(g.get(k, 0)), total)} for k, v in GROUPS.items()]
    top = max(GROUPS, key=lambda k: float(g.get(k, 0)))
    return _out("scope_split", f"{SHORT[top]} accounts for {_pct(float(g[top]), total):.0f} % of {year} emissions", "donut",
                rows, ["li"], year,
                note="Scope 1: fuel and refrigerants at our own sites. Scope 2: purchased electricity and heat. "
                     "Scope 3: all other emissions in the value chain, upstream and downstream.")


def trend(year: int | None = None) -> dict:
    g = _li().groupby(["year", "scope"])["tco2e"].sum().unstack(fill_value=0)
    h = _t("s3_published_inventory_history").set_index("year")
    rows = []
    for y in sorted(g.index.astype(int)):
        r = {"year": y, **{v: round(float(g.loc[y].get(k, 0))) for k, v in GROUPS.items()}}
        if y in h.index:
            r["As originally published"] = int(h.loc[y, ["scope1", "scope2_market", "scope3"]].sum())
        rows.append(r)
    tot = lambda r: sum(r[v] for v in GROUPS.values())
    ch = _pct(tot(rows[-1]) - tot(rows[0]), tot(rows[0]))
    return _out("trend", f"Total emissions {'down' if ch < 0 else 'up'} {abs(ch):.0f} % from {rows[0]['year']} to {rows[-1]['year']}",
                "stacked_bar", rows, ["li", "history"], None, series=list(GROUPS.values()),
                note="Markers show totals as originally published, before data validation. Year-on-year changes include "
                     "methodology and organisational changes as well as actual reductions.")


# ---- Emission sources ----------------------------------------------------------------------------------------

def top_categories(year: int) -> dict:
    g = _li(year).groupby("category")["tco2e"].sum().sort_values(ascending=False)
    total = float(g.sum())
    rows = [{"label": PLAIN.get(k, k), "value": round(float(v)), "pct": _pct(float(v), total)} for k, v in g.head(10).items()]
    return _out("top_categories", f"{rows[0]['label']} account for {rows[0]['pct']:.0f} % of {year} emissions", "hbar", rows, ["li"], year)


def top_materials(year: int) -> dict:
    d = _li(year)
    d = d[d["category"] == "cat01_purchased_goods"]
    g = d.groupby("line_item")["tco2e"].sum().sort_values(ascending=False).head(10)
    m = _t("gold_dim_materials").drop_duplicates("material_id").set_index("material_id")["name_en"]
    s = _t("gold_dim_suppliers").drop_duplicates("supplier_id").set_index("supplier_id")["supplier_name"]

    def name(k: str) -> str:
        if k.startswith("contract_farming:"):
            return f"Contract farming: {k.split(':')[-1].replace('_', ' ')}"
        mat, _, sup = k.partition(":")
        return f"{m.get(mat, mat)} · {s.get(sup, sup)}"
    rows = [{"label": name(k), "value": round(float(v))} for k, v in g.items()]
    return _out("top_materials", f"Largest purchased-goods source: {rows[0]['label']} ({rows[0]['value']:,} t CO₂e)",
                "hbar", rows, ["li", "mat", "sup"], year, note="Top 10 material and supplier combinations by emissions.")


def land_use(year: int) -> dict:
    d = _li(year)
    total, flag = float(d["tco2e"].sum()), float(d["flag_tco2e"].sum())
    rows = [{"label": "Agriculture and land use (FLAG)", "value": round(flag), "pct": _pct(flag, total)},
            {"label": "Other emissions", "value": round(total - flag), "pct": _pct(total - flag, total)}]
    return _out("land_use", f"Agriculture and land use account for {rows[0]['pct']:.0f} % of {year} emissions", "split_bar",
                rows, ["li"], year, note="FLAG (forest, land and agriculture) emissions require a separate SBTi reduction target.")


# ---- Agricultural supply chain -------------------------------------------------------------------------------

FARM_SOURCES = {"Organic (peat) soils": ["organic_soil_tco2e"], "Fertiliser manufacture": ["fertiliser_tco2e"],
                "Field emissions from fertiliser (N₂O)": ["direct_n2o_tco2e", "indirect_n2o_tco2e"],
                "Fuel and other inputs": ["diesel_tco2e", "lime_tco2e", "pesticides_tco2e", "electricity_tco2e"]}


def _farms(year: int) -> pd.DataFrame:
    f = _t("gold_farm_footprints")
    return f[f["year"] == year]


def farm_summary(year: int) -> dict:
    f = _farms(year)
    t, kg, total = float(f["tco2e"].sum()), float(f["delivered_kg"].sum()), float(_li(year)["tco2e"].sum())
    rows = [{"label": "Contract-farm emissions", "value": round(t), "unit": "t CO₂e"},
            {"label": "Share of company total", "value": _pct(t, total), "unit": "%"},
            {"label": "Contract farms", "value": int(f["farm_id"].nunique()), "unit": "farms"},
            {"label": "Average intensity", "value": round(1000 * t / kg, 2) if kg else None, "unit": "kg CO₂e per kg delivered"}]
    return _out("farm_summary", f"Contract farms emitted {t:,.0f} t CO₂e in {year}, {_pct(t, total):.0f} % of the company total",
                "kpis", rows, ["farms", "li"], year,
                note="Crops grown for the company by Finnish contract farms. Other agricultural emissions, such as imported "
                     "rapeseed and dairy, are reported under Purchased goods.")


def farm_sources(year: int) -> dict:
    f = _farms(year)
    total = float(f["tco2e"].sum())
    rows = sorted(({"label": k, "value": round(float(f[cols].sum().sum())), "pct": _pct(float(f[cols].sum().sum()), total)}
                   for k, cols in FARM_SOURCES.items()), key=lambda r: -r["value"])
    return _out("farm_sources", f"{rows[0]['label']} account for {rows[0]['pct']:.0f} % of contract-farm emissions", "hbar",
                rows, ["farms"], year,
                note="Drained peat soils release CO₂ continuously as organic matter decomposes, whatever crop is grown.")


def farm_concentration(year: int) -> dict:
    f = _farms(year).groupby("farm_id").agg(t=("tco2e", "sum"), org=("organic_ha", "sum"))
    peat = f["org"] > 0
    farms_pct, em_pct = _pct(int(peat.sum()), len(f)), _pct(float(f.loc[peat, "t"].sum()), float(f["t"].sum()))
    rows = [{"label": "Share of farms", "Farms with peat soils": farms_pct, "Farms on mineral soils only": round(100 - farms_pct, 1)},
            {"label": "Share of emissions", "Farms with peat soils": em_pct, "Farms on mineral soils only": round(100 - em_pct, 1)}]
    return _out("farm_concentration", f"{farms_pct:.0f} % of contract farms (those with peat soils) produce {em_pct:.0f} % of contract-farm emissions",
                "stacked_100", rows, ["farms"], year, unit="%", series=["Farms with peat soils", "Farms on mineral soils only"],
                note="Peat soils: any field classified as organic soil on the national soil map.")


def crop_intensity(year: int) -> dict:
    f = _farms(year).groupby("crop")[["tco2e", "delivered_kg"]].sum()
    rows = sorted(({"label": c.replace("_", " ").capitalize(), "value": round(1000 * r.tco2e / r.delivered_kg, 2),
                    "volume_t": round(r.delivered_kg / 1000)} for c, r in f.iterrows() if r.delivered_kg), key=lambda r: -r["value"])
    return _out("crop_intensity", f"{rows[0]['label']} has the highest emission intensity: {rows[0]['value']} kg CO₂e per kg delivered",
                "hbar", rows, ["farms"], year, unit="kg CO₂e per kg delivered",
                note="Volume delivered (tonnes) is shown for each crop: a high intensity matters most where volumes are large.")


# ---- Data quality & assurance --------------------------------------------------------------------------------

def corrections(year: int) -> dict:
    raw, st = data.inventory(year)
    if st != "naive":
        return _out("corrections", "No unvalidated baseline available for comparison", "waterfall", [], ["li"], year)
    raw = raw[(raw["scope"] != "scope2_location") & (raw["scope"] != "memo")]
    a, b = raw.groupby("category")["tco2e"].sum(), _li(year).groupby("category")["tco2e"].sum()
    delta = b.sub(a, fill_value=0).sort_values(key=abs, ascending=False)
    start, end = float(a.sum()), float(b.sum())
    draft = year == 2025
    rows = [{"label": "Draft report (unvalidated)" if draft else "Unvalidated data", "value": round(start), "type": "total"}]
    rows += [{"label": PLAIN.get(k, k), "value": round(float(v)), "type": "delta"} for k, v in delta.head(5).items()]
    rows.append({"label": "Other corrections", "value": round(float(delta.iloc[5:].sum())), "type": "delta"})
    rows.append({"label": "Validated total", "value": round(end), "type": "total"})
    verb = "reduced" if end < start else "increased"
    return _out("corrections", f"Data validation {verb} the {year} total from {_big(start)} to {_big(end)} t CO₂e",
                "waterfall", rows, ["li", "issues"] + (["draft"] if draft else []), year,
                note="The draft 2025 report was prepared from unvalidated source data; its figures match our unvalidated calculation exactly."
                if draft else None)


def issues_by_type(year: int) -> dict:
    i = _t(gold.GOLD["issues"])
    i = i[i["year"] == year]
    g = i.groupby(["issue_type", "action"]).size().reset_index(name="n")
    rows = [{"label": ISSUES.get(r.issue_type, r.issue_type), "outcome": ACTION.get(r.action, r.action), "value": int(r.n)}
            for r in g.sort_values("n", ascending=False).itertuples()]
    n = lambda o: sum(r["value"] for r in rows if r["outcome"] == o)
    return _out("issues_by_type", f"{sum(r['value'] for r in rows)} data-quality findings in {year}: "
                f"{n('Corrected automatically')} corrected, {n('Estimated')} estimated, {n('Pending expert review')} pending review",
                "hbar_stacked", rows, ["issues"], year, unit="findings", series=list(dict.fromkeys(ACTION.values())))


def published_vs_checked(year: int | None = None) -> dict:
    rows = [{"year": r["year"], "Validated": sum(r[k] for k in GROUPS.values()), "As originally published": r.get("As originally published")}
            for r in trend()["rows"]]
    gaps = [_pct(r["Validated"] - r["As originally published"], r["As originally published"]) for r in rows if r["As originally published"]]
    worst = max(gaps, key=abs)
    return _out("published_vs_checked", f"Validated totals differ from published figures by up to {worst:+.0f} %", "grouped_bar", rows,
                ["li", "history"], None, series=["Validated", "As originally published"])


# ---- Decarbonisation pathway ---------------------------------------------------------------------------------

def target_path(year: int | None = None) -> dict:
    d = _li()
    d = d[d["scope"].isin(["scope1", "scope2_market"])].groupby("year")["tco2e"].sum()
    base = float(d.loc[BASE_YEAR])
    target = lambda y: tools.sbti_target(base, SBTI_RATE, BASE_YEAR, y)["target_tco2e"]
    rows = [{"year": y, "Actual": round(float(d[y])) if y in d.index else None, "1.5 °C pathway": target(y)} for y in range(BASE_YEAR, 2031)]
    last = max(int(y) for y in d.index)
    gap = _pct(float(d[last]) - target(last), target(last))
    return _out("target_path", f"Scope 1 and 2 emissions are {abs(gap):.0f} % {'below' if gap <= 0 else 'above'} the 1.5 °C pathway ({last})",
                "line", rows, ["li"], None, series=["Actual", "1.5 °C pathway"],
                note=f"Pathway: {BASE_YEAR} baseline reduced by {SBTI_RATE} % of the baseline each year "
                     "(SBTi 1.5 °C, linear absolute contraction). Scope 1 and 2 only.")


def levers(year: int | None = None) -> dict:
    lv = _t("s3_decarbonisation_levers")
    lv = lv[(lv["abatement_tco2e_2030_design"] > 0) & lv["indicative_cost_eur_per_tco2e"].notna()]
    lv = lv.sort_values("indicative_cost_eur_per_tco2e")
    rows = [{"label": r.name, "value": int(r.abatement_tco2e_2030_design), "cost": float(r.indicative_cost_eur_per_tco2e),
             "start": int(r.earliest_start), "confidence": r.confidence} for r in lv.itertuples()]
    cheap = sum(r["value"] for r in rows if r["cost"] <= 0)
    return _out("levers", f"{len(rows)} reduction measures identified; {cheap:,} t CO₂e per year achievable at a net saving",
                "lever_bars", rows, ["levers"], None, unit="t CO₂e abated per year by 2030",
                note="Abatement and cost figures are design estimates from the scenario dataset, not yet validated against the inventory.")


def carbon_cost(year: int) -> dict:
    s1 = float(_li(year).query("scope == 'scope1'")["tco2e"].sum())
    sc = _t("s3_transition_scenarios")
    pick = {"net_zero_2050": "Net zero 2050", "delayed_transition": "Delayed transition", "current_policies": "Current policies"}
    sc = sc[sc["scenario"].isin(pick)]
    rows = [{"year": int(y), **{pick[k]: round(s1 * float(p) / 1e6, 2) for k, p in g.set_index("scenario")["carbon_price_eur_t"].items()}}
            for y, g in sc.groupby("year")]
    hi = max(rows[-1][v] for v in pick.values())
    return _out("carbon_cost", f"Carbon pricing on Scope 1 could cost up to €{hi:.1f} M per year by {rows[-1]['year']}",
                "line", rows, ["li", "scen"], year, unit="€ million per year", series=list(pick.values()),
                note=f"{year} Scope 1 emissions ({s1:,.0f} t CO₂e) × carbon price under each NGFS scenario. Scenario prices are illustrative.")


CHARTS = {f.__name__: f for f in (kpis, scope_split, trend, top_categories, top_materials, land_use, corrections, issues_by_type,
                                    published_vs_checked, target_path, levers, carbon_cost, farm_summary, farm_sources,
                                    farm_concentration, crop_intensity)}
SECTIONS = [  # executive reading order
    {"id": "summary", "title": "Executive summary", "intro": "Total emissions, intensity and trend, with data status.",
     "charts": ["kpis", "scope_split", "trend"]},
    {"id": "sources", "title": "Emission sources", "intro": "Where emissions arise, by GHG Protocol category and supplier.",
     "charts": ["top_categories", "land_use", "top_materials"]},
    {"id": "quality", "title": "Data quality & assurance", "intro": "How source data was validated and what remains for expert review.",
     "charts": ["corrections", "issues_by_type", "published_vs_checked"]},
    {"id": "pathway", "title": "Decarbonisation pathway", "intro": "Progress against the 1.5 °C pathway, reduction measures and carbon-price exposure.",
     "charts": ["target_path", "levers", "carbon_cost"]},
    {"id": "agriculture", "title": "Agricultural supply chain", "intro": "Emissions from contract farms growing crops for the company.",
     "charts": ["farm_summary", "farm_sources", "farm_concentration", "crop_intensity"]},
]


def chart(chart_id: str, year: int = 2025) -> dict:
    if chart_id not in CHARTS:
        return {"error": f"unknown chart_id {chart_id!r}; use one of {', '.join(CHARTS)}"}
    if not gold.has("line_items"):
        return {"error": "the data pipeline has not run yet, so dashboard charts are unavailable"}
    return CHARTS[chart_id](int(year))


def dashboard(year: int = 2025) -> dict:
    return {"year": year, "sections": SECTIONS, "charts": {k: chart(k, year) for k in CHARTS}}
