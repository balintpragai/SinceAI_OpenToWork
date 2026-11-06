"""Reference check (ADR 0001) and self-check against the public dev keys."""
from __future__ import annotations

import pandas as pd

from .emissions import summarise
from .refdata import ccn_score, reference_calculator

TOLERANCE_T = 0.05   # absolute tolerance per category (t), covers float noise


def reference_check(T: dict, eli: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    rows = []
    for y in years:
        ref = reference_calculator.summarise(reference_calculator.compute_inventory(T, y))
        ours = summarise(eli, y).set_index(["scope", "category"]).tco2e
        for r in ref.itertuples():
            v = float(ours.get((r.scope, r.category), 0.0))
            rows.append(dict(year=y, scope=r.scope, category=r.category, reference_tco2e=float(r.tco2e), line_items_tco2e=v,
                             diff_tco2e=v - float(r.tco2e), ok=abs(v - float(r.tco2e)) <= TOLERANCE_T))
    return pd.DataFrame(rows)


def self_check(issues_a1: pd.DataFrame, eli: pd.DataFrame, a1_key: pd.DataFrame, a2_keys: dict[int, pd.DataFrame],
               dev_years) -> pd.DataFrame:
    rows = []
    sub = issues_a1[issues_a1.year.isin(dev_years)]
    a1 = ccn_score.score_a1(sub, a1_key, list(dev_years))
    rows.append(dict(check="A1", years="-".join(map(str, dev_years)), score=a1["score"], precision=a1["precision"],
                     recall=a1["recall"], f1=a1["f1"], detail=str(a1["recall_by_type"])))
    for y, key in a2_keys.items():
        s = summarise(eli, y)[["scope", "category", "tco2e"]]
        a2 = ccn_score.score_a2(s, key)
        rows.append(dict(check="A2", years=str(y), score=a2["score"], precision=None, recall=None, f1=None,
                         detail=str({k: v["error_pct"] for k, v in a2["detail"].items()})))
    return pd.DataFrame(rows)
