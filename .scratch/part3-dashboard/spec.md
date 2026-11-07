# Part 3: Dashboard

Status: ready-for-agent (approved 2026-11-07)

A visual dashboard for non-technical readers (sustainability managers, executives), plus charts inside copilot answers. Vocabulary follows [GLOSSARY.md](../../GLOSSARY.md).

## Inspiration (competitor review, 2026-11-07)

- **Headline tiles:** Microsoft Sustainability's 3–4 headline tiles and "Include pending data" draft toggle.
- **Trust next to every number:** CarbonCloud's trust indicators (share of primary data, quality grade, a change log that separates real reductions from data fixes).
- **Hotspots and tracing:** Watershed's hotspot ranking and "trace every number to its source".
- **Farm-to-product breakdowns:** from Foodsteps and Klimato.
- **Charts inside answers:** Power BI Copilot and ThoughtSpot answer with native charts and show the query and data used.
- **Left out on purpose:** "= X flights" style comparisons.

## Design

- **One chart registry:** `copilot/dashboard.py` `CHARTS`. Each function takes a year and returns `{id, title, kind, unit, rows, status, sources, note?, trust?, series?}`.
  - `title` is the takeaway, computed from the numbers.
  - `sources` are plain names.
- **API:** `GET /api/dashboard?year=` returns every chart, grouped into `SECTIONS`.
- **Copilot tool:** `show_chart(chart_id, year)` calls the same functions. The chart travels in the answer's tool trace, and the chat renders it with the same `ChartCard` the dashboard uses, so the numbers always agree.
- **Totals are market-based** (location-based Scope 2 is dropped to avoid double counting).
- **Target:** base year 2021 (the first pipeline year), with a 4.2 %/yr linear reduction for Scope 1+2.
- **Landing page:** the Dashboard is the default view.

## Layout (revised 2026-11-07)

- **One scrolling page, not tabs.** Executive dashboards are a single page read top to bottom.
- **Sticky header:** year, draft/published status, and section links that highlight the section in view.
- **Language:** professional and direct.
  - GHG Protocol category names.
  - Scope 1/2/3 with a one-line definition.
  - Every title states the finding with its figure.

**Sections**, in executive reading order:
1. **Executive summary:** kpis, scope_split, trend.
2. **Emission sources:** top_categories, land_use, top_materials.
3. **Decarbonisation pathway:** target_path, levers (labelled as design estimates), carbon_cost (3 scenarios).
4. **Agricultural supply chain:** farm_summary, farm_sources (4 source groups), farm_concentration (peat-soil farms' share of farms vs share of emissions), crop_intensity (with volume delivered).
   - Replaces the earlier "Farm to freezer" page and its unlabelled farm scatter chart.

**"Ask the copilot"** on any chart starts a new conversation.

**Data quality moved to the Data review page** (PR #4). corrections, issues_by_type and published_vs_checked are no longer on the dashboard; the copilot can still show them with `show_chart`.

## Findings during the build

- **The draft 2025 report summary was calculated on uncleaned data.** It matches `data.inventory(2025)` exactly (1,117,417 t for purchased electricity). Cleaning takes 18.8 million t down to 246,451 t.
- **No emission line item is marked `flagged`.** The 103 open flagged issues are on records that carry no emissions (field areas, outliers), so "needs review" is 0 % of tCO2e but 15 items in 2025.

## Tests

`tests/test_dashboard.py` covers four things:
- every chart renders and is valid JSON;
- totals match `gold_inventory_summary`;
- the waterfall adds up;
- trust shares sum to 100 %.

The tests are skipped if no lakehouse has been built.
