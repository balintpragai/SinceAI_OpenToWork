# Auditor exports

Status: ready-for-agent (approved 2026-11-07)

**Audience:** auditors.
- Exports are always allowed. Unapproved content is marked **DRAFT**, and approved content carries its approval.
- Exports only read data. The answer-sheet submission CSV (`POST /api/export`) is unchanged.

## Exports

| Where | Format | Route |
|---|---|---|
| Copilot answer (chat or answer sheet) | Excel evidence pack | `GET /api/export/answer.xlsx?thread_id=&answer_id=` or `?question_id=` |
| Copilot answer | PDF working paper (browser print) | data from `GET /api/export/answer?…` |
| Conversation | Excel | `GET /api/export/conversation.xlsx?thread_id=` |
| Audit log | Excel | `GET /api/export/audit.xlsx` |
| Dashboard chart | Excel | `GET /api/export/chart.xlsx?chart_id=&year=` |

**Evidence pack sheets:** Summary, Sources, Checks, Citations, and one `Data n <tool>` sheet per tabular tool result (at most 5,000 rows each).
- **Summary** holds the stamp, the question, the answer, the technical evidence, reviewer and time, model, content SHA-256 and the data-run stamp.
- **Checks** lists every tool call with its arguments (for example, the SQL text) and its duration.

## Stamps

- **Approval banner** on every sheet and every PDF page:
  - `APPROVED by X, date`
  - `APPROVED WITH EDITS by X, date`
  - `REJECTED by X, date – not for reliance`
  - `DRAFT – NOT APPROVED` (red sheet tabs in Excel; diagonal watermark in the PDF).
- **Data run:** from `gold_run_manifest`: run id, git commit, finish time, inputs SHA-256, number of input files, reference check, inventory sign-off status. With these, an auditor can reproduce the data behind an answer.
- **Content SHA-256** of the answer and its evidence. An edited copy no longer matches.
- **Synthetic-data disclaimer** on every sheet.

## Related fix

Chart payloads now carry `tables`, the real lakehouse tables, alongside the plain `sources` labels. Answer sources therefore name the file (`lakehouse: gold_…`) instead of repeating the label.

## Out of scope

- PowerPoint and Word.
- A dashboard board pack.

## Tests

`tests/test_export.py` uses a temporary store and checks that:
- the banner follows the decision (draft, approved, rejected);
- the expected sheets exist;
- the hash changes when the answer is edited;
- the audit export carries `tools_used` instead of the raw trace;
- missing answers raise an error.
