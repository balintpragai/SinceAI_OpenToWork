"""Dashboard charts (Part 3). One function per chart; the dashboard API and the copilot's show_chart tool share them,
so a chart shows the same numbers in both places. Each returns
{id, title (the takeaway), kind, unit, rows, status, sources, note?, trust?}."""
from __future__ import annotations

import pandas as pd

from . import data, gold, tools

PLAIN = {  # category -> words a non-specialist understands
    "cat01_purchased_goods": "Ingredients & materials bought", "cat01_purchased_services": "Services bought",
    "cat02_capital_goods": "Machinery & buildings", "cat03_fuel_energy": "Producing our fuel & power",
    "cat04_upstream_transport": "Inbound transport", "cat05_waste": "Waste", "cat06_business_travel": "Business travel",
    "cat07_employee_commuting": "Employee commuting", "cat09_downstream_transport": "Outbound transport",
    "cat11_use_of_sold_products": "Cooking & storing our products", "cat12_end_of_life": "Packaging disposal",
    "fugitive_refrigerants": "Refrigerant leaks", "stationary_and_mobile_combustion": "Fuel burned on site & in vehicles",
    "purchased_electricity": "Electricity", "purchased_heat_steam": "Heat & steam",
}
ISSUES = {  # issue type -> plain name
    "unit_error": "Wrong unit", "decimal_shift": "Misplaced decimal point", "duplicate_record": "Duplicate record",
    "currency_error": "Wrong currency", "soil_misreport": "Soil type misreported", "material_mismatch": "Wrong material code",
    "area_mismatch": "Field area doesn't match", "outlier_implausible": "Implausible value", "missing_record": "Missing meter month",
    "missing_leg": "Missing transport leg", "meter_spike": "Meter spike", "wrong_gas_code": "Wrong refrigerant gas",
    "mode_mislabel": "Commute mode mislabelled", "pcf_stale_period": "Outdated supplier footprint",
    "certificate_mismatch": "Green-power certificate mismatch", "coordinate_swap": "Swapped coordinates",
    "pcf_unit_error": "Supplier footprint unit error", "total_mismatch": "Totals don't add up",
}
GROUPS = {"scope1": "Own operations", "scope2_market": "Purchased energy", "scope3": "Supply chain"}
ACTION = {"correct": "Fixed automatically", "method": "Fixed automatically", "estimate": "Filled with an estimate", "flag": "Needs expert review"}
SRC = {"li": "Emission calculation (data pipeline)", "issues": "Data-quality findings (data pipeline)",
       "sales": "Sales volumes", "history": "Previously published inventories", "farms": "Farm footprints (data pipeline)",
       "parcels": "Field parcels", "draft": "Draft 2025 report summary", "levers": "Decarbonisation options",
       "scen": "Transition scenarios", "mat": "Materials list", "sup": "Supplier list"}
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


# ---- 1. Overview ---------------------------------------------------------------------------------------------

def kpis(year: int) -> dict:
    d, prev = _li(year), _li(year - 1)
    total, before = float(d["tco2e"].sum()), float(prev["tco2e"].sum())
    s = _t("s4_sales")
    tonnes = float(s.loc[(s["year"] == year) & ~s["is_excluded"].astype(bool), "t_sold"].sum())
    iss = _t(gold.GOLD["issues"])
    open_n = int(((iss["year"] == year) & (iss["status"] == "open")).sum())
    rows = [{"label": "Total emissions", "value": round(total), "unit": "t CO₂e"},
            {"label": f"Change vs {year - 1}", "value": _pct(total - before, before) if before else None, "unit": "%"},
            {"label": "Per tonne of product sold", "value": round(total * 1000 / tonnes) if tonnes else None, "unit": "kg CO₂e"},
            {"label": "Items needing expert review", "value": open_n, "unit": "items"}]
    return _out("kpis", f"{year} emissions: about {total:,.0f} t CO₂e", "kpis", rows, ["li", "sales", "issues"], year,
                trust=_trust(d))


def scope_split(year: int) -> dict:
    d = _li(year)
    g = d.groupby("scope")["tco2e"].sum()
    total = float(g.sum())
    rows = [{"label": GROUPS[k], "value": round(float(g.get(k, 0))), "pct": _pct(float(g.get(k, 0)), total)} for k in GROUPS]
    top = max(rows, key=lambda r: r["value"])
    return _out("scope_split", f"{top['label']} is {top['pct']:.0f} % of {year} emissions", "donut", rows, ["li"], year,
                note="Own operations = fuel and refrigerants on our sites; purchased energy = electricity and heat we buy; "
                     "supply chain = everything upstream and downstream.")


