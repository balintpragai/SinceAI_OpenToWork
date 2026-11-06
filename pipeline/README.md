# Part 1 pipeline: how it works

This pipeline turns the raw Apetit challenge package into traceable Delta tables. It produces the A1 issue list and the A2 2025 inventory, and every inventory number can be traced back to the source rows it came from. Terms follow [GLOSSARY.md](../GLOSSARY.md). Decisions are recorded in [docs/adr/](../docs/adr/). This description is also indexed for the agent.

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
python -m pipeline run          # reprocesses everything from Raw to Gold (~20 s)
python -m pytest                # rule and allocation unit tests
```

Environment variables:
- `CCN_PACKAGE_ROOT`: the unzipped challenge package. Default `.tmp/Apetit_SinceAI2026/.../APETIT_CLIMATE_NATURE_NAVIGATOR_2026`.
- `CCN_LAKEHOUSE`: the output lakehouse. Either a local folder (default `lakehouse/`) or `az://<container>`, an Azure Blob container such as Azurite. For `az://`, also set `AZURE_STORAGE_BLOB_ENDPOINT`, and optionally `AZURE_STORAGE_ACCOUNT_NAME` and `AZURE_STORAGE_ACCOUNT_KEY` (they default to the public Azurite development account).
- `GEMINI_API_KEY`: turns on embeddings for the document index.

The command exits with code 1 if the reference check fails.

### With Docker

There is one container per job. The lakehouse is Azurite, which stands in for the Fabric Lakehouse (OneLake). The pipeline container mounts the challenge package read-only.

```bash
cp .env.example .env                       # set CCN_PACKAGE_DIR and, optionally, GEMINI_API_KEY
docker compose up -d lakehouse
GIT_COMMIT=$(git rev-parse --short HEAD) docker compose run --rm --build pipeline
```

Tables land in the blob container `lakehouse` under `Tables/`, and files under `Files/`. That is the same layout as a Fabric Lakehouse. Moving to production means pointing at OneLake (`abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<lakehouse>.Lakehouse`) with Entra ID authentication. The agent (Part 2) and the dashboard (Part 3) attach to the same lakehouse; their services are stubbed in `docker-compose.yml`.

## Stages

| Stage | Output | What happens |
|---|---|---|
| Raw | `Files/raw/…`, `raw_file_manifest` | Byte copy of every in-scope file, with SHA-256. Only this stage reads the package. |
| Bronze | `bronze_<source>` | Parsed. `record_key`, `_source_file` and `_source_row` added. No values change. |
| S1 Standardised | `s1_<source>` | Normalisations only: kg, MWh, t, EUR, decimal comma, Swedish headers. |
| S2 Validated | `s2_issue_log` | Deterministic rules detect issues (ADR 0002). No values change. |
| S3 Corrected | `s3_<source>`, `s3_correction_log`, `s3_issue_status` | Corrections and estimates applied; flagged issues marked with `has_flag`; reviewer decisions from `review_decisions` applied. |
| S4 Canonical | `s4_<table>`, `s4_lineage` | Tables of METHODOLOGY.md §2, with the organisational boundary applied. |
| Gold | `gold_*` | Emission line items, inventory summary, issues, exports, checks, catalog. |

Each run writes one Delta version per table. The commit metadata carries `run_id`, `git_commit` and `inputs_sha256`, so earlier runs can be read back.

## Issues and what happens to them

The rule catalogue (`gold_rule_catalog`) is generated from the code on every run. Summary:

| Action | Issue types |
|---|---|
| Correct | `duplicate_record` (later row excluded), `unit_error`, `decimal_shift`, `currency_error`, `material_mismatch` (material taken from the ERP text), `pcf_unit_error`, `pcf_stale_period` (PCF not used, default factor applies), `wrong_gas_code`, `certificate_mismatch` (registry wins), `coordinate_swap`, `mode_mislabel` (label mapped to the survey code), `total_mismatch` |
| Estimate | `missing_record`, `meter_spike` (seasonal profile: the year's available months ÷ their median profile share × the month's share), `missing_leg` (median km of that leg type from the same origin; *tentative*) |
| Method | `soil_misreport`: recorded; emissions use the soil-map organic share for every farm anyway (ADR 0003) |
| Flag only | `outlier_implausible`, `area_mismatch` |

