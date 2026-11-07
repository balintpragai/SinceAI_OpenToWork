"""As recorded: the same S3 -> S4 -> Gold code run on S1 with no issue applied (organisational boundary still applied).

The difference between the Gold line items and these is exactly what the corrections, estimates and exclusions
changed, so readers (the web app's Data review view) can show "as first recorded -> after fixes" and the effect of
each issue without re-running pipeline code. Written by run.py as:

  gold_emission_line_items_as_recorded   line items with no issue applied (same columns as gold_emission_line_items)
  gold_inventory_summary_as_recorded     summarise() of those, per year
  gold_issue_effects                     year x issue x scope x category: tCO2e the issue changed (after - as recorded)
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .canonical import build_canonical
from .correct import stage_s3
from .emissions import emission_line_items

_ISSUE_COLS = ["issue_id", "table", "record_key", "action", "changes", "drop", "new_row", "field", "observed_value",
               "proposed_value", "evidence", "rule_id"]
EFFECT_COLUMNS = ["year", "issue_id", "scope", "category", "dt_tco2e"]


def as_recorded_line_items(s1: dict, boundary, years, log=print) -> pd.DataFrame | None:
    """Gold line items with no issue applied. None when the raw values break a calculation."""
    try:
        s3r, _, _ = stage_s3(s1, pd.DataFrame(columns=_ISSUE_COLS), None, "as_recorded")
        Tr, _ = build_canonical(s3r, boundary)
        return emission_line_items(Tr, s3r, years)
    except Exception as e:  # raw values can break a calculation; readers then show "as recorded" as unknown
        log(f"as recorded: calculation failed ({e!r}); skipping")
        return None


def issue_effects(eli: pd.DataFrame, raw: pd.DataFrame, issues: pd.DataFrame, s3: dict) -> pd.DataFrame:
    """Split (after - as recorded) per record over the issues that caused it.

    A record's change is split equally over its issues. GoO registry corrections land on that site-year's
    electricity meters; farm-survey corrections land on the farm's deliveries (factor_id farm_footprint:...).
    Changes no issue explains (pro-rata GoO cover, per-respondent commuting scale, farm totals) get issue_id None."""
    key_cols = ["year", "record_key", "scope", "category", "akey"]

    def prep(df, sign):
        d = df[["year", "record_key", "scope", "category", "factor_id", "tco2e"]].copy()
        fid = d.factor_id.astype(str)
        d["akey"] = np.where(fid.str.startswith("farm_footprint:"), fid, "")
        d["dt"] = d.tco2e * sign
        return d.groupby(key_cols, dropna=False).dt.sum()

    delta = prep(eli, 1).add(prep(raw, -1), fill_value=0.0)
    delta = delta[delta.abs() > 1e-9].reset_index()

    by_record = issues.groupby("record_key").issue_id.apply(list).to_dict()
    goo = defaultdict(list)                          # (site, year) -> GoO issue ids
    for r in issues[issues.table == "goo_cancellations"].itertuples():
        parts = r.record_key.split(":")
        goo[(parts[1], int(parts[2]))].append(r.issue_id)
    farm = defaultdict(list)                         # farm_footprint key -> survey issue ids
    sv = s3["farm_survey"].set_index("record_key")
    for r in issues[issues.table == "farm_survey"].itertuples():
        if r.record_key in sv.index and r.action != "method":
            s = sv.loc[r.record_key]
            farm[f"farm_footprint:{s.farm_id}:{s.crop}:{int(s.year)}"].append(r.issue_id)

    out: dict[tuple, float] = defaultdict(float)
    for r in delta.itertuples():
        owners = []
        if r.akey and farm.get(r.akey):
            owners = farm[r.akey]
        elif r.record_key in by_record:
            owners = by_record[r.record_key]
        elif str(r.record_key).startswith("energy:") and r.category == "purchased_electricity":
            p = r.record_key.split(":")
            owners = goo.get((p[1], int(p[2][:4])), [])
        for iid in owners or [None]:
            out[(int(r.year), iid, r.scope, r.category)] += r.dt / max(1, len(owners))
    return pd.DataFrame([dict(zip(EFFECT_COLUMNS, (*k, v))) for k, v in out.items()], columns=EFFECT_COLUMNS)
