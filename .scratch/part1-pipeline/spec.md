# Part 1: Data processing pipeline

Status: needs-triage

Part 1 of our Climate & Nature Navigator solution (Apetit × Since AI 2026). It turns the raw challenge package into traceable Delta tables. These feed task A1 (data-quality issues), task A2 (2025 GHG inventory), the Gemini agent (Part 2) and the dashboard (Part 3).

Vocabulary follows [GLOSSARY.md](../../GLOSSARY.md). Decisions: [ADR 0001](../../docs/adr/0001-record-level-emission-line-items.md), [ADR 0002](../../docs/adr/0002-deterministic-issue-detection.md), [ADR 0003](../../docs/adr/0003-organic-share-from-soil-map.md).

`PKG` = `.tmp/Apetit_SinceAI2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026/`

## Why

The jury weighs traceability and expert review at 25 %, usefulness at 30 % and reliability at 10 % (source: `PKG/docs/TASKS_AND_SCORING.md`, "Jury rubric"). A2 requires that every number traces to source records, every correction is logged with its reason, and every factor is recorded with its source (source: same file, "A2: 2025 inventory").

## Scope

**In:**
- `PKG/data/01_master`, `02_raw_feeds` (incl. `supplier_pcfs/*.json`), `03_farming`, all of `05_scenarios`, `07_frameworks`;
- `PKG/tasks/dev` (answer keys for self-check) and `PKG/tasks/templates` (export formats).

**Out:**
- `00_apetit_original`: a sample left from data generation.
- `04_climate` and `06_nature`.
- The challenge brief PDF, which is also not indexed.

**Years:** every year present in the inputs. 2025 is the submission year.

## Stages

Every run reprocesses everything from Raw, deterministically, with one command (`python -m pipeline run`). There is no orchestrator.

| Stage | What it does | Stored as |
|---|---|---|
| **Raw** | Byte copy of each source file, plus a file hash | Lakehouse `Files/` |
| **Bronze** | Parsed and typed, record key assigned, no values changed | Full table per source |
| **S1 Standardised** | Normalisations: units to kg/MWh/m³, currency to EUR (`factors.FX_PER_EUR`), decimal comma, Swedish headers/values (`foodhills_odlingsdata_se.csv`) | Full table per source |
| **S2 Validated** | Issue detection only; no values change | **Issue log** only (record state "as validated" = S1 ⨝ issue log) |
| **S3 Corrected** | Corrections and estimates applied; flagged issues pass through unchanged; review decisions applied | Full table per source + **correction log** |
| **S4 Canonical** | Reshape into the canonical tables of `PKG/docs/METHODOLOGY.md` §2 (energy = deliveries − stock change, GoO validated against registry, farm footprints, …) | Full table per canonical table |
| **Gold** | Reference tables, emission line items, exports, run quality, catalog | See below |

Record keys follow `PKG/docs/TASKS_AND_SCORING.md`, A1 "Record keys". Each derived record gets its own stable key, for example `energy:S-SAK:2025:diesel` for a canonical row and `eli:{n}` for an emission line item.

**Lineage table:** `(derived_key, source_key, stage, run_id)`. It covers every derived record at S4 and in Gold. We use no array columns, because Gemini queries through SQL.

## Issues (A1)

Detection uses rules and statistical checks only, with no LLM (ADR 0002). Each detection carries `rule_id`, `issue_type` (exact strings from `TASKS_AND_SCORING.md`, "ISSUE_TYPES"), `confidence` and `evidence`.

Legitimate oddities are never raised: credit notes (movement 122), `uom = TO` vessel lots, seasonal meter peaks, and ammonia systems (source: `TASKS_AND_SCORING.md`, A1).

| Action | Issue types |
|---|---|
| **Correct** | `duplicate_record` (drop the later row), `unit_error`, `decimal_shift`, `currency_error`, `pcf_unit_error`, `coordinate_swap`, `wrong_gas_code` (when the system history shows the right gas), `certificate_mismatch` (the registry is authoritative), `pcf_stale_period` (fall back to the material default factor), `total_mismatch` (recompute from components) |
| **Estimate** | `missing_record` and `meter_spike` (seasonal profile method), `missing_leg` (see below) |
| **Correct (method)** | `soil_misreport`: raised where organic share ≥ 30 % and the survey says "Mineral soil"; emissions come from the organic share for every farm anyway (ADR 0003) |
| **Correct** (changed during build, see Comments) | `material_mismatch` (material taken from the ERP text), `mode_mislabel` (label mapped to the survey code) |
| **Flag only** | `outlier_implausible`, `area_mismatch` |

