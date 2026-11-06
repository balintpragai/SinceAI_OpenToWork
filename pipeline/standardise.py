"""S1 Standardised: normalisations only. Valid values are brought into canonical form (kg, MWh, t, EUR,
English headers, decimal point). No issue is resolved here; values that are wrong stay wrong."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .refdata import FX_PER_EUR

# What each table gains in S1, for the pipeline description and catalog.
NORMALISATIONS = {
    "erp_purchase_lines": "year from posting_date; qty_kg (KG as is, TO x 1000, EUR lines 0); amount_eur = net_amount / FX",
    "energy_meter_readings": "mwh = value (kWh / 1000 if unit is kWh); period = YYYY-MM",
    "waste_transfer_notes": "t = quantity / 1000 (quantity is in kg)",
    "foodhills_odlingsdata": "Swedish headers to English; decimal comma to point; crop names to English codes; ja/nej to bool",
    "supplier_pcfs": "numeric strings to float; reference period to dates",
    "farm_survey": "organic_reported = soil_type_reported starts with 'Organic'",
    "commuting_survey": "mode stripped of surrounding whitespace (labels themselves are checked in S2)",
}

SWEDISH_COLUMNS = {"odlar_id": "grower_id", "skördeår": "year", "gröda": "crop_sv", "areal_ha": "area_ha",
                   "levererad_mängd_ton": "delivered_t", "kvävegiva_kg_ha": "n_kg_ha", "diesel_l_ha": "diesel_l_ha",
                   "bevattnad": "irrigated"}
SWEDISH_CROPS = {"Ärt (frysärt)": "pea", "Ärt": "pea", "Frysärt": "pea"}


def _sv_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype("string").str.replace(" ", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")


def standardise(name: str, df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if name == "erp_purchase_lines":
        d["year"] = d.posting_date.str[:4].astype(int)
        d["qty_kg"] = np.where(d.uom == "TO", d.quantity * 1000, np.where(d.uom == "KG", d.quantity, 0.0))
        d["amount_eur"] = d.net_amount / d.currency.map(FX_PER_EUR).astype(float)
    elif name == "energy_meter_readings":
        d["mwh"] = np.where(d.unit.str.lower() == "kwh", d.value / 1000, d.value)
        d["period"] = d.year.astype(str) + "-" + d.month.map("{:02d}".format)
    elif name == "waste_transfer_notes":
        d["t"] = d.quantity / 1000
    elif name == "foodhills_odlingsdata":
        d = d.rename(columns=SWEDISH_COLUMNS)
        d["year"] = pd.to_numeric(d.year).astype(int)
        for c in ("area_ha", "delivered_t", "n_kg_ha", "diesel_l_ha"):
            d[c] = _sv_float(d[c])
        d["crop"] = d.crop_sv.map(SWEDISH_CROPS).fillna(d.crop_sv)
        d["irrigated"] = d.irrigated.str.strip().str.lower().map({"ja": True, "nej": False})
    elif name == "supplier_pcfs":
        for c in ("pcf_excl_biogenic", "pcf_incl_biogenic", "fossil_ghg", "dluc_ghg", "land_management_ghg",
                  "unitary_product_amount", "primary_data_share"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d["ref_start"] = d.reference_period_start.str[:10]
        d["ref_end"] = d.reference_period_end.str[:10]
    elif name == "farm_survey":
        d["organic_reported"] = d.soil_type_reported.str.lower().str.startswith("organic")
    elif name == "commuting_survey":
        d["mode"] = d["mode"].astype(str).str.strip()
    return d
