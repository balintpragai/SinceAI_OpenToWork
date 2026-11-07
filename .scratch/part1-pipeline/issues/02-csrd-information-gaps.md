# Close the CSRD information gaps in the Gold layer

Status: needs-triage

## Problem

The pipeline produces a traceable GHG inventory, but the CSRD (Directive (EU) 2022/2464, amending Directive 2013/34/EU) asks for much more than Scope 1–3 totals. This ticket lists what is missing, checked against the three EUR-Lex versions:

- original text: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022L2464
- consolidated 17.04.2025 (Directive (EU) 2025/794): https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02022L2464-20250417
- consolidated 18.03.2026 (Directive (EU) 2026/470): https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02022L2464-20260318

Evidence: Docker run `run-20261107T094418Z-585f7699` (git `0903697`), reference check OK, all exports `draft`. Tables read: `gold_catalog` (Gold and S4 rows), `gold_inventory_summary`, `gold_a2_submission`, `gold_boundary`, `gold_dim_sites`, an aggregate of `gold_emission_line_items`, and the column lists of the S3/S4 tables named below.

### Does the CSRD apply to Apetit?

| Version | Application to a large undertaking |
|---|---|
| Original | FY2025 (Art 5(2)(b)) |
| 2025/794 | Postponed to FY2027 |
| 2026/470 | From FY2027 only > EUR 450 m net turnover **and** > 1,000 employees |

The 2026/470 thresholds are **not verified verbatim**: EUR-Lex returned an empty page for the amending directive, and the figures come from a summary of the consolidated text. `07_frameworks/framework_digest.md` (ESRS section) says the same and expects Apetit to report voluntarily. The gaps still matter for voluntary reporting and for data requests from in-scope customers, which Art 29b(4) limits to the SME standard.

### Already covered

- Scope 1, Scope 2 location- and market-based, Scope 3 at record level with lineage (Art 29b(2)(a)(i)).
- Correction log, estimates marked, reference check, draft/published status: a basis for limited assurance (Art 34(1)(aa)).
- FLAG part separated (2025: 174,232 of 220,923 tCO2e in cat 1).
- Biogenic CO2 memo, Scope 1 only (2025: 10,948 t).

## Gaps

| # | Requirement | Today | Gap | Fix type |
|---|---|---|---|---|
| 1 | Resilience, principal risks and dependencies, adaptation (19a(2)(a)(i), (g); 29b(2)(a)(ii)) | `04_climate`, `06_nature` out of scope (spec, "Scope"); `transition_scenarios` stops at S3 | No physical-risk exposure per site/parcel, no scenario outputs | New ingestion |
| 2 | Transition plan with implementing actions, financial and investment plans; 1.5 °C; coal/oil/gas exposure (19a(2)(a)(iii)) | `s3_decarbonisation_levers`, `s3_capex_projects` | No Gold table; capex not linked to levers; no EU Taxonomy fields, though Art 29d requires marking up the Art 8 Reg 2020/852 disclosures | Gold build + decision |
| 3 | Absolute GHG reduction targets 2030/2050, progress, scientific basis (19a(2)(b)) | Nothing | No targets table, no base year; `structural_events` not used for base-year recalculation (Foodhills in, Pudasjärvi out). Refrigerants: 32,417 t (2021), 22,703 t (2022) vs 824–1,094 t (2023–2025): settle before choosing a base year | Decision + Gold build |
| 4 | Water and marine resources (29b(2)(a)(iii)) | `s4_water_balance` (flow, source_or_destination, m3), `s4_wastewater` (m3) | Not in Gold: no withdrawal/discharge/consumption; no water-stress class per site | Gold build + new data (stress) |
| 5 | Pollution (29b(2)(a)(v)) | Wastewater m3 only | No N, P or COD loads; farm N/P per ha in `gold_farm_footprints`; `monitored_catchment_loads` in excluded `06_nature` | New ingestion |
| 6 | Biodiversity and ecosystems (29b(2)(a)(vi); recital 53) | `gold_dim_parcels` (catchment, dist_to_water, buffer_strip, p_test), `gold_dim_materials` (eudr_commodity, sbtn_high_impact_commodity) | Nothing aggregated: no land-use metric, no catchment state of nature, no sites near sensitive areas, no EUDR exposure by volume | New ingestion + Gold build |
| 7 | Resource use and circular economy (29b(2)(a)(iv)) | `s4_waste` (waste_stream, treatment, t) | No hazardous/non-hazardous split, no recovery vs disposal; material inflows and packaging t not reported as metrics | Gold build + new field |
| 8 | GHG detail (29b(2)(a)(i); recital 47) | Line items, inventory summary | Scope 3 cats 8, 10, 13, 14, 15 absent with no screening note (cat 10 plausible for Kantvik oil/expeller); no intensity per net revenue (`s4_sales.net_sales_eur` exists); no energy consumption/mix (`s4_energy`, `s4_goo` exist); no removals or credits; biogenic CO2 zero for Scope 2/3; share of supplier-specific data not output (PCF 28.8 %, farm-specific 11.0 % of 2025 Scope 3) | Gold build |
| 9 | Value-chain information and 3-year transition rule (19a(3)) | Non-respondent farms estimated | No record of efforts, reasons and plans when value-chain data is missing; Swedish farms excluded from 2025 though S-BJU is in the boundary from 2025-12 | Gold build + decision |
| 10 | Process, digital format, assurance (19a(2) last subpara.; 29d; 34) | CSV exports, all `draft` | No materiality/IRO register or time horizons; no mapping to ESRS datapoint IDs for tagging; not signed off; ticket 01 open | Process |
| 11 | Social and governance (29b(2)(b), (c)) | Headcount, commuting, travel | Out of this pipeline's scope; contract-farm workers are value-chain workers | Out of scope |

## To decide / do

- Decide whether `04_climate` and `06_nature` come into scope (gaps 1, 5, 6). The spec excludes them today.
- Add Gold tables for data already at S4 (gaps 4, 7, 8): water balance, waste by treatment, energy by carrier with renewable share, intensity per net revenue, Scope 3 category screening with an exclusion reason per category.
- Promote levers and capex to Gold and link them (gap 2). Add a targets/base-year table once management sets targets (gap 3).
- Add a column or table that records, per value-chain data gap, the effort made, the reason and the plan (gap 9).
- Add a datapoint mapping table (ESRS datapoint ID → Gold table/column) for tagging under Art 29d (gap 10).
- Check the 2025 heat: 2021–2023 have `purchased_heat_steam` line items, 2024–2025 have none. Possibly real (in-house biosteam), but confirm.
- Read Directive (EU) 2026/470 verbatim before relying on the thresholds or any change to Art 19a/29b.

## Caveats

- The ESRS-level datapoints (water stress, energy mix, removals, revenue intensity) come from `framework_digest.md` and general knowledge. The directive names the topics and delegates detail to the standards (Art 29b).
- Under AGENTS.md, only approved tables were read, and some only as schemas or aggregates.

## Comments