**Seasonal profile method** (meter gaps and spikes):

  `estimate(month m) = Σ(this year's available months) × share of month m in this site × carrier's earlier complete years`

If no complete earlier year exists, use the mean of the neighbouring months, with lower confidence. Detection must tell a spike, which is far outside the site's own profile for that month, apart from a seasonal peak. E10 expects meter spikes to be corrected (source: `PKG/tasks/E_questions.csv`, E10).

**Missing transport leg:** tonnes from the ERP document. km = the median km of the same mode for lots from the same origin country in the same year, falling back to all years. tkm = t × km. The result is marked as an estimate.

**Organisational boundary:** no estimate outside it, based on `structural_events.csv` and `sites.in_group_from/to`. For example, Foodhills operations count only from Dec 2025 (source: `PKG/docs/METHODOLOGY.md` §1).

**Flagged issues** keep their original values. Every Gold figure carries its **flagged share**.

## Correction log

Fields follow `PKG/docs/AZURE_FABRIC_QUICKSTART.md`, "Audit trail pattern": `record_key, field, old_value, new_value, rule_or_model, evidence, proposed_by, approved_by, timestamp`. Added fields:
- `kind`: correction, estimate or method;
- `status`: `auto_applied`, or the review outcome;
- `run_id`.

Estimates have no trusted old value.

## Contract-farm footprint

Following `PKG/docs/METHODOLOGY.md` §5, not the simplified `io.naive_farm_footprints`:

- **Per-hectare footprint:** the formulas of `PKG/tools/ccn_tools/farm_calculator.py`. The organic-soil term is weighted by the **organic share** from `parcels.soil_class_soilmap` × `parcel_crop_history`, not taken as a yes/no from the survey (ADR 0003).
- **Farm emissions:** per-hectare footprint × the crop's **declared parcel area** from `parcel_crop_history`, not the survey `area_ha`.
- **Allocation:** divided by **delivered kg** from ERP. Intake rejections stay with the delivered product.
- **Farms that didn't answer the survey:** estimated with the crop-year median of respondents' management inputs, together with each farm's own organic share.
- **Breakdown:** a `component` column (fertiliser, direct N2O, indirect N2O, organic soil, diesel, lime, pesticides, electricity), plus the FLAG part.
- **Swedish farms:** not in the 2025 inventory (source: `METHODOLOGY.md` §1).

## Gold

- **Reference tables:** site, material, supplier, farm, parcel, emission factor (with `reference_source`, `value_status`), period.
- **Emission line items:** one per source record × factor. Columns include:
  - `tco2e`, `flag_tco2e`, `biogenic_co2_t`, `component`;
  - `activity_value`, `activity_unit`;
  - `scope`, `category`, `ef_id`, factor source;
  - `is_estimate`, `flagged`.
  This level of detail is needed for E06, E07, E09, E10, E11, E15 and E16 (source: `PKG/tasks/E_questions.csv`).
- **Exports:**
  - A1 submission: 2025 issues, minus those a reviewer rejected.
  - A2 inventory: the categories in `PKG/tools/ccn_tools/score.py` `A2_WEIGHTS`.
  - Both stamped `draft` / `published` according to sign-off.
- **Run quality:** `score_a1` on the 2023–2024 dev labels, `score_a2` on the 2023 and 2024 dev inventories, plus the reference-check result.
- **Catalog:** table, column, description, unit and example. Generated from the schema definitions.

## Calculation and reference check

Our own record-level calculation (ADR 0001). On every run, `reference_calculator.compute_inventory` runs on our S4 tables. The sum of our emission line items must match it within rounding, or the run fails.

Three steps are not simple activity × factor. Their results are shared out in proportion to activity, and the method is logged:
- the GoO cap `min(mwh, goo)`;
- commuting (survey mean × headcount);
- PCF selection per supplier × material.

## Review

- The dashboard (Part 3) writes a **review decisions** table: accept, reject, or override with a value.
- The next run applies these decisions in S3. An override becomes a correction with `proposed_by = <person>`.
- **Sign-off** is recorded in the same table. Until then, every Gold figure is a draft.

## Index (for the Gemini agent)

- **Indexed:**
  - `PKG/data/07_frameworks/framework_digest.md`;
  - `PKG/docs/*.md`;
  - our `GLOSSARY.md`;
  - a **pipeline description**: a hand-written method note plus the per-run generated rule catalogue (rule_id, issue type, action, description) and the catalog descriptions.