def trend(year: int | None = None) -> dict:
    d = _li()
    g = d.groupby(["year", "scope"])["tco2e"].sum().unstack(fill_value=0)
    h = _t("s3_published_inventory_history").set_index("year")
    rows = []
    for y in sorted(g.index.astype(int)):
        r = {"year": y, **{GROUPS[k]: round(float(g.loc[y].get(k, 0))) for k in GROUPS}}
        if y in h.index:
            r["Previously published"] = int(h.loc[y, ["scope1", "scope2_market", "scope3"]].sum())
        rows.append(r)
    first, last = rows[0], rows[-1]
    tot = lambda r: sum(r[k] for k in GROUPS.values())
    ch = _pct(tot(last) - tot(first), tot(first))
    return _out("trend", f"Emissions {'fell' if ch < 0 else 'rose'} {abs(ch):.0f} % from {first['year']} to {last['year']}",
                "stacked_bar", rows, ["li", "history"], None, series=list(GROUPS.values()),
                note="Dots show what was published at the time, before our data cleaning. "
                     "Changes can come from method or company-structure changes, not only real reductions.")


# ---- 2. What drives our footprint ----------------------------------------------------------------------------

def top_categories(year: int) -> dict:
    d = _li(year)
    g = d.groupby("category")["tco2e"].sum().sort_values(ascending=False)
    total = float(g.sum())
    rows = [{"label": PLAIN.get(k, k), "value": round(float(v)), "pct": _pct(float(v), total)} for k, v in g.head(10).items()]
    return _out("top_categories", f"{rows[0]['label']}: {rows[0]['pct']:.0f} % of {year} emissions", "hbar", rows, ["li"], year)


def top_materials(year: int) -> dict:
    d = _li(year)
    d = d[d["category"] == "cat01_purchased_goods"]
    g = d.groupby("line_item")["tco2e"].sum().sort_values(ascending=False).head(10)
    m = _t("gold_dim_materials").drop_duplicates("material_id").set_index("material_id")["name_en"]
    s = _t("gold_dim_suppliers").drop_duplicates("supplier_id").set_index("supplier_id")["supplier_name"]

    def name(k: str) -> str:
        if k.startswith("contract_farming:"):
            return f"Contract farms: {k.split(':')[-1].replace('_', ' ')}"
        mat, _, sup = k.partition(":")
        return f"{m.get(mat, mat)} · {s.get(sup, sup)}"
    rows = [{"label": name(k), "value": round(float(v))} for k, v in g.items()]
    return _out("top_materials", f"Biggest single source: {rows[0]['label']}", "hbar", rows, ["li", "mat", "sup"], year)


def land_use(year: int) -> dict:
    d = _li(year)
    total, flag = float(d["tco2e"].sum()), float(d["flag_tco2e"].sum())
    rows = [{"label": "Farming & land use", "value": round(flag), "pct": _pct(flag, total)},
            {"label": "Everything else", "value": round(total - flag), "pct": _pct(total - flag, total)}]
    return _out("land_use", f"{rows[0]['pct']:.0f} % of {year} emissions come from farming and land use", "split_bar",
                rows, ["li"], year, note="Land-use emissions (fields, fertiliser, soils) have their own reduction target under SBTi FLAG.")


# ---- 3. Farm to freezer --------------------------------------------------------------------------------------

COMPONENTS = {"fertiliser_tco2e": "Making fertiliser", "direct_n2o_tco2e": "Fertiliser in the soil (N₂O)",
              "indirect_n2o_tco2e": "Nitrogen run-off (N₂O)", "organic_soil_tco2e": "Peat (organic) soils",
              "diesel_tco2e": "Tractor diesel", "lime_tco2e": "Lime", "pesticides_tco2e": "Pesticides",
              "electricity_tco2e": "Farm electricity"}


def _farms(year: int) -> pd.DataFrame:
    f = _t("gold_farm_footprints")
    return f[f["year"] == year]


def farm_components(year: int) -> dict:
    f = _farms(year)
    total = float(f["tco2e"].sum())
    rows = sorted(({"label": v, "value": round(float(f[k].sum())), "pct": _pct(float(f[k].sum()), total)}
                   for k, v in COMPONENTS.items()), key=lambda r: -r["value"])
    return _out("farm_components", f"{rows[0]['label']} is the biggest part of contract-farm emissions in {year}",
                "hbar", rows, ["farms"], year)


