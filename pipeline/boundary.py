"""Organisational boundary (GLOSSARY: Organisational boundary). A site belongs to the inventory from the
first month after its acquisition (structural_events) or from Jan of `in_group_from`, until Dec of
`in_group_to` when that is set. Source: docs/METHODOLOGY.md §1 (Foodhills included from Dec 2025)."""
from __future__ import annotations

import pandas as pd


class Boundary:
    def __init__(self, sites: pd.DataFrame, events: pd.DataFrame):
        self.start: dict[str, pd.Period] = {}
        self.end: dict[str, pd.Period | None] = {}
        for _, s in sites.iterrows():
            self.start[s.site_id] = pd.Period(f"{int(s.in_group_from)}-01", "M")
            self.end[s.site_id] = None if pd.isna(s.in_group_to) else pd.Period(f"{int(s.in_group_to)}-12", "M")
        acq = events[events["type"] == "acquisition"]
        for _, e in acq.iterrows():
            for _, s in sites.iterrows():
                token = str(s["name"]).split(" ")[0]
                if token and token in str(e.event):
                    self.start[s.site_id] = max(self.start[s.site_id], pd.Period(e.date, "M") + 1)

    def contains(self, site_id: str, year: int, month: int = 12) -> bool:
        if site_id not in self.start:      # e.g. FLEET: vehicles belong to the group
            return True
        p = pd.Period(f"{int(year)}-{int(month):02d}", "M")
        end = self.end[site_id]
        return p >= self.start[site_id] and (end is None or p <= end)

    def describe(self) -> pd.DataFrame:
        return pd.DataFrame([dict(site_id=k, from_month=str(v), to_month=str(self.end[k]) if self.end[k] else None)
                             for k, v in self.start.items()])
