# 🥐 Croissant: Climate & Nature Navigator

**Our submission to Apetit's *Climate & Nature Navigator* challenge at the Since AI 2026 hackathon.**

Apetit's sustainability data comes from many places: ERP exports, energy meters, supplier carbon footprints, contract-farm surveys, soil maps and more. People spend hours chasing loose ends and checking which number is true. Croissant collects all of it in one place, cleans it in a way you can trace, and puts it on one dashboard with an AI co-pilot that answers questions and cites its sources.

**Link to the Demo:** https://youtu.be/ba2Bmh2JnSY

## What it does

| | |
|---|---|
| **Finds data-quality issues (task A1)** | Fixed rules, with no LLM involved, find duplicates, unit and decimal errors, wrong currencies, meter spikes, missing records, soil misreports and more. Normal quirks such as credit notes and seasonal peaks are left alone. |
| **Builds the 2025 GHG inventory (task A2)** | Every tCO2e figure is calculated per source record, and each figure can be traced back to the raw rows and emission factors behind it. Each run is checked against Apetit's reference calculator. |
| **Logs every change** | Each correction and estimate is logged with the old value, the new value, the rule that made the change and the evidence for it. Every figure shows how much of it is flagged or estimated, and whether it is a draft or published. |
| **Answers questions with an AI co-pilot** | A Qwen3.8-Flash-Next agent queries the data through read-only SQL, traces numbers back to the source records, and cites the document file and section for every claim. |
| **Keeps people in charge** | Reviewers accept, reject or override issues, approve the agent's draft answers one at a time, and sign off the inventory. Every decision goes into an audit log, and every output can be exported. |

### How we score on the public dev answer keys

| Check | Croissant | Package baseline |
|---|---|---|
| A1 issues, 2023–2024 | **95.8** (F1 0.96) | 52.2 |
| A2 inventory, 2023 | **97.2** | 25.5 |
| A2 inventory, 2024 | **90.7** | 23.2 |

The pipeline scores itself on every run and stores the result in the `gold_run_quality` table. Known limitations are listed in [pipeline/README.md](pipeline/README.md#known-limitations).

## How it is built

```
Challenge package ──► Part 1: Pipeline ──► Delta lakehouse ──► Part 2: featherless.ai co-pilot ─┐
 (read-only)          Raw → Bronze → S1      (Fabric layout:     (SQL, lineage, citations) ├─► Web app
                      → S2 → S3 → S4 → Gold   Tables/ + Files/)   Part 3: Dashboard + review┘
```

- **Part 1, the pipeline** ([pipeline/](pipeline/)): Python, pandas and Delta Lake. One command reprocesses everything from the raw files to Gold in about 20 seconds. The output uses the Microsoft Fabric lakehouse layout (`Tables/` and `Files/`), the same stack Apetit uses.
- **Part 2, the co-pilot** ([copilot/](copilot/), [server.py](server.py)): a FastAPI backend with a QWEN agent that queries the Gold tables with DuckDB, follows the lineage table, and searches the document index (`gemini-embedding-001`).
- **Part 3, the web app** ([web/](web/)): React and TypeScript, with five views: Dashboard, Data review, Ask, Answer sheet and Audit log.

Further reading: [pipeline/README.md](pipeline/README.md) explains the stages and rules, [GLOSSARY.md](GLOSSARY.md) defines our terms, and [docs/adr/](docs/adr/) records our design decisions.

## Start guide

### 1. What you need

- **Python 3.13** and **Node.js 22**, or **Docker** for the web app (see option B).
- **The challenge package** from Apetit. It is not in this repo. Unzip it so that this folder exists:
  ```
  .tmp/Apetit_SinceAI2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026/
  ```
  If you keep it somewhere else, set `CCN_PACKAGE_ROOT` (for the pipeline) and `CCN_ROOT` (for the web app) to that folder.
- **A Featherless.ai API key** (optional). Without one, run in **fake mode**: the co-pilot gives scripted answers and everything else works the same. The free tier allows only 20 requests per day per model.

```bash
git clone https://github.com/balintpragai/SinceAI_OpenToWork.git
cd SinceAI_OpenToWork
cp .env.example .env        # optional: add GEMINI_API_KEY=... here
```

### 2. Build the lakehouse (run the pipeline)

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-web.txt     # Windows: .venv\Scripts\pip
.venv/bin/python -m pipeline run                                       # Windows: .venv\Scripts\python
```

This writes the Delta tables to `./lakehouse/` and prints the self-check scores. It exits with an error if the reference check fails. Optionally, run the unit tests with `.venv/bin/python -m pytest`.

### 3. Start the app

**Option A: run locally** (two terminals)

```bash
# Terminal 1: backend on :8000 (remove COPILOT_FAKE=1 to use Qwen3.8-Flash-Next)
COPILOT_FAKE=1 .venv/bin/python -m uvicorn server:app --port 8000
# Windows PowerShell:  $env:COPILOT_FAKE="1"; .venv\Scripts\python -m uvicorn server:app --port 8000

# Terminal 2: frontend
cd web
npm install
npm run dev
```

Open **http://localhost:5173**.

**Option B: Docker** (after step 2)

```bash
COPILOT_FAKE=1 docker compose up -d --build web     # leave out COPILOT_FAKE=1 to use the key in .env
```

Open **http://localhost:8080**. The container reads `./lakehouse` and the challenge package as read-only, and writes drafts and the audit log to a Docker volume.

### 4. Things to try

1. **Dashboard**: the 2025 inventory by scope and category, with the flagged and estimated share of each figure.
2. **Ask**: ask a question about a chart, such as *"Why did Scope 2 change?"*. The answer shows the SQL it ran, the records it traced, and the documents it cited.
3. **Data review**: accept, reject or override the issues the pipeline found. Run the pipeline again and your decisions are applied.
4. **Answer sheet** and **Audit log**: approve the co-pilot's draft answers one at a time, export them, and see every decision that was recorded.

## Repository map

| Path | What is there |
|---|---|
| [pipeline/](pipeline/) | Part 1: the raw package to Gold Delta tables, issue rules, emission calculation, document index |
| [copilot/](copilot/), [server.py](server.py), [answer_e.py](answer_e.py) | Part 2: the Featherless.ai agent, its tools, guardrails, review and export |
| [web/](web/) | Part 3: the React web app |
| [tests/](tests/) | Unit tests for rules, emissions, index, dashboard and export |
| [docs/adr/](docs/adr/), [GLOSSARY.md](GLOSSARY.md) | Design decisions and vocabulary |
| [docker-compose.yml](docker-compose.yml) | Containers for the lakehouse (Azurite, standing in for Fabric OneLake), the pipeline and the web app |