Legitimate oddities are never raised as issues: credit notes (movement 122), vessel lots in tonnes, seasonal meter peaks and ammonia systems. Nothing is estimated outside the organisational boundary; for example, Bjuv counts only from December 2025.

## Calculation

Emission line items (`gold_emission_line_items`) have one row per source record × emission factor. Each row carries `tco2e`, `flag_tco2e`, `biogenic_co2_t`, a `component` (for farm items), `activity_value` and `activity_unit`, `factor_id`, `factor_source`, `is_estimate` and `flagged`. The method mirrors `ccn_tools.reference_calculator`. Three steps are allocated back to records, and the `allocation` column says how:
- the GoO cover, shared pro rata over meter months;
- commuting, as the survey mean × headcount, shared equally per respondent;
- farm emissions, shared over the farm's deliveries by kg.

On every run, the reference calculator is run on our S4 tables, and the line items must match it per category (`gold_reference_check`).

**Contract farms** (METHODOLOGY.md §5, ADR 0003): per-hectare footprint × declared parcel area, divided by delivered kg. The organic-soil term uses the *expected* organic share: the soil map's organic area plus 0.42 × the area of parcels mapped as clay with ≤ 10 % clay. The 0.42 was calibrated on the 2023/2024 dev inventories. Farms that didn't answer the survey get the crop-year median of respondents' inputs, marked as an estimate.

## Document index (for the agent)

`gold_doc_chunks` holds these documents, split along their Markdown headings:
- the framework digest and the package `docs/*.md`;
- our GLOSSARY, this description and the ADRs;
- two documents generated on every run: the rule catalogue and the table catalog.

The challenge brief is excluded. Each chunk carries `file`, `heading_path` and `chunk_id`, and its text starts with `[file > section]`, so an answer can cite file and section.

When `GEMINI_API_KEY` is set, chunks are embedded with `gemini-embedding-001` (task `RETRIEVAL_DOCUMENT`, 768 dimensions, L2-normalised). Unchanged chunks reuse their earlier vectors, matched by text hash.

**Contract for Part 2:** embed queries with the same model and dimension, using task `RETRIEVAL_QUERY`; normalise, and rank by dot product. `gold_index_manifest` records the model, dimension, tasks and counts. For tables, the agent should query SQL using `gold_catalog`, not search the index.

## Review and sign-off

The dashboard writes `review_decisions` with columns `issue_id`, `decision` (accept / reject / override / sign_off), `override_field`, `override_value`, `reviewer`, `decided_at` and `comment`. The next run applies them:
- a rejected issue drops out of the A1 export;
- an override becomes a correction with `proposed_by = <reviewer>`;
- a `sign_off` with `override_value = 2025` publishes the 2025 exports, as long as no later decision exists.

Exports go to `Files/exports/draft/` or `Files/exports/published/`.

## Self-check (dev keys)

`gold_run_quality` scores each run on the public dev keys. Results at the time of writing:

| Check | Score |
|---|---|
| A1 2023–2024 | 95.8 (F1 0.96) |
| A2 2023 | 97.2 |
| A2 2024 | 90.7 |

For comparison, the package's own baselines score 52.2 (A1) and 25.5 / 23.2 (A2). The main remaining errors:
- `soil_misreport` recall is 0.70, limited by the soil map's accuracy;
- Scope 2 market-based depends on a few MWh of estimate noise at sites with no GoO cover.

## Known limitations

- The soil map is about 88 % accurate. Organic-soil emissions, about half of farm emissions, carry that uncertainty.
- Meter estimates have about 1.5 % error (backtested). Flagged and estimated tCO2e are reported per category in `gold_inventory_summary`.
- The commuting survey exists only for 2025. Like the reference method, earlier years use it with that year's headcount.
- In 2022, ERP capex (13.2 M€) does not match `capex_projects.csv` (3.5 M€). There is no reconciliation rule for that yet; 2025 matches exactly.
