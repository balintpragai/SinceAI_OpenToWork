"""Gold emission line items (ADR 0001): one row per source record x emission factor.

The method mirrors `ccn_tools.reference_calculator.compute_inventory` (docs/METHODOLOGY.md §3-§5)
line by line, but keeps every record. Three steps are not simple activity x factor and are
allocated back to records proportionally (`allocation` column):
  - market-based electricity: the site's GoO cover min(MWh, GoO) is shared pro rata over meter months;
  - commuting: site total = survey mean x headcount, shared equally over respondents' annual km-kg;
  - contract farming: farm emissions shared over the farm's deliveries by delivered kg.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .farm import COMPONENTS, FLAG_COMPONENTS
from .refdata import F, NCV_PER_UNIT

METHOD_SOURCE = "ccn_tools.factors / docs/METHODOLOGY.md"
HEAT = ["steam", "district_heat"]


class _Out:
    def __init__(self, efl: pd.DataFrame):
        self.rows: list[pd.DataFrame] = []
        self.efl = efl.set_index("ef_id")
        self._meta: dict[str, dict] = {}

    def ef(self, ef_id: str) -> float:
        return float(self.efl.loc[ef_id, "kgco2e_per_unit"])

    def ef_meta(self, ef_id: str) -> dict:
        if ef_id not in self._meta:
            r = self.efl.loc[ef_id]
            self._meta[ef_id] = dict(factor_id=ef_id, factor_source=f"{r.reference_source} ({r.value_status}, v{r.version})")
        return self._meta[ef_id]

    def add(self, df: pd.DataFrame, *, year, scope, category, line_item, tco2e, activity_value, activity_unit,
            factor_id, factor_value, factor_unit, factor_source, basis, component=None, flag_tco2e=0.0,
            biogenic_co2_t=0.0, allocation="direct", source_table=None):
        if len(df) == 0:
            return
        n = len(df)

        def col(v):
            return v.values if isinstance(v, pd.Series) else np.full(n, v, dtype=object if isinstance(v, str) or v is None else float)
        self.rows.append(pd.DataFrame(dict(
            record_key=df.record_key.values, source_table=source_table, year=col(year), scope=scope, category=category,
            line_item=col(line_item), component=col(component) if component is not None else None,
            activity_value=col(activity_value).astype(float), activity_unit=activity_unit,
            factor_id=col(factor_id), factor_value=col(factor_value).astype(float), factor_unit=factor_unit,
            factor_source=col(factor_source), basis=basis, allocation=allocation,
            tco2e=col(tco2e).astype(float), flag_tco2e=col(flag_tco2e).astype(float),
            biogenic_co2_t=col(biogenic_co2_t).astype(float),
            is_estimate=df.is_estimate.values.astype(bool) if "is_estimate" in df else False,
            flagged=df.has_flag.values.astype(bool) if "has_flag" in df else False)))


def emission_line_items(T: dict[str, pd.DataFrame], s3: dict[str, pd.DataFrame], years: list[int]) -> pd.DataFrame:
    o = _Out(T["ef_library"])
    country = T["sites"].set_index("site_id").country.to_dict()
    flag_share = T["ef_library"].set_index("ef_id").flag_share.to_dict()
    mm = T["materials"].set_index("material_id")
    svc = set(mm[mm.material_group == "service"].index)
    cap = set(mm[mm.material_group == "capex"].index)
    for y in years:
        en = T["energy"][T["energy"].year == y]
        meter_fuels = en[(en.month > 0) & ~en.carrier.isin(["electricity"] + HEAT)]
        # --- Scope 1 combustion: metered fuels + fuel deliveries - stock change (record level)
        fd = s3["fuel_deliveries"]
        fd = fd[(fd.year == y) & ~fd.is_excluded.astype(bool)].copy()
        fd["mwh"] = fd.quantity * [NCV_PER_UNIT[(c, u)] for c, u in zip(fd.carrier, fd.unit)]
        st = s3["fuel_stock_changes"]
        st = st[(st.year == y) & st.set_index(["site_id", "carrier"]).index.isin(
            fd.set_index(["site_id", "carrier"]).index)].copy()
        st["mwh"] = -st.stock_change * [NCV_PER_UNIT[(c, u)] for c, u in zip(st.carrier, st.unit)]
        st["is_estimate"], st["has_flag"] = False, False
        for src, tbl in ((meter_fuels, "energy_meter_readings"), (fd, "fuel_deliveries"), (st, "fuel_stock_changes")):
            if len(src) == 0:
                continue
            ef = src.carrier.map(F.FUEL_EF_T_PER_MWH).astype(float)
            bio = src.carrier.map(F.FUEL_BIOGENIC_T_PER_MWH).fillna(0.0).astype(float)
            o.add(src, year=y, scope="scope1", category="stationary_and_mobile_combustion",
                  line_item=src.site_id + ":" + src.carrier, tco2e=src.mwh * ef, activity_value=src.mwh,
                  activity_unit="MWh", factor_id="fossil_co2:" + src.carrier, factor_value=ef, factor_unit="t/MWh",
                  factor_source=METHOD_SOURCE + " §3", basis="fuel MWh x fossil EF", biogenic_co2_t=src.mwh * bio,
                  source_table=tbl)
            # --- cat 3 well-to-tank
            wtt = src.carrier.map(F.FUEL_WTT)
            efw = wtt.map(lambda e: o.ef(e)).astype(float)
            o.add(src, year=y, scope="scope3", category="cat03_fuel_energy", line_item="wtt:" + src.carrier,
                  tco2e=src.mwh * efw / 1000, activity_value=src.mwh, activity_unit="MWh", factor_id=wtt,
                  factor_value=efw, factor_unit="kg/MWh", factor_source=wtt.map(lambda e: o.ef_meta(e)["factor_source"]),
                  basis="fuel MWh x WTT", source_table=tbl)
        # --- refrigerants
        rf = T["refrigerants"][T["refrigerants"].year == y]
        gwp = rf.refrigerant.map(F.REFRIGERANT_GWP).astype(float)
        o.add(rf, year=y, scope="scope1", category="fugitive_refrigerants", line_item=rf.site_id + ":" + rf.refrigerant,
              tco2e=rf.kg_added * gwp / 1000, activity_value=rf.kg_added, activity_unit="kg", factor_id="gwp100:" + rf.refrigerant,
              factor_value=gwp, factor_unit="kgCO2e/kg", factor_source="IPCC AR6 GWP100 (METHODOLOGY.md §3)",
              basis="kg top-up x GWP100", source_table="refrigerant_service_log")
        # --- electricity (Scope 2 + cat 3 upstream)
        el = en[en.carrier == "electricity"].copy()
        g0 = T["goo"]
        goo = g0[(g0.year == y) & (g0.vintage_year == y)].groupby("site_id").mwh_cancelled.sum()
        site_mwh = el.groupby("site_id").mwh.transform("sum")
        covered = np.minimum(site_mwh, el.site_id.map(goo).fillna(0.0))
        c = el.site_id.map(country).fillna("FI")
        lb = np.where(c == "FI", F.GRID_FI_LB[y], F.GRID_SE_LB[y])
        res = np.where(c == "FI", F.RESIDUAL_FI[y], F.RESIDUAL_SE[y])
        o.add(el, year=y, scope="scope2_location", category="purchased_electricity", line_item=el.site_id,
              tco2e=el.mwh * lb, activity_value=el.mwh, activity_unit="MWh", factor_id="grid_lb:" + c, factor_value=lb,
              factor_unit="t/MWh", factor_source=METHOD_SOURCE + " §3", basis="MWh x grid average",
              source_table="energy_meter_readings")
        uncovered = el.mwh * (1 - covered / site_mwh.where(site_mwh != 0))
        o.add(el, year=y, scope="scope2_market", category="purchased_electricity", line_item=el.site_id,
              tco2e=uncovered.fillna(0.0) * res, activity_value=uncovered.fillna(0.0), activity_unit="MWh (not GoO-covered)",
              factor_id="residual_mix:" + c, factor_value=res, factor_unit="t/MWh", factor_source="AIB residual mix (METHODOLOGY.md §3)",
              basis="uncovered MWh x residual mix", allocation="goo_cover_pro_rata", source_table="energy_meter_readings")
        up = "EF-ELEC-UPSTREAM-" + c
        efu = up.map(o.ef).astype(float)
        o.add(el, year=y, scope="scope3", category="cat03_fuel_energy", line_item="elec_upstream:" + el.site_id,
              tco2e=el.mwh * efu / 1000, activity_value=el.mwh, activity_unit="MWh", factor_id=up, factor_value=efu,
              factor_unit="kg/MWh", factor_source=up.map(lambda e: o.ef_meta(e)["factor_source"]), basis="MWh x upstream+T&D",
              source_table="energy_meter_readings")
        # --- purchased heat / steam
        ht = en[en.carrier.isin(HEAT)].copy()
        hef = T["heat_suppliers"]
        hef = hef[hef.year == y].groupby("site_id").t_per_mwh.first()
        mb = ht.site_id.map(hef).fillna(0.0).astype(float)
        o.add(ht, year=y, scope="scope2_location", category="purchased_heat_steam", line_item=ht.site_id,
              tco2e=ht.mwh * F.HEAT_LB_EF[y], activity_value=ht.mwh, activity_unit="MWh", factor_id="heat_lb:FI",
              factor_value=F.HEAT_LB_EF[y], factor_unit="t/MWh", factor_source=METHOD_SOURCE + " §3",
              basis="MWh x national heat average", source_table="energy_meter_readings")
        o.add(ht, year=y, scope="scope2_market", category="purchased_heat_steam", line_item=ht.site_id,
              tco2e=ht.mwh * mb, activity_value=ht.mwh, activity_unit="MWh", factor_id="heat_supplier:" + ht.site_id,
              factor_value=mb, factor_unit="t/MWh", factor_source="heat_supplier_factors.csv",
              basis="MWh x supplier-specific EF", source_table="energy_meter_readings")
        ehu = o.ef("EF-HEAT-UPSTREAM")
        o.add(ht, year=y, scope="scope3", category="cat03_fuel_energy", line_item="heat_upstream", tco2e=ht.mwh * ehu / 1000,
              activity_value=ht.mwh, activity_unit="MWh", factor_id="EF-HEAT-UPSTREAM", factor_value=ehu, factor_unit="kg/MWh",
              factor_source=o.ef_meta("EF-HEAT-UPSTREAM")["factor_source"], basis="MWh x upstream",
              source_table="energy_meter_readings")
        # --- cat 1 purchased goods (supplier PCF > material default), services, cat 2 capex
        pur = T["purchases"][T["purchases"].year == y]
        goods = pur[~pur.material_id.isin(svc | cap)]
        goods = goods[goods.material_id.map(mm.default_ef_id) != "FARM"].copy()
        pcf = T["pcf_used"][T["pcf_used"].year == y].set_index(["supplier_id", "material_id"]).kgco2e_per_kg
        pcf_key = T["pcf_used"][T["pcf_used"].year == y].set_index(["supplier_id", "material_id"]).record_key
        idx = list(zip(goods.supplier_id, goods.material_id))
        has_pcf = np.array([i in pcf.index for i in idx], dtype=bool)
        dflt = goods.material_id.map(mm.default_ef_id)
        efv = np.where(has_pcf, [pcf.get(i, np.nan) for i in idx], dflt.map(o.ef)).astype(float)
        fid = np.where(has_pcf, [pcf_key.get(i, None) for i in idx], dflt)
        fsrc = np.where(has_pcf, "supplier PCF (PACT v2)", dflt.map(lambda e: o.ef_meta(e)["factor_source"]))
        t = goods.qty_kg * efv / 1000
        o.add(goods, year=y, scope="scope3", category="cat01_purchased_goods", line_item=goods.material_id + ":" + goods.supplier_id,
              tco2e=t, activity_value=goods.qty_kg, activity_unit="kg", factor_id=pd.Series(fid, index=goods.index),
              factor_value=pd.Series(efv, index=goods.index), factor_unit="kgCO2e/kg",
              factor_source=pd.Series(fsrc, index=goods.index),
              basis="kg x supplier PCF or material default factor", flag_tco2e=t * pd.to_numeric(dflt.map(flag_share), errors="coerce").fillna(0.0),
              source_table="erp_purchase_lines")
        for mats, cat, basis in ((svc, "cat01_purchased_services", "spend x EEIO"), (cap, "cat02_capital_goods", "capex spend x EEIO")):
            sp = pur[pur.material_id.isin(mats)]
            efid = sp.material_id.map(mm.default_ef_id)
            efs = efid.map(o.ef).astype(float)
            o.add(sp, year=y, scope="scope3", category=cat, line_item=sp.material_id, tco2e=sp.amount_eur * efs / 1000,
                  activity_value=sp.amount_eur, activity_unit="EUR", factor_id=efid, factor_value=efs, factor_unit="kgCO2e/EUR",
                  factor_source=efid.map(lambda e: o.ef_meta(e)["factor_source"]), basis=basis, source_table="erp_purchase_lines")
        # --- contract farming: farm emissions shared over deliveries by kg
        ff = T["farm_footprints"][T["farm_footprints"].year == y]
        farm_mat = pur[pur.material_id.map(mm.default_ef_id) == "FARM"].copy()
        from .refdata import FARM_CROP_BY_MATERIAL
        farm_mat["crop"] = farm_mat.material_id.map(FARM_CROP_BY_MATERIAL)
        farm_mat = farm_mat.merge(ff[["farm_id", "crop", "delivered_kg", "region", "record_key", "is_estimate"]
                                     + [f"{c}_tco2e" for c in COMPONENTS]].rename(
            columns={"record_key": "footprint_key", "is_estimate": "fp_estimate"}),
            left_on=["supplier_id", "crop"], right_on=["farm_id", "crop"], how="inner")
        w = farm_mat.qty_kg / farm_mat.delivered_kg
        farm_mat["is_estimate"] = farm_mat.is_estimate.astype(bool) | farm_mat.fp_estimate.astype(bool)
        for comp in COMPONENTS:
            tt = farm_mat[f"{comp}_tco2e"] * w
            o.add(farm_mat, year=y, scope="scope3", category="cat01_purchased_goods",
                  line_item="contract_farming:" + farm_mat.region + ":" + farm_mat.crop, component=comp, tco2e=tt,
                  activity_value=farm_mat.qty_kg, activity_unit="kg delivered", factor_id=farm_mat.footprint_key,
                  factor_value=farm_mat[f"{comp}_tco2e"] * 1e6 / farm_mat.delivered_kg, factor_unit="gCO2e/kg (component)",
                  factor_source="farm footprint (METHODOLOGY.md §5, ADR 0003)", basis="farm-specific footprint x delivered kg",
                  flag_tco2e=tt if comp in FLAG_COMPONENTS else 0.0, allocation="farm_total_by_delivered_kg",
                  source_table="erp_purchase_lines")
        # --- transport (cat 4 inbound, cat 9 outbound) and warehousing
        sh = T["shipments"][T["shipments"].year == y]
        efs = sh.ef_id.map(o.ef).astype(float)
        cat = np.where(sh.direction == "inbound", "cat04_upstream_transport", "cat09_downstream_transport")
        for cname in ("cat04_upstream_transport", "cat09_downstream_transport"):
            m = cat == cname
            s = sh[m]
            o.add(s, year=y, scope="scope3", category=cname, line_item=s.direction + ":" + s.ef_id,
                  tco2e=s.tkm * efs[m] / 1000, activity_value=s.tkm, activity_unit="tkm", factor_id=s.ef_id,
                  factor_value=efs[m], factor_unit="kgCO2e/tkm", factor_source=s.ef_id.map(lambda e: o.ef_meta(e)["factor_source"]),
                  basis="tkm x WTW EF", source_table="shipments")
        wh = T["warehousing"][T["warehousing"].year == y]
        epd = o.ef("EF-PALLETDAY-FROZEN")
        o.add(wh, year=y, scope="scope3", category="cat09_downstream_transport", line_item="frozen_warehousing",
              tco2e=wh.pallet_days * epd / 1000, activity_value=wh.pallet_days, activity_unit="pallet-days",
              factor_id="EF-PALLETDAY-FROZEN", factor_value=epd, factor_unit="kgCO2e/pallet-day",
              factor_source=o.ef_meta("EF-PALLETDAY-FROZEN")["factor_source"], basis="pallet-days x EF",
              source_table="frozen_warehousing")
        # --- waste
        ws = T["waste"][T["waste"].year == y]
        efw = ws.ef_id.map(o.ef).astype(float)
        o.add(ws, year=y, scope="scope3", category="cat05_waste", line_item=ws.site_id + ":" + ws.waste_stream,
              tco2e=ws.t * efw / 1000, activity_value=ws.t, activity_unit="t", factor_id=ws.ef_id, factor_value=efw,
              factor_unit="kgCO2e/t", factor_source=ws.ef_id.map(lambda e: o.ef_meta(e)["factor_source"]),
              basis="t x treatment EF", source_table="waste_transfer_notes")
        ww = T["wastewater"][T["wastewater"].year == y]
        eww = o.ef("EF-WASTEWATER-MUNI")
        o.add(ww, year=y, scope="scope3", category="cat05_waste", line_item="wastewater_third_party", tco2e=ww.m3 * eww / 1000,
              activity_value=ww.m3, activity_unit="m3", factor_id="EF-WASTEWATER-MUNI", factor_value=eww, factor_unit="kgCO2e/m3",
              factor_source=o.ef_meta("EF-WASTEWATER-MUNI")["factor_source"], basis="m3 x EF", source_table="wastewater_third_party")
        # --- business travel
        tr = T["travel"][T["travel"].year == y]
        for mode, item, efid in (("flight", "flights", "EF-PKM-FLIGHT-SHORT"), ("train", "rail", "EF-PKM-TRAIN")):
            s = tr[tr["mode"] == mode]
            e = o.ef(efid)
            o.add(s, year=y, scope="scope3", category="cat06_business_travel", line_item=item, tco2e=s.pkm * e / 1000,
                  activity_value=s.pkm, activity_unit="pkm", factor_id=efid, factor_value=e, factor_unit="kgCO2e/pkm",
                  factor_source=o.ef_meta(efid)["factor_source"], basis="pkm x EF", source_table="travel_bookings")
        eh = o.ef("EF-HOTEL-NIGHT")
        o.add(tr, year=y, scope="scope3", category="cat06_business_travel", line_item="hotels", tco2e=tr.nights * eh / 1000,
              activity_value=tr.nights, activity_unit="nights", factor_id="EF-HOTEL-NIGHT", factor_value=eh,
              factor_unit="kgCO2e/night", factor_source=o.ef_meta("EF-HOTEL-NIGHT")["factor_source"], basis="nights x EF",
              source_table="travel_bookings")
        # --- commuting: survey mean x headcount, shared equally over respondents
        cs = T["commuting_survey"].copy()
        hc = T["headcount"][T["headcount"].year == y].set_index("site_id").headcount
        car = o.ef("EF-PKM-CAR")
        mode_ef = {"car": car, "carpool": car / 2, "bus": o.ef("EF-PKM-BUS"), "train": o.ef("EF-PKM-TRAIN"),
                   "bike_walk": 0.0, "ev_car": 0.03}
        cs["kg_year"] = cs.one_way_km * 2 * cs.days_on_site_per_week * 46 * cs["mode"].map(mode_ef).fillna(car)
        n = cs.groupby("site_id").record_key.transform("size")
        scale = cs.site_id.map(hc).fillna(0) / n
        o.add(cs, year=y, scope="scope3", category="cat07_employee_commuting", line_item=cs.site_id,
              tco2e=cs.kg_year * scale / 1000, activity_value=cs.one_way_km * 2 * cs.days_on_site_per_week * 46,
              activity_unit="km/yr (respondent)", factor_id="commute_mode:" + cs["mode"],
              factor_value=cs["mode"].map(mode_ef).fillna(car), factor_unit="kgCO2e/pkm",
              factor_source="EF-PKM-* factors; survey mean x site headcount", basis="survey mean x headcount",
              allocation="site_total_equal_per_respondent", source_table="commuting_survey")
        # --- sold products: use phase (cat 11) and end of life (cat 12)
        sa = T["sales"][T["sales"].year == y]
        kwh = sa.t_sold * 1000 * sa.product_group.map(F.USE_PHASE_KWH_PER_KG)
        grid = sa.market.map(lambda m: F.MARKET_GRID[m][y]).astype(float)
        s11 = sa[kwh > 0]
        o.add(s11, year=y, scope="scope3", category="cat11_use_of_sold_products", line_item=s11.product_group + ":" + s11.market,
              tco2e=(kwh * grid / 1000)[kwh > 0], activity_value=kwh[kwh > 0], activity_unit="kWh", factor_id="market_grid:" + s11.market,
              factor_value=grid[kwh > 0], factor_unit="kgCO2e/kWh", factor_source=METHOD_SOURCE + " §4 cat 11",
              basis="kWh x market grid", source_table="sales_volumes")
        pl = sa.product_group.map(lambda g: F.PACK_KG_PER_T[g][0])
        bd = sa.product_group.map(lambda g: F.PACK_KG_PER_T[g][1])
        eol = sa.t_sold * pl / 1000 * F.EOL_PLASTIC_EF_T + sa.t_sold * bd / 1000 * F.EOL_BOARD_EF_T
        o.add(sa, year=y, scope="scope3", category="cat12_end_of_life", line_item=sa.product_group + ":" + sa.market,
              tco2e=eol, activity_value=sa.t_sold, activity_unit="t sold", factor_id="packaging_eol:" + sa.product_group,
              factor_value=eol / sa.t_sold.where(sa.t_sold != 0), factor_unit="tCO2e/t sold", factor_source=METHOD_SOURCE + " §4 cat 12",
              basis="packaging t x EoL EF", source_table="sales_volumes")
    eli = pd.concat(o.rows, ignore_index=True)
    eli.insert(0, "eli_key", [f"eli:{y}:{i:07d}" for i, y in enumerate(eli.year.astype(int))])
    return eli


def summarise(eli: pd.DataFrame, year: int) -> pd.DataFrame:
    """A2 summary in the template's categories, with the flagged share and the estimated share per line."""
    e = eli[eli.year == year].copy()
    e.loc[e.category.isin(["cat01_purchased_goods", "cat01_purchased_services"]), "category"] = "cat01_purchased_goods_services"
    e["t_flag"] = np.where(e.flagged, e.tco2e, 0.0)
    e["t_est"] = np.where(e.is_estimate, e.tco2e, 0.0)
    rows = e.groupby(["scope", "category"]).agg(tco2e=("tco2e", "sum"), flagged_tco2e=("t_flag", "sum"),
                                                 estimated_tco2e=("t_est", "sum"), flag_tco2e=("flag_tco2e", "sum"),
                                                 n_line_items=("eli_key", "size")).reset_index()
    tot = []
    for scope, cat in (("scope1", "scope1_total"), ("scope2_location", "scope2_location_total"),
                       ("scope2_market", "scope2_market_total"), ("scope3", "scope3_total")):
        s = e[e.scope == scope]
        tot.append(dict(scope="total", category=cat, tco2e=s.tco2e.sum(), flagged_tco2e=s.t_flag.sum(),
                        estimated_tco2e=s.t_est.sum(), flag_tco2e=s.flag_tco2e.sum(), n_line_items=len(s)))
    s1 = e[e.scope == "scope1"]
    tot.append(dict(scope="memo", category="biogenic_co2_scope1", tco2e=s1.biogenic_co2_t.sum(), flagged_tco2e=0.0,
                    estimated_tco2e=0.0, flag_tco2e=0.0, n_line_items=int((s1.biogenic_co2_t != 0).sum())))
    out = pd.concat([rows, pd.DataFrame(tot)], ignore_index=True)
    out.insert(0, "year", year)
    out["flagged_share"] = out.flagged_tco2e / out.tco2e.where(out.tco2e != 0)
    return out
