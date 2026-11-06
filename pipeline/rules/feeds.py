"""Rules for 02_raw_feeds. Signatures follow the planted issue types listed in
docs/TASKS_AND_SCORING.md (A1) and observed in the public 2023-2024 dev labels."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..refdata import COMMUTE_MODES, FX_PER_EUR
from .base import Context, make_issue, ratio_to_power_of_ten, rule, thousand_factor

# ----------------------------------------------------------------------------------------------- ERP


def _supplier_currency(erp: pd.DataFrame) -> pd.Series:
    """Modal invoicing currency per supplier, when one non-EUR currency clearly dominates."""
    out = {}
    for sup, g in erp.groupby("supplier_id"):
        vc = g.currency.value_counts(normalize=True)
        if vc.index[0] != "EUR" and vc.iloc[0] >= 0.7:
            out[sup] = vc.index[0]
    return pd.Series(out, dtype="object")


def _erp_with_price(ctx: Context) -> pd.DataFrame:
    erp = ctx.t("erp_purchase_lines").copy()
    cur = _supplier_currency(erp)
    erp["currency_fixed"] = erp.supplier_id.map(cur).astype(object).where(erp.currency == "EUR").fillna(erp.currency.astype(object))
    erp["amount_eur_fixed"] = erp.net_amount / erp.currency_fixed.map(FX_PER_EUR).astype(float)
    goods = (erp.uom.isin(["KG", "TO"])) & (erp.qty_kg > 0) & (erp.movement_type == 101)
    erp["unit_price"] = np.where(goods, erp.amount_eur_fixed / erp.qty_kg.where(erp.qty_kg > 0), np.nan)
    med = erp[goods].groupby("material_id").unit_price.median()
    erp["price_ratio"] = erp.unit_price / erp.material_id.map(med)
    return erp


@rule("ERP-CUR-01", "erp_purchase_lines", "currency_error", "correct",
      "EUR line from a supplier that invoices >= 70 % of its lines in one other currency; that currency is restored.")
def erp_currency(ctx: Context):
    erp = _erp_with_price(ctx)
    bad = erp[erp.currency != erp.currency_fixed]
    return [make_issue(erp_currency.rule, r.record_key, r.year, 0.9,
                       f"supplier {r.supplier_id} invoices in {r.currency_fixed}; line booked as EUR",
                       fld="currency", observed=r.currency, proposed=r.currency_fixed,
                       changes={"currency": r.currency_fixed, "amount_eur": r.amount_eur_fixed})
            for r in bad.itertuples()]


@rule("ERP-CUR-02", "erp_purchase_lines", "currency_error", "correct",
      "Spend line (uom EUR) 7.5-25x the material's median amount, i.e. ~11.4x: a SEK amount booked as EUR; "
      "net_amount / 11.4 (FX from ccn_tools.factors).")
def erp_currency_spend(ctx: Context):
    erp = ctx.t("erp_purchase_lines")
    sp = erp[(erp.uom == "EUR") & (erp.currency == "EUR") & (erp.net_amount > 0)].copy()
    sp["r"] = sp.net_amount / sp.groupby("material_id").net_amount.transform("median")
    out = []
    for r in sp[(sp.r >= 7.5) & (sp.r <= 25)].itertuples():
        v = r.net_amount / FX_PER_EUR["SEK"]
        out.append(make_issue(erp_currency_spend.rule, r.record_key, r.year, 0.75,
                              f"amount {r.net_amount:,.0f} is {r.r:.1f}x the material median (SEK/EUR = {FX_PER_EUR['SEK']})",
                              fld="net_amount", observed=r.net_amount, proposed=round(v, 2),
                              changes={"net_amount": v, "amount_eur": v}))
    return out


def _price_shift_issues(ctx: Context, the_rule, want: set[int], conf: float, note: str):
    erp = _erp_with_price(ctx)
    out = []
    for r in erp[erp.uom == "KG"].itertuples():
        k = 3 if thousand_factor(r.price_ratio) == 3 else ratio_to_power_of_ten(r.price_ratio)
        if k in want:
            q = r.quantity * 10 ** k
            out.append(make_issue(the_rule, r.record_key, r.year, conf,
                                  f"unit price {r.unit_price:.4g} EUR/kg is {r.price_ratio:.3g}x the material median; {note}",
                                  fld="quantity", observed=r.quantity, proposed=round(q, 6),
                                  changes={"quantity": q, "qty_kg": q}))
    return out


@rule("ERP-UNIT-01", "erp_purchase_lines", "unit_error", "correct",
      "Unit price ~1000x the material median on a KG line: quantity was keyed in tonnes; quantity x 1000.")
def erp_unit(ctx: Context):
    return _price_shift_issues(ctx, erp_unit.rule, {3}, 0.9, "tonnes keyed with uom KG")


@rule("ERP-DEC-01", "erp_purchase_lines", "decimal_shift", "correct",
      "Unit price ~10x or ~0.1x the material median: decimal point shifted by one place; quantity rescaled.")
def erp_decimal(ctx: Context):
    return _price_shift_issues(ctx, erp_decimal.rule, {1, -1}, 0.8, "quantity decimal shifted")


@rule("ERP-DUP-01", "erp_purchase_lines", "duplicate_record", "correct",
      "Same supplier, material, quantity, amount and movement as an earlier line posted <= 10 days before; later line dropped.")
def erp_duplicate(ctx: Context):
    erp = ctx.t("erp_purchase_lines").copy()
    erp["file_order"] = np.arange(len(erp))
    erp["post_dt"] = pd.to_datetime(erp.posting_date)
    erp = erp.sort_values(["post_dt", "file_order"])
    out = []
    for _, g in erp.groupby(["supplier_id", "material_id", "quantity", "net_amount", "currency", "movement_type"], sort=False):
        if len(g) < 2:
            continue
        prev = None
        for r in g.itertuples():
            if prev is not None and (r.post_dt - prev.post_dt).days <= 10 and r.doc_no != prev.doc_no:
                out.append(make_issue(erp_duplicate.rule, r.record_key, r.year, 0.95,
                                      f"duplicate of {prev.record_key} posted {prev.posting_date}", drop=True))
            else:
                prev = r
    return out


@rule("ERP-MAT-01", "erp_purchase_lines", "material_mismatch", "correct",
      "material_text is the ERP name of a different material than material_id; material_id taken from the text.")
def erp_material(ctx: Context):
    erp = ctx.t("erp_purchase_lines")
    mm = ctx.t("materials")
    by_name = mm.groupby("erp_name").material_id.agg(lambda s: s.iloc[0] if len(s) == 1 else None).dropna()
    name_of = mm.set_index("material_id").erp_name
    out = []
    for r in erp.itertuples():
        txt_mat = by_name.get(r.material_text)
        if txt_mat and txt_mat != r.material_id and name_of.get(r.material_id) != r.material_text:
            out.append(make_issue(erp_material.rule, r.record_key, r.year, 0.85,
                                  f"text '{r.material_text}' is the ERP name of {txt_mat}",
                                  fld="material_id", observed=r.material_id, proposed=txt_mat,
                                  changes={"material_id": txt_mat}))
    return out


# --------------------------------------------------------------------------------------------- energy


def _energy_analysis(ctx: Context) -> dict:
    cache = ctx.tables.get("__energy_analysis")
    if cache is not None:
        return cache
    e = ctx.t("energy_meter_readings").copy()
    e["in_boundary"] = [ctx.boundary.contains(s, y, m) for s, y, m in zip(e.site_id, e.year, e.month)]
    e = e[e.in_boundary]
    unit, spikes, missing = [], [], []
    for (site, carrier), g in e.groupby(["site_id", "carrier"]):
        g = g.sort_values(["year", "month"]).copy()
        pos = g.mwh[g.mwh > 0]
        if len(pos) < 6:
            continue
        med = pos.median()
        g["v"] = g.mwh
        for r in g.itertuples():
            if thousand_factor(r.mwh / med) == 3:
                unit.append((r, r.mwh / 1000))
                g.loc[r.Index, "v"] = r.mwh / 1000
        # seasonal profile from complete years
        piv = g.pivot_table(index="year", columns="month", values="v", aggfunc="sum")
        complete = piv.dropna()
        complete = complete[complete.sum(axis=1) > 0]
        shares = complete.div(complete.sum(axis=1), axis=0).median() if len(complete) else None
        if shares is not None:
            shares = shares / shares.sum()
        spiked = set()

        def expected(year, month, exclude):
            row = piv.loc[year] if year in piv.index else pd.Series(dtype=float)
            avail = row.dropna()
            avail = avail[[m for m in avail.index if m != month and (year, m) not in exclude]]
            if shares is not None and len(avail) >= 3:
                return float(avail.sum() / shares[avail.index].sum() * shares[month]), "seasonal_profile"
            # fallback: neighbouring months in the series
            s = g[(g.year * 12 + g.month) != year * 12 + month].copy()
            s["d"] = (s.year * 12 + s.month - (year * 12 + month)).abs()
            nb = s.nsmallest(2, "d").v
            return (float(nb.mean()), "neighbour_mean") if len(nb) else (None, None)

        if shares is not None:
            for r in g.itertuples():
                exp, _ = expected(r.year, r.month, set())
                if exp and exp > 0 and r.v / exp > 2.2 and thousand_factor(r.v / exp) != 3:
                    spiked.add((r.year, r.month))
            for r in g.itertuples():
                if (r.year, r.month) in spiked:
                    exp, method = expected(r.year, r.month, spiked)
                    spikes.append((r, r.v, exp, method))
        # missing months inside the series span (extended to Dec of the last data year)
        first = pd.Period(f"{g.year.iloc[0]}-{g.month.iloc[0]:02d}", "M")
        last = pd.Period(f"{g.year.iloc[-1]}-{g.month.iloc[-1]:02d}", "M")
        if last.year == int(e.year.max()):
            last = pd.Period(f"{last.year}-12", "M")
        have = {(int(y), int(m)) for y, m in zip(g.year, g.month)}
        for p in pd.period_range(first, last, freq="M"):
            if (p.year, p.month) not in have and ctx.boundary.contains(site, p.year, p.month):
                exp, method = expected(p.year, p.month, spiked)
                missing.append((site, carrier, p.year, p.month, exp, method))
    res = dict(unit=unit, spikes=spikes, missing=missing)
    ctx.tables["__energy_analysis"] = res
    return res


@rule("EN-UNIT-01", "energy_meter_readings", "unit_error", "correct",
      "Reading ~1000x the series median: kWh reported in the MWh column; value / 1000.")
def energy_unit(ctx: Context):
    return [make_issue(energy_unit.rule, r.record_key, r.year, 0.95, "kWh reported in MWh column",
                       fld="value", observed=r.mwh, proposed=round(v, 6), changes={"value": v, "mwh": v})
            for r, v in _energy_analysis(ctx)["unit"]]


@rule("EN-SPIKE-01", "energy_meter_readings", "meter_spike", "estimate",
      "Reading > 2.2x the site's own seasonal expectation for that month (seasonal peaks are in the profile and "
      "do not trigger); replaced by the seasonal-profile estimate.")
def energy_spike(ctx: Context):
    out = []
    for r, v, exp, method in _energy_analysis(ctx)["spikes"]:
        if exp is None:
            continue
        out.append(make_issue(energy_spike.rule, r.record_key, r.year, 0.8,
                              f"{v:.4g} MWh vs {exp:.4g} expected ({method})", fld="value", observed=v,
                              proposed=round(exp, 3), changes={"value": exp, "mwh": exp, "estimate_method": method}))
    return out


@rule("EN-MISS-01", "energy_meter_readings", "missing_record", "estimate",
      "Month missing inside a meter series (inside the organisational boundary); estimated with the seasonal "
      "profile: (sum of the year's available months / their profile share) x the month's share. Fallback: mean "
      "of the two nearest months (lower confidence).")
def energy_missing(ctx: Context):
    out = []
    for site, carrier, y, m, exp, method in _energy_analysis(ctx)["missing"]:
        key = f"energy:{site}:{y}-{m:02d}:{carrier}"
        conf = 0.9 if method == "seasonal_profile" else 0.6
        row = dict(record_key=key, site_id=site, year=y, month=m, carrier=carrier, value=exp, unit="MWh", mwh=exp,
                   period=f"{y}-{m:02d}", estimate_method=method)
        out.append(make_issue(energy_missing.rule, key, y, conf, f"no reading for {y}-{m:02d}; estimate {exp} ({method})",
                              fld="value", proposed=None if exp is None else round(exp, 3), new_row=row))
    return out


# ---------------------------------------------------------------------------------------------- fuels


@rule("FUEL-UNIT-01", "fuel_deliveries", "unit_error", "correct",
      "Delivery ~1/1000 of the site-carrier median: m3 keyed as litres (or kg as t); quantity x 1000.")
def fuel_unit(ctx: Context):
    fd = ctx.t("fuel_deliveries")
    out = []
    for _, g in fd.groupby(["site_id", "carrier", "unit"]):
        med = g.quantity.median()
        big = g.quantity[g.quantity > med / 30]
        ref = big.median() if len(big) else med
        for r in g.itertuples():
            if thousand_factor(r.quantity / ref) == -3:
                out.append(make_issue(fuel_unit.rule, r.record_key, r.year, 0.9, f"{r.quantity} {r.unit} vs median {ref:.0f}",
                                      fld="quantity", observed=r.quantity, proposed=r.quantity * 1000,
                                      changes={"quantity": r.quantity * 1000}))
    return out


# ------------------------------------------------------------------------------------------------ GoO


def registry_by_site_year(reg: pd.DataFrame) -> pd.DataFrame:
    reg = reg.copy()
    reg["vintage_year"] = reg.production_period_start.str[:4].astype(int)
    return (reg.groupby(["beneficiary_site", "consumption_year", "vintage_year"]).mwh.sum().reset_index()
            .rename(columns={"beneficiary_site": "site_id", "consumption_year": "year", "mwh": "mwh_registry"}))


@rule("GOO-REG-01", "goo_cancellations", "certificate_mismatch", "correct",
      "Internal GoO log disagrees with the national registry statement (vintage or MWh); registry values win.")
def goo_mismatch(ctx: Context):
    log = ctx.t("goo_cancellations")
    reg = registry_by_site_year(ctx.t("goo_registry_statement"))
    out = []
    for r in log.itertuples():
        g = reg[(reg.site_id == r.site_id) & (reg.year == r.year)]
        if g.empty:
            out.append(make_issue(goo_mismatch.rule, r.record_key, r.year, 0.8, "no registry cancellation for this site-year",
                                  fld="mwh_cancelled", observed=r.mwh_cancelled, proposed=0.0, changes={"mwh_cancelled": 0.0}))
            continue
        v = g.loc[g.mwh_registry.idxmax()]
        tot = g.mwh_registry.sum()
        if int(v.vintage_year) != int(r.vintage_year):
            out.append(make_issue(goo_mismatch.rule, r.record_key, r.year, 0.9,
                                  f"registry vintage {int(v.vintage_year)} vs log {r.vintage_year}", fld="vintage_year",
                                  observed=r.vintage_year, proposed=int(v.vintage_year),
                                  changes={"vintage_year": int(v.vintage_year), "mwh_cancelled": tot}))
        elif abs(tot - r.mwh_cancelled) > max(1.0, 0.01 * tot):
            out.append(make_issue(goo_mismatch.rule, r.record_key, r.year, 0.85,
                                  f"registry {tot:.1f} MWh vs log {r.mwh_cancelled}", fld="mwh_cancelled",
                                  observed=r.mwh_cancelled, proposed=round(tot, 3), changes={"mwh_cancelled": tot}))
    return out


# ------------------------------------------------------------------------------------------ refrigerant


@rule("REF-UNIT-01", "refrigerant_service_log", "unit_error", "correct",
      "Top-up ~1000x the system's median: grams in the kg column; kg_added / 1000.")
def refrigerant_unit(ctx: Context):
    rf = ctx.t("refrigerant_service_log")
    out = []
    for _, g in rf.groupby(["site_id", "system"]):
        med = g.kg_added.median()
        for r in g.itertuples():
            if thousand_factor(r.kg_added / med) == 3:
                out.append(make_issue(refrigerant_unit.rule, r.record_key, r.year, 0.9, f"{r.kg_added} vs system median {med}",
                                      fld="kg_added", observed=r.kg_added, proposed=r.kg_added / 1000,
                                      changes={"kg_added": r.kg_added / 1000}))
    return out


@rule("REF-GAS-01", "refrigerant_service_log", "wrong_gas_code", "correct",
      "Ammonia (R717) code on a system whose service history is mainly one HFC; code set to that HFC. "
      "Systems mainly on ammonia are legitimate.")
def refrigerant_gas(ctx: Context):
    rf = ctx.t("refrigerant_service_log")
    out = []
    for (site, system), g in rf.groupby(["site_id", "system"]):
        vc = g.refrigerant.value_counts()
        main = vc.index[0]
        if main == "R717_ammonia" or vc.get("R717_ammonia", 0) == 0:
            continue
        for r in g[g.refrigerant == "R717_ammonia"].itertuples():
            out.append(make_issue(refrigerant_gas.rule, r.record_key, r.year, 0.85, f"system '{system}' history is {main}",
                                  fld="refrigerant", observed=r.refrigerant, proposed=main, changes={"refrigerant": main}))
    return out


# ---------------------------------------------------------------------------------------------- waste


@rule("WASTE-UNIT-01", "waste_transfer_notes", "unit_error", "correct",
      "Quantity ~1/1000 of the stream's median: tonnes keyed as kg; quantity x 1000.")
def waste_unit(ctx: Context):
    w = ctx.t("waste_transfer_notes")
    out = []
    for _, g in w.groupby(["site_id", "waste_stream", "treatment"]):
        med = g.quantity.median()
        for r in g.itertuples():
            if thousand_factor(r.quantity / med) == -3:
                q = r.quantity * 1000
                out.append(make_issue(waste_unit.rule, r.record_key, r.year, 0.9, f"{r.quantity} kg vs median {med:.0f}",
                                      fld="quantity", observed=r.quantity, proposed=q, changes={"quantity": q, "t": q / 1000}))
    return out


# --------------------------------------------------------------------------------------------- travel


@rule("TRAVEL-DUP-01", "travel_bookings", "duplicate_record", "correct",
      "Same traveller, date, route, distance and nights as an earlier row in the file; later row dropped "
      "(definition from docs/TASKS_AND_SCORING.md, A1 record keys).")
def travel_duplicate(ctx: Context):
    t = ctx.t("travel_bookings")
    dup = t.duplicated(["traveller_id", "travel_date", "route", "pkm", "nights"], keep="first")
    first = t[~dup].set_index(["traveller_id", "travel_date", "route", "pkm", "nights"]).record_key
    out = []
    for r in t[dup].itertuples():
        orig = first.get((r.traveller_id, r.travel_date, r.route, r.pkm, r.nights))
        out.append(make_issue(travel_duplicate.rule, r.record_key, r.year, 0.95, f"re-import of {orig}", drop=True))
    return out


# ------------------------------------------------------------------------------------------ commuting

MODE_SYNONYMS = {"car": "car", "auto": "car", "henkilöauto": "car", "henkiloauto": "car", "bil": "car",
                 "bus": "bus", "linja-auto": "bus", "buss": "bus", "train": "train", "juna": "train", "tåg": "train",
                 "carpool": "carpool", "kimppakyyti": "carpool", "bike_walk": "bike_walk", "bike": "bike_walk",
                 "walk": "bike_walk", "pyörä": "bike_walk", "kävely": "bike_walk", "ev_car": "ev_car",
                 "ev": "ev_car", "sähköauto": "ev_car"}


@rule("COMM-UNIT-01", "commuting_survey", "unit_error", "correct",
      "One-way distance > 300 km and ~1000x the survey median: metres entered as km; value / 1000.")
def commute_unit(ctx: Context):
    c = ctx.t("commuting_survey")
    med = c.one_way_km.median()
    out = []
    for r in c.itertuples():
        if r.one_way_km > 300 and thousand_factor(r.one_way_km / med) == 3:
            out.append(make_issue(commute_unit.rule, r.record_key, 2025, 0.9, f"{r.one_way_km} km one way",
                                  fld="one_way_km", observed=r.one_way_km, proposed=r.one_way_km / 1000,
                                  changes={"one_way_km": r.one_way_km / 1000}))
    return out


@rule("COMM-MODE-01", "commuting_survey", "mode_mislabel", "correct",
      "Mode label outside the survey's code list (e.g. 'Car', 'henkilöauto', 'linja-auto'); mapped to the code.")
def commute_mode(ctx: Context):
    c = ctx.t("commuting_survey")
    out = []
    for r in c[~c["mode"].isin(COMMUTE_MODES)].itertuples():
        code = MODE_SYNONYMS.get(str(r.mode).strip().lower())
        out.append(make_issue(commute_mode.rule, r.record_key, 2025, 0.9 if code else 0.5,
                              f"label '{r.mode}' -> {code or 'unknown'}", fld="mode", observed=r.mode, proposed=code,
                              changes={"mode": code} if code else {}))
    return out


# ------------------------------------------------------------------------------------------ shipments


@rule("SHIP-LEG-01", "shipments", "missing_leg", "estimate",
      "Inbound document lacks a leg type (factor) that >= 80 % of documents for the same material and origin "
      "have. Estimated leg: tonnes from the document's other legs, km = median km of that leg type for the same "
      "origin in the same year (fallback all years). TENTATIVE method, revisit after dev scores.")
def shipment_missing_leg(ctx: Context):
    sh = ctx.t("shipments")
    erp = ctx.t("erp_purchase_lines")[["doc_no", "material_id", "origin_country", "year"]].drop_duplicates("doc_no")
    inb = sh[sh.direction == "inbound"].merge(erp, left_on="ref_doc", right_on="doc_no", how="left", suffixes=("", "_erp"))
    legs = inb.groupby("ref_doc").ef_id.agg(set)
    docs = inb.drop_duplicates("ref_doc").set_index("ref_doc")
    docs["legs"] = legs
    out = []
    for (mat, origin), g in docs.groupby(["material_id", "origin_country"]):
        if len(g) < 5:
            continue
        counts = pd.Series([e for s in g.legs for e in s]).value_counts() / len(g)
        expected = set(counts[counts >= 0.8].index)
        for ref_doc, d in g.iterrows():
            for ef in sorted(expected - d.legs):
                same = inb[(inb.ef_id == ef) & (inb.origin_country == origin)]
                km_y = same[same.year == d.year].km
                km = float(km_y.median() if len(km_y) else same.km.median())
                t = float(inb[inb.ref_doc == ref_doc].t.max())
                key = f"ship:{ref_doc}:{ef}"
                mode = same["mode"].iloc[0]
                row = dict(record_key=key, shipment_id=None, year=int(d.year), direction="inbound", ref_doc=ref_doc,
                           ef_id=ef, mode=mode, t=t, km=km, tkm=t * km, estimate_method="origin_median_km")
                out.append(make_issue(shipment_missing_leg.rule, key, d.year, 0.85,
                                      f"{mat} from {origin}: {ef} leg present on {counts[ef]:.0%} of documents, missing here; "
                                      f"estimate {t:.1f} t x {km:.0f} km", fld="tkm", proposed=round(t * km, 2), new_row=row))
    return out
