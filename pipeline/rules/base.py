"""Rule framework for S2 (detect) and S3 (apply). A rule inspects S1 tables and returns issues. Each
issue says what it would change: `changes` (field -> new value), `drop` (exclude the record) or
`new_row` (an estimate for a missing record). Detection is deterministic (ADR 0002)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

ACTIONS = ("correct", "estimate", "method", "flag")


@dataclass(frozen=True)
class Rule:
    rule_id: str
    table: str
    issue_type: str
    action: str           # correct | estimate | method | flag
    description: str
    detect: Callable[["Context"], list[dict]] = field(repr=False, compare=False)


@dataclass
class Context:
    """S1 tables plus the organisational boundary, shared by all rules."""
    tables: dict[str, pd.DataFrame]
    boundary: "object"

    def t(self, name: str) -> pd.DataFrame:
        return self.tables[name]


def issue_id(record_key: str, issue_type: str, fld: str | None) -> str:
    h = hashlib.sha1(f"{record_key}|{issue_type}|{fld or ''}".encode()).hexdigest()[:12]
    return f"iss:{h}"


def make_issue(rule: Rule, record_key: str, year, confidence: float, evidence: str, *, fld: str | None = None,
               observed=None, proposed=None, changes: dict | None = None, drop: bool = False,
               new_row: dict | None = None) -> dict:
    return dict(
        issue_id=issue_id(record_key, rule.issue_type, fld), table=rule.table, record_key=record_key,
        year=int(year) if year is not None and not pd.isna(year) else None, issue_type=rule.issue_type,
        rule_id=rule.rule_id, action=rule.action, confidence=round(float(confidence), 3), field=fld,
        observed_value=None if observed is None or (isinstance(observed, float) and pd.isna(observed)) else str(observed),
        proposed_value=None if proposed is None else str(proposed), evidence=evidence,
        changes=changes or {}, drop=bool(drop), new_row=new_row,
    )


RULES: list[Rule] = []


def rule(rule_id: str, table: str, issue_type: str, action: str, description: str):
    assert action in ACTIONS, action

    def deco(fn):
        r = Rule(rule_id, table, issue_type, action, description, fn)
        fn.rule = r
        RULES.append(r)
        return fn
    return deco


def thousand_factor(r: float) -> int | None:
    """+3 if r is roughly 1000x (10^2.3 .. 10^3.7), -3 if roughly 1/1000x, else None. Unit slips
    (kWh/MWh, g/kg, l/m3, kg/t) are exact factors of 1000 but the reference median is noisy."""
    import math
    if r is None or r <= 0 or pd.isna(r):
        return None
    lg = math.log10(r)
    if 2.3 <= lg <= 3.7:
        return 3
    if -3.7 <= lg <= -2.3:
        return -3
    return None


def ratio_to_power_of_ten(r: float) -> int | None:
    """Return k if r is close to 10**k (k != 0), else None. Used for unit slips and decimal shifts."""
    import math
    if r is None or r <= 0 or pd.isna(r):
        return None
    k = round(math.log10(r))
    if k == 0:
        return None
    return k if abs(math.log10(r) - k) < 0.35 else None
