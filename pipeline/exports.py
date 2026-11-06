"""A1 and A2 submission exports (formats from tasks/templates/), stamped draft or published."""
from __future__ import annotations

import pandas as pd

from .emissions import summarise

A2_METHOD_NOTES = {
    "scope1": "record-level line items; fuels = deliveries - stock change (NCV), meters; refrigerants kg x GWP100",
    "scope2_location": "meter MWh x national grid average",
    "scope2_market": "MWh not covered by registry GoOs of the same vintage x residual mix; heat x supplier factor",
    "scope3": "record-level line items, see gold_emission_line_items",
    "total": "sum of scope line items",
    "memo": "biogenic CO2 from wood chips, side streams, biogas and the bio share of diesel",
}


def a1_rows(issues: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    """All non-rejected issues, one row per record key (highest confidence first)."""
    st = status.set_index("issue_id").status
    d = issues[issues.issue_id.map(st) != "rejected"].copy()
    d = d.sort_values("confidence", ascending=False).drop_duplicates("record_key")
    d = d.rename(columns={"evidence": "explanation"})
    return d[["table", "record_key", "issue_type", "confidence", "explanation", "year"]].sort_values(["table", "record_key"])


def a1_export(issues: pd.DataFrame, status: pd.DataFrame, year: int) -> pd.DataFrame:
    d = a1_rows(issues, status)
    return d[(d.year == year) | d.year.isna()].reset_index(drop=True)


def a2_export(eli: pd.DataFrame, template: pd.DataFrame, year: int) -> pd.DataFrame:
    s = summarise(eli, year).set_index(["scope", "category"])
    out = template[["scope", "category"]].copy()
    out["tco2e"] = [round(float(s.tco2e.get((a, b), 0.0)), 2) for a, b in zip(out.scope, out.category)]
    out["method_note"] = out.scope.map(A2_METHOD_NOTES)
    return out


def write_csv(df: pd.DataFrame, path) -> None:
    """Exports keep the exact template columns; the draft/published status is carried by the folder
    (Files/exports/<status>/) and the gold_export_manifest table."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
