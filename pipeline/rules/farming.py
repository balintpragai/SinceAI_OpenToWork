"""Rules for 03_farming, the farm registry, supplier PCFs and the draft report summary."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from ..farm import organic_share
from ..refdata import ORGANIC_SOIL_THRESHOLD
from .base import Context, make_issue, ratio_to_power_of_ten, rule


def _survey_with_share(ctx: Context) -> pd.DataFrame:
    cache = ctx.tables.get("__survey_share")
    if cache is not None:
        return cache
    sh = organic_share(ctx.t("parcels"), ctx.t("parcel_crop_history_and_plan"))
    sv = ctx.t("farm_survey").merge(sh, on=["farm_id", "crop", "year"], how="left")
    ctx.tables["__survey_share"] = sv
    return sv


@rule("FARM-SOIL-01", "farm_survey", "soil_misreport", "method",
      "Survey says 'Mineral soil' but >= 30 % of the crop's declared parcel area is organic on the soil map. "
      "Emissions use the soil-map organic share for every farm anyway (ADR 0003); this records the discrepancy.")
def soil_misreport(ctx: Context):
    sv = _survey_with_share(ctx)
    bad = sv[(~sv.organic_reported) & (sv.organic_share >= ORGANIC_SOIL_THRESHOLD)]
    return [make_issue(soil_misreport.rule, r.record_key, r.year, 0.7 + 0.25 * min(1.0, (r.organic_share - 0.3) / 0.4),
                       f"organic share {r.organic_share:.2f} of {r.declared_area_ha:.1f} ha on the soil map (~88 % accurate)",
                       fld="soil_type_reported", observed=r.soil_type_reported, proposed=f"organic share {r.organic_share:.2f}")
            for r in bad.itertuples()]


@rule("FARM-AREA-01", "farm_survey", "area_mismatch", "flag",
      "Reported crop area differs from the declared parcel area by more than 20 %. Flag only; the footprint "
      "uses the declared parcel area.")
def area_mismatch(ctx: Context):
    sv = _survey_with_share(ctx)
    r_ = sv.area_ha / sv.declared_area_ha
    bad = sv[(r_ > 1.2) | (r_ < 1 / 1.2)]
    return [make_issue(area_mismatch.rule, r.record_key, r.year, 0.75,
                       f"reported {r.area_ha} ha vs declared {r.declared_area_ha:.2f} ha", fld="area_ha",
                       observed=r.area_ha, proposed=round(r.declared_area_ha, 2))
            for r in bad.itertuples() if pd.notna(r.declared_area_ha)]


def _reference_value(sv: pd.DataFrame, col: str) -> pd.Series:
    """Farm's own median for the crop over other years; crop-year median of respondents as fallback."""
    own = sv.groupby(["farm_id", "crop"])[col].transform(lambda s: s.median() if len(s) >= 3 else np.nan)
    cy = sv.groupby(["crop", "year"])[col].transform("median")
    return own.fillna(cy)


@rule("FARM-DEC-01", "farm_survey", "decimal_shift", "correct",
      "Mineral N ~10x or ~0.1x the farm's own level for the crop: decimal point shifted; value rescaled.")
def n_decimal(ctx: Context):
    sv = _survey_with_share(ctx).copy()
    sv["ref"] = _reference_value(sv, "n_mineral_kg_ha")
    out = []
    for r in sv[sv.n_mineral_kg_ha > 0].itertuples():
        if r.ref and r.ref >= 10:
            k = ratio_to_power_of_ten(r.ref / r.n_mineral_kg_ha)
            if k in (1, -1):
                v = round(r.n_mineral_kg_ha * 10 ** k, 1)
                out.append(make_issue(n_decimal.rule, r.record_key, r.year, 0.75, f"{r.n_mineral_kg_ha} vs farm level {r.ref:.1f}",
                                      fld="n_mineral_kg_ha", observed=r.n_mineral_kg_ha, proposed=v,
                                      changes={"n_mineral_kg_ha": v}))
    return out


@rule("FARM-OUT-01", "farm_survey", "outlier_implausible", "flag",
      "Yield ~10x the crop-year median of respondents (implausible). Flag only.")
def yield_outlier(ctx: Context):
    sv = _survey_with_share(ctx).copy()
    sv["ref"] = sv.groupby(["crop", "year"]).yield_t_ha.transform("median")
    out = []
    for r in sv.itertuples():
        if r.ref and ratio_to_power_of_ten(r.yield_t_ha / r.ref) == 1:
            out.append(make_issue(yield_outlier.rule, r.record_key, r.year, 0.8, f"yield {r.yield_t_ha} vs median {r.ref:.2f} t/ha",
                                  fld="yield_t_ha", observed=r.yield_t_ha, proposed=round(r.yield_t_ha / 10, 3)))
    return out


