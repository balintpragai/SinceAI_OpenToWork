# Record-level emission line items, reconciled against the reference calculator

The challenge ships a reference GHG calculator (`tools/ccn_tools/reference_calculator.py`) that implements the hidden-truth method, but it aggregates immediately (`groupby` site × carrier, material × supplier, …) and keeps only a free-text `basis`, so its output cannot be traced to source records. Traceability is 25 % of the jury score (`docs/TASKS_AND_SCORING.md`, "Jury rubric"), so we compute our own **emission line items**, one per source record × emission factor, carrying record key, factor and factor source. Every pipeline run also feeds our canonical tables to `compute_inventory` and asserts that our line items sum to its result within rounding. The three non-linear steps (GoO cap `min(mwh, goo)`, commuting survey mean × headcount, PCF selection per supplier × material) are allocated back to records proportionally to activity, and the allocation method is logged.

## Considered Options

- **Use the reference calculator directly.** Correct numbers, almost no effort, but no record-level lineage: rejected because the audit trail is the point of the solution.
- **Reimplement without reconciliation.** Rejected: silent method drift would cost A2 points and we would not notice.
