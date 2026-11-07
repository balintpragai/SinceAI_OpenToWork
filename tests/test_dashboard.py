"""Dashboard charts (copilot/dashboard.py) agree with the pipeline's own totals; needs a built lakehouse."""
import json

import pytest

from copilot import dashboard as D, gold, tools

pytestmark = pytest.mark.skipif(not gold.has("line_items") or not gold.has("summary"), reason="lakehouse not built")


def _summary_total(year: int) -> float:
    s = gold.frame(gold.GOLD["summary"])
    s = s[(s["year"] == year) & (s["scope"] == "total")]
    return float(s[s["category"].isin(["scope1_total", "scope2_market_total", "scope3_total"])]["tco2e"].sum())


@pytest.mark.parametrize("year", [2023, 2025])
def test_every_chart_renders_and_is_json(year):
    d = D.dashboard(year)
    assert set(d["charts"]) == {c for sec in d["sections"] for c in sec["charts"]}
    for c in d["charts"].values():
        assert "error" not in c and c["title"] and c["kind"], c
    json.dumps(tools.clean(d, cap=None), allow_nan=False)


@pytest.mark.parametrize("year", [2023, 2025])
def test_totals_match_pipeline_summary(year):
    total = _summary_total(year)
    assert D.kpis(year)["rows"][0]["value"] == pytest.approx(total, abs=1)
    assert sum(r["value"] for r in D.scope_split(year)["rows"]) == pytest.approx(total, abs=2)
    wf = D.corrections(year)["rows"]
    assert wf[0]["value"] + sum(r["value"] for r in wf if r["type"] == "delta") == pytest.approx(wf[-1]["value"], abs=len(wf))
    assert wf[-1]["value"] == pytest.approx(total, abs=1)


def test_trust_shares_sum_to_100():
    t = D.kpis(2025)["trust"]
    assert sum(t.values()) == pytest.approx(100, abs=0.2)


def test_show_chart_tool_rejects_unknown_id():
    assert "error" in tools.show_chart("nope")
    assert tools.show_chart("levers")["kind"] == "lever_bars"


def test_farm_shares_add_up():
    rows = D.farm_concentration(2025)["rows"]
    assert all(r["Farms with peat soils"] + r["Farms on mineral soils only"] == pytest.approx(100, abs=0.2) for r in rows)
    src = D.farm_sources(2025)["rows"]
    assert sum(r["value"] for r in src) == pytest.approx(D.farm_summary(2025)["rows"][0]["value"], abs=len(src))
