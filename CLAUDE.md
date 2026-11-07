# Climate & Nature Navigator — Claude notes

**Read `AGENTS.md` first. Its data-file rules are mandatory: ask before reading any file, per file.**
Project plan: `.scratch/part1-pipeline/spec.md` (Part 1 pipeline), `GLOSSARY.md`, `docs/adr/`.

## Parts
- **Part 1 — pipeline** (teammates): raw package → Delta lakehouse (Bronze, S1–S4, Gold). No LLM inside.
- **Part 2 — Gemini agent** (this folder: `copilot/`, `server.py`, `web/`, `answer_e.py`).
- **Part 3 — dashboard / review decisions**: owner not decided yet (goal G7 pending).

## Part 2 goals (approved 2026-11-06)
- G1 Read-only SQL (DuckDB) over Gold Delta tables, catalog in the prompt; raw CSVs registered as fallback.
- G2 Trace derived keys (`eli:{n}`, canonical keys) through the lineage table to raw records.
- G3 Chunk-level citations via the pipeline's doc index (`gemini-embedding-001`); in-prompt docs + keyword search when no index.
- G4 Every inventory figure states flagged share, estimate share and draft/published status.
- G5 E answers: batch drafts → human approval (one decision per answer) → export. Guardrails + audit log.
- G6 Package path per spec (`.tmp/...`), Docker agent-harness container last.

## Interface with Part 1 (confirm with the pipeline team)
- Lakehouse: `LAKEHOUSE_DIR` (default `./lakehouse`), Delta tables in `Tables/<name>/`.
- Gold table names live in one place: `copilot/gold.py` `GOLD` (emission_line_items, issue_log, correction_log,
  lineage, review_decisions, catalog, run_quality, doc_index). Columns follow the spec.
- Package: `CCN_ROOT`, else `.tmp/Apetit_SinceAI2026/.../APETIT_CLIMATE_NATURE_NAVIGATOR_2026/`, else a sibling folder.

## Run
- Backend: `python3 -m uvicorn server:app --port 8000` (`COPILOT_FAKE=1` = scripted model, no Gemini quota).
- Frontend: `cd web && npm run dev` → http://localhost:5173.
- Secrets: `GEMINI_API_KEY` in `.env` (gitignored). Free tier is 20 requests/day/model: enable billing for real use.