def crop_intensity(year: int) -> dict:
    f = _farms(year).groupby("crop")[["tco2e", "delivered_kg"]].sum()
    rows = sorted(({"label": c.replace("_", " ").capitalize(), "value": round(1000 * r.tco2e / r.delivered_kg, 2)}
                   for c, r in f.iterrows() if r.delivered_kg), key=lambda r: -r["value"])
    return _out("crop_intensity", f"{rows[0]['label']} has the highest footprint per kg delivered", "hbar", rows, ["farms"],
                year, unit="kg CO₂e per kg")


def farm_map(year: int) -> dict:
    p = _t("gold_dim_parcels").groupby("farm_id")[["lat", "lon"]].mean()
    f = _farms(year).groupby("farm_id").agg(tco2e=("tco2e", "sum"), org=("organic_ha", "sum"), area=("declared_area_ha", "sum"))
    f = f.join(p, how="inner")
    share = f["org"] / f["area"].where(f["area"] > 0)
    soil = pd.cut(share.fillna(0), [-1, 0, 0.3, 1.01], labels=["No peat soil", "Some peat soil", "Mostly peat soil"])
    rows = [{"farm": k, "lat": round(r.lat, 4), "lon": round(r.lon, 4), "value": round(r.tco2e, 1), "soil": str(s)}
            for (k, r), s in zip(f.iterrows(), soil)]
    peat = sum(r["value"] for r in rows if r["soil"] != "No peat soil")
    return _out("farm_map", f"Farms on peat soil cause {_pct(peat, sum(r['value'] for r in rows)):.0f} % of contract-farm emissions",
                "scatter_map", rows, ["farms", "parcels"], year, note="Each dot is a contract farm, sized by its emissions.")


# ---- 4. Can we trust the numbers? ----------------------------------------------------------------------------

def corrections(year: int) -> dict:
    raw, st = data.inventory(year)
    if st != "naive":
        return _out("corrections", "No uncleaned baseline to compare against", "waterfall", [], ["li"], year)
    raw = raw[(raw["scope"] != "scope2_location") & (raw["scope"] != "memo")]
    a, b = raw.groupby("category")["tco2e"].sum(), _li(year).groupby("category")["tco2e"].sum()
    delta = b.sub(a, fill_value=0).sort_values(key=abs, ascending=False)
    start, end = float(a.sum()), float(b.sum())
    draft = year == 2025
    rows = [{"label": "Draft report (uncleaned data)" if draft else "Uncleaned data", "value": round(start), "type": "total"}]
    rows += [{"label": PLAIN.get(k, k), "value": round(float(v)), "type": "delta"} for k, v in delta.head(5).items()]
    rows.append({"label": "Other fixes", "value": round(float(delta.iloc[5:].sum())), "type": "delta"})
    rows.append({"label": "Checked figure", "value": round(end), "type": "total"})
    return _out("corrections", f"Cleaning the data changed the {year} figure from {_big(start)} to {_big(end)} t CO₂e",
                "waterfall", rows, ["li", "issues"] + (["draft"] if draft else []), year,
                note="The draft 2025 report was calculated on uncleaned data; its figures match our uncleaned calculation exactly." if draft else None)


def issues_by_type(year: int) -> dict:
    i = _t(gold.GOLD["issues"])
    i = i[i["year"] == year]
    g = i.groupby(["issue_type", "action"]).size().reset_index(name="n")
    rows = [{"label": ISSUES.get(r.issue_type, r.issue_type), "outcome": ACTION.get(r.action, r.action), "value": int(r.n)}
            for r in g.sort_values("n", ascending=False).itertuples()]
    review = sum(r["value"] for r in rows if r["outcome"] == "Needs expert review")
    return _out("issues_by_type", f"{sum(r['value'] for r in rows)} data problems found in {year}; {review} need an expert",
                "hbar_stacked", rows, ["issues"], year, unit="findings", series=list(dict.fromkeys(ACTION.values())))


def published_vs_checked(year: int | None = None) -> dict:
    tr = trend()
    rows = [{"year": r["year"], "Checked": sum(r[k] for k in GROUPS.values()), "Previously published": r.get("Previously published")}
            for r in tr["rows"]]
    return _out("published_vs_checked", "Our checked figures vs what was published at the time", "grouped_bar", rows,
                ["li", "history"], None, series=["Checked", "Previously published"])