@rule("FARM-COORD-01", "farm_registry", "coordinate_swap", "correct",
      "Latitude smaller than longitude for a Nordic farm: lat and lon swapped back.")
def coordinate_swap(ctx: Context):
    fr = ctx.t("farm_registry")
    bad = fr[fr.lat < fr.lon]
    return [make_issue(coordinate_swap.rule, r.record_key, None, 0.95, f"lat {r.lat}, lon {r.lon}", fld="lat",
                       observed=f"{r.lat},{r.lon}", proposed=f"{r.lon},{r.lat}", changes={"lat": r.lon, "lon": r.lat})
            for r in bad.itertuples()]


@rule("PCF-UNIT-01", "supplier_pcfs", "pcf_unit_error", "correct",
      "PCF value ~1000x the same supplier-material's other years (g CO2e per kg, or a non-kg declared unit); value / 1000.")
def pcf_unit(ctx: Context):
    p = ctx.t("supplier_pcfs")
    out = []
    for r in p.itertuples():
        other = p[(p.supplier_id == r.supplier_id) & (p.material_id == r.material_id) & (p.year != r.year)].pcf_excl_biogenic
        ref = other.median() if len(other) else 2.0
        k = ratio_to_power_of_ten(r.pcf_excl_biogenic / ref)
        if k == 3 or str(r.declared_unit).lower() not in ("kilogram", "kg"):
            out.append(make_issue(pcf_unit.rule, r.record_key, r.year, 0.9, f"{r.pcf_excl_biogenic} per {r.declared_unit} vs {ref}",
                                  fld="pcf_excl_biogenic", observed=r.pcf_excl_biogenic,
                                  proposed=r.pcf_excl_biogenic / 1000,
                                  changes={"pcf_excl_biogenic": r.pcf_excl_biogenic / 1000,
                                           "pcf_incl_biogenic": r.pcf_incl_biogenic / 1000}))
    return out


@rule("PCF-STALE-01", "supplier_pcfs", "pcf_stale_period", "correct",
      "PCF reference period does not cover the year it is filed for; it is not used (default factor applies). "
      "Source: docs/METHODOLOGY.md §4, supplier PCF validity.")
def pcf_stale(ctx: Context):
    p = ctx.t("supplier_pcfs")
    out = []
    for r in p.itertuples():
        start, end = pd.Timestamp(r.ref_start), pd.Timestamp(r.ref_end)
        if not (start <= pd.Timestamp(f"{r.year}-01-01") and end >= pd.Timestamp(f"{r.year}-12-31")):
            out.append(make_issue(pcf_stale.rule, r.record_key, r.year, 0.95, f"reference period {r.ref_start}..{r.ref_end}",
                                  fld="valid_for_year", observed=f"{r.ref_start}..{r.ref_end}", proposed="not used",
                                  changes={"valid_for_year": False}))
    return out


def _transpositions(n: int):
    s = str(int(n))
    for i in range(len(s) - 1):
        t = s[:i] + s[i + 1] + s[i] + s[i + 2:]
        if t != s and not t.startswith("0"):
            yield int(t)


@rule("REPORT-TOT-01", "draft_report_summary", "total_mismatch", "correct",
      "Draft report total differs from the sum of its scope lines. If transposing two adjacent digits of one line "
      "closes the gap, that line is corrected; the total line is reported too.")
def report_total(ctx: Context):
    rep = ctx.t("draft_report_summary")
    out = []
    for year, g in rep.groupby("year"):
        tot = g[g.line.str.startswith("total")]
        parts = g[~g.line.str.startswith("total")]
        if tot.empty:
            continue
        t = tot.iloc[0]
        s = parts.tco2e.sum()
        if abs(s - t.tco2e) <= 2:
            continue
        culprit = None
        for r in parts.itertuples():
            for v in _transpositions(r.tco2e):
                if abs(s - r.tco2e + v - t.tco2e) <= 2:
                    culprit = (r, v)
        if culprit:
            r, v = culprit
            out.append(make_issue(report_total.rule, r.record_key, year, 0.85,
                                  f"lines sum to {s}, total says {t.tco2e}; {r.tco2e} -> {v} (digits transposed) closes it",
                                  fld="tco2e", observed=r.tco2e, proposed=v, changes={"tco2e": v}))
        out.append(make_issue(report_total.rule, t.record_key, year, 0.6 if culprit else 0.9,
                              f"total {t.tco2e} != sum of lines {s}", fld="tco2e", observed=t.tco2e))
    return out