- **Queried with SQL, not indexed:** the Gold tables, `source_registry.csv`.
- **Chunking:** split on Markdown headings. Each chunk carries `file`, `heading_path` and `chunk_id`, so answers can cite file and section.
- **Embeddings:** `gemini-embedding-001`. Stored as a Delta table with the model name and vector size. Part 2 must embed queries with the same model.

## Storage and runtime

- Delta Lake via `deltalake`, used with pandas. One Delta version per run, tagged with `run_id`, git commit and input file hashes.
- Code in this repo under `pipeline/`. The package location is set in config and mounted read-only. Only Raw reads from the package.
- Lakehouse layout follows Fabric: `Files/` for raw, `Tables/` for the rest (source: `PKG/docs/AZURE_FABRIC_QUICKSTART.md`).
- Docker: one container each for the pipeline, the lakehouse, the dashboard and the agent harness.

## Tests

- Every detection and correction rule has a small unit test with a hand-made example. One case where it fires, one legitimate oddity where it must not.
- The end-to-end check is the run quality table: dev-key scores plus the reference check.

## Build order

If time runs short, cut from the bottom.

1. Raw → S4, issue log, correction log, A1 export.
2. Emission line items, A2 export, reference check.
3. Self-check (run quality).
4. Index and pipeline description.
5. Docker and Azurite. Until then, a local folder laid out like a lakehouse.

## Tentative decisions

These are open to change based on dev-key results or later constraints:

- **Missing-leg distance method** (same-origin median km). Revisit after the A2 category 4 dev score.
- **Azurite as the lakehouse container.** Alternatives are a shared Docker volume or MinIO. Not yet certain.

## Comments

### 2026-11-07: build items 1-3 done

Built: Raw → S1 → S2 → S3 → S4 → Gold, record-level emission line items with the reference check, A1/A2 exports, and the self-check. See [pipeline/README.md](../../pipeline/README.md). 20 unit tests pass. Self-check: A1 95.8 (2023–24), A2 97.2 (2023) and 90.7 (2024); the reference check passes for 2021–2025.

Deviations from the spec, decided during the build:
- **`material_mismatch` and `mode_mislabel` are corrected, not flagged.** The ERP `material_text` names the right material unambiguously, and the commuting labels map one-to-one ('Car', 'henkilöauto', 'auto' → car; 'linja-auto' → bus). Both change category 1 and category 7 numbers, so leaving them uncorrected would bias A2.
- **Second currency rule (ERP-CUR-02).** Spend lines (uom EUR) from EUR suppliers can carry a SEK amount. They are detected at 7.5–25× the material's median amount.
- **Expected organic share for emissions** (ADR 0003 amendment): parcels mapped as clay with ≤ 10 % clay count as organic with p = 0.42, calibrated on the dev inventories. Detection still uses the soil map only.
- **The meter seasonal profile uses the median over complete years.** The mean let one year's spike distort the profile and missed two dev spikes.

Not built yet: item 4 (index; needs a Gemini API key for `gemini-embedding-001`) and item 5 (Docker + Azurite).

### 2026-11-07: build items 4-5 done

- **Index (item 4):** `gold_doc_chunks` and `gold_index_manifest`, 147 chunks, split on headings, each with a `[file > section]` citation prefix. Embedding with `gemini-embedding-001` (768-d, normalised, RETRIEVAL_DOCUMENT; content-hash cache) runs when `GEMINI_API_KEY` is set. **Not yet run against the real API: no key was available.** The request shape and caching are covered by unit tests with a fake transport. Indexed in addition to the spec: our ADRs and the generated table catalog.
- **Docker (item 5):** `Dockerfile` (pipeline), `docker-compose.yml` (lakehouse = Azurite, pipeline; agent and dashboard stubbed), `.env.example`. The storage layer (`pipeline/storage.py`) writes Delta straight to `az://` and uploads `Files/`. Verified against a local Azurite (Node), with results identical to a local run. **The Docker images themselves were not built: the Docker daemon was not running.** `docker compose config` validates, and every pinned dependency has a Linux wheel for Python 3.13.
- Review loop verified end to end with simulated dashboard decisions (reject, override, sign_off): A1 135 → 134 rows, the override logged with the reviewer as `proposed_by`, exports moved to `published/`.
- The 2022 capex gap is ticket [issues/01](issues/01-capex-2022-reconciliation.md).
- **2026-11-07, Docker verified:** `docker compose up -d lakehouse` plus `docker compose run --rm --build pipeline` (the README commands, run verbatim) build the image and run the pipeline against the Azurite container in about 25 s. Scores are identical to a local run, the reference check passes, and 25/25 tests pass inside the container. A second run reads the previous run's tables and appends a Delta version tagged with run_id and git commit. The host reads the same tables through `localhost:10010`.
