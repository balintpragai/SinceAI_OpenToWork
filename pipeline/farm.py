"""Contract-farm footprint (docs/METHODOLOGY.md §5; ADR 0003).

Per hectare we use the formulas of `ccn_tools.farm_calculator.farm_footprint_per_ha`, split into
components, with one deliberate change: the organic-soil term is weighted by the organic share
of the crop's declared parcel area (soil map), instead of a yes/no taken from the survey."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .refdata import F

COMPONENTS = ["fertiliser", "direct_n2o", "indirect_n2o", "diesel", "lime", "organic_soil", "pesticides", "electricity"]
FLAG_COMPONENTS = {"direct_n2o", "indirect_n2o", "lime", "organic_soil"}   # METHODOLOGY.md §5 "FLAG (SBTi) part"
INPUT_COLUMNS = ["n_mineral_kg_ha", "n_manure_kg_ha", "p_kg_ha", "diesel_l_ha", "lime_t_ha", "sprays"]


# Parcels mapped as clay but with a clay content that contradicts the class (<= 10 %) are counted as
# organic with this probability in the *expected* organic share used for emissions. Calibrated on
# the public 2023/2024 dev inventories (category 1); see ADR 0003. Set to 0 to use the soil map only.
LOW_CLAY_MAX_PCT = 10.0
LOW_CLAY_ORGANIC_PROBABILITY = 0.42


def organic_share(parcels: pd.DataFrame, crop_history: pd.DataFrame,
                  low_clay_probability: float = LOW_CLAY_ORGANIC_PROBABILITY) -> pd.DataFrame:
    """Declared area and organic share per farm x crop x year.

    organic_share           soil-map organic area / declared area (used for `soil_misreport`)
    organic_share_expected  adds `low_clay_probability` x area of clay-mapped parcels with clay <= 10 %
                            (used for emissions)"""
    ch = crop_history[crop_history.status == "declared"].merge(
        parcels[["parcel_id", "area_ha", "soil_class_soilmap", "clay_pct_soilmap"]], on="parcel_id", how="left")
    ch["organic_ha"] = np.where(ch.soil_class_soilmap == "organic", ch.area_ha, 0.0)
    low = (ch.soil_class_soilmap == "clay") & (ch.clay_pct_soilmap <= LOW_CLAY_MAX_PCT)
    ch["low_clay_ha"] = np.where(low, ch.area_ha, 0.0)
    g = ch.groupby(["farm_id", "crop", "year"]).agg(declared_area_ha=("area_ha", "sum"), organic_ha=("organic_ha", "sum"),
                                                     low_clay_ha=("low_clay_ha", "sum"),
                                                     n_parcels=("parcel_id", "nunique")).reset_index()
    area = g.declared_area_ha.where(g.declared_area_ha > 0)
    g["organic_share"] = g.organic_ha / area
    g["organic_share_expected"] = (g.organic_ha + low_clay_probability * g.low_clay_ha) / area
    return g


def footprint_components_per_ha(df: pd.DataFrame, grid_kg_per_kwh) -> pd.DataFrame:
    """kg CO2e/ha per component. df needs crop, INPUT_COLUMNS, yield_t_ha, organic_share, irrigated,
    fertiliser_product (optional)."""
    E = F.FARM_EF
    n2o = E["n2o_n_to_n2o"] * E["n2o_gwp"]
    nmin = df.n_mineral_kg_ha.fillna(0).values
    nman = df.n_manure_kg_ha.fillna(0).values
    yld = df.yield_t_ha.fillna(0).values
    res_n = df.crop.map(F.RESIDUE_N_PER_T).fillna(0).values * yld
    low = df.get("fertiliser_product", pd.Series("", index=df.index)).fillna("").str.contains("low-carbon").values
    fert = np.where(low, E["fert_n_prod_lowcarbon"], E["fert_n_prod"])
    p = df.p_kg_ha.fillna(0).values
    out = pd.DataFrame(index=df.index)
    out["fertiliser"] = nmin * fert + p * E["fert_p_prod"] + p * 2.2 * E["fert_k_prod"]
    out["direct_n2o"] = (nmin * E["ef1_synthetic"] + (nman + res_n) * E["ef1_organic"]) * n2o
    out["indirect_n2o"] = ((nmin * E["frac_gasf"] + nman * E["frac_gasm"]) * E["ef4_n2o_n"]
                           + (nmin + nman + res_n) * E["frac_leach"] * E["ef5_n2o_n"]) * n2o
    out["diesel"] = df.diesel_l_ha.fillna(0).values * (E["diesel_ttw"] + E["diesel_wtt"])
    out["lime"] = df.lime_t_ha.fillna(0).values * E["lime"] * 1000
    co2 = np.where(df.crop.values == "grass_ley", E["org_soil_co2_grass_t_ha"], E["org_soil_co2_t_ha"]) * 1000
    out["organic_soil"] = df.organic_share.fillna(0).values * (co2 + E["org_soil_n2o_n_kg_ha"] * n2o)
    out["pesticides"] = df.sprays.fillna(0).values * E["spray_pass"]
    kwh_t = df.crop.map({c: v["kwh_t"] for c, v in F.MGMT_NORMS.items()}).fillna(0).values
    irr = df.irrigated.fillna(False).astype(bool).values
    out["electricity"] = (kwh_t * yld + np.where(irr, 180.0, 0.0)) * np.asarray(grid_kg_per_kwh, dtype=float)
    return out