# ---- 5. Getting to target ------------------------------------------------------------------------------------

def target_path(year: int | None = None) -> dict:
    d = _li()
    d = d[d["scope"].isin(["scope1", "scope2_market"])].groupby("year")["tco2e"].sum()
    base = float(d.loc[BASE_YEAR])
    rows = [{"year": y, "Actual": round(float(d[y])) if y in d.index else None,
             "Target path": tools.sbti_target(base, SBTI_RATE, BASE_YEAR, y)["target_tco2e"]} for y in range(BASE_YEAR, 2031)]
    last = max(int(y) for y in d.index)
    gap = float(d[last]) - tools.sbti_target(base, SBTI_RATE, BASE_YEAR, last)["target_tco2e"]
    return _out("target_path", f"Own operations and energy are {'below' if gap <= 0 else 'above'} the 1.5 °C path in {last}",
                "line", rows, ["li"], None, series=["Actual", "Target path"],
                note=f"Target path: {BASE_YEAR} level reduced {SBTI_RATE} % of the base each year (SBTi 1.5 °C, own operations + purchased energy).")


def levers(year: int | None = None) -> dict:
    lv = _t("s3_decarbonisation_levers")
    lv = lv[(lv["abatement_tco2e_2030_design"] > 0) & lv["indicative_cost_eur_per_tco2e"].notna()]
    lv = lv.sort_values("indicative_cost_eur_per_tco2e")
    rows = [{"label": r.name, "value": int(r.abatement_tco2e_2030_design), "cost": float(r.indicative_cost_eur_per_tco2e),
             "start": int(r.earliest_start), "confidence": r.confidence} for r in lv.itertuples()]
    cheap = sum(r["value"] for r in rows if r["cost"] <= 0)
    return _out("levers", f"{len(rows)} reduction options; {cheap:,} t CO₂e/yr of them save money", "lever_bars", rows, ["levers"],
                None, unit="t CO₂e saved per year by 2030",
                note="Savings and costs are design estimates from the scenario pack, not yet recalculated from our inventory.")


def carbon_cost(year: int) -> dict:
    s1 = float(_li(year).query("scope == 'scope1'")["tco2e"].sum())
    sc = _t("s3_transition_scenarios")
    pick = {"net_zero_2050": "Net zero 2050", "delayed_transition": "Delayed transition", "current_policies": "Current policies"}
    sc = sc[sc["scenario"].isin(pick)]
    rows = [{"year": int(y), **{pick[k]: round(s1 * float(p) / 1e6, 2) for k, p in g.set_index("scenario")["carbon_price_eur_t"].items()}}
            for y, g in sc.groupby("year")]
    hi = max(rows[-1][v] for v in pick.values())
    return _out("carbon_cost", f"At today's own-operations emissions, carbon could cost up to €{hi:.1f} M a year by {rows[-1]['year']}",
                "line", rows, ["li", "scen"], year, unit="€ million per year", series=list(pick.values()),
                note=f"{year} own-operations emissions ({s1:,.0f} t CO₂e) × each scenario's carbon price. Scenario prices are illustrative.")


CHARTS = {f.__name__: f for f in (kpis, scope_split, trend, top_categories, top_materials, land_use, farm_components,
                                    crop_intensity, farm_map, corrections, issues_by_type, published_vs_checked,
                                    target_path, levers, carbon_cost)}
PAGES = {"overview": ["kpis", "scope_split", "trend"], "drivers": ["top_categories", "top_materials", "land_use"],
         "farms": ["farm_components", "crop_intensity", "farm_map"], "trust": ["corrections", "issues_by_type", "published_vs_checked"],
         "target": ["target_path", "levers", "carbon_cost"]}


def chart(chart_id: str, year: int = 2025) -> dict:
    if chart_id not in CHARTS:
        return {"error": f"unknown chart_id {chart_id!r}; use one of {', '.join(CHARTS)}"}
    if not gold.has("line_items"):
        return {"error": "the data pipeline has not run yet, so dashboard charts are unavailable"}
    return CHARTS[chart_id](int(year))


def dashboard(year: int = 2025) -> dict:
    return {"year": year, "pages": PAGES, "charts": {k: chart(k, year) for k in CHARTS}}
