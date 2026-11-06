# Climate & Nature Navigator

Our solution to the Apetit × Since AI 2026 challenge (tracks A and E): a data pipeline, an agent harness and a dashboard that turn raw climate data into a traceable GHG inventory. Domain terms from the challenge package itself (Scope 1/2/3, GoO, PCF, FLAG, …) are defined in the package's `docs/GLOSSARY.md`; this file only holds our own language.

## Records and traceability

**Source record**:
One row (or one JSON document) in a source file of the challenge package, exactly as delivered.
_Avoid_: raw row, input line

**Record key**:
The stable identifier of a source record, in the format the challenge defines (e.g. `erp:{doc_no}:{line_no}`, `energy:{site_id}:{YYYY-MM}:{carrier}`).
_Avoid_: row id, primary key, record id

**Derived record**:
A record built by the pipeline from one or more source records (e.g. a year's fuel energy from deliveries minus stock change). It has its own key and is linked to its source records through lineage.
_Avoid_: aggregate row, computed row

**Lineage**:
The chain linking any value back to the record keys, source file and row it was derived from.
_Avoid_: provenance (when meaning per-value links), audit trail (the audit trail is lineage plus the issue log)

**Stage snapshot**:
The stored state of the data at the output of one pipeline stage, kept so a record can be inspected as it looked at every stage.
_Avoid_: checkpoint, intermediate table

## Data quality

**Issue**:
A data-quality problem detected on a source record, classified with exactly one of the challenge's issue types (e.g. `unit_error`, `duplicate_record`).
_Avoid_: error, defect, incorrection, anomaly

**Legitimate oddity**:
A source record that looks wrong but is valid, such as credit notes, vessel lots in tonnes, seasonal meter peaks or ammonia systems. It is never raised as an issue.
_Avoid_: false positive, edge case

**Normalisation**:
A legitimate conversion of a valid value into canonical form (tonnes to kg, SEK to EUR, decimal comma to point, Swedish headers to English). It resolves no issue.
_Avoid_: correction, cleaning, standardisation fix

**Correction**:
A value change that resolves an issue, logged with old value, new value, rule and reason. It is applied automatically by a rule, or comes from a reviewer's review decision.
_Avoid_: fix, cleaning, repair

**Estimate**:
A value the pipeline creates where a source record or value is missing or unusable (a meter gap, a meter spike, a missing transport leg, a non-respondent farm). It is derived from other records, always marked as an estimate, and logged like a correction but without a trusted old value.
_Avoid_: imputation, interpolation (those are methods, not the thing), fill

**Flagged issue**:
An issue that cannot be corrected automatically. The record continues through the pipeline with its original values and the issue stays visible.
_Avoid_: incorrection, warning, open error

## Contract farming

**Organic share**:
The fraction of a farm's area under one crop in one year that lies on organic soil according to the soil map. It sets the farm's organic-soil emissions, regardless of what the farmer reported.
_Avoid_: soil type (self-reported), organic flag

**Organisational boundary**:
The sites and periods whose emissions belong in the inventory (e.g. Foodhills operations only from December 2025). Outside it, a missing record is not an issue and gets no estimate.
_Avoid_: scope (that word means Scope 1/2/3), perimeter

## Inventory and review

**Emission line item**:
The emissions attributed to one source record through one emission factor, carrying its record key, factor and factor source. Every inventory figure is a sum of emission line items.
_Avoid_: emission row, calculation result

**Flagged share**:
The part of an inventory figure (tCO2e) that comes from records with a flagged issue.
_Avoid_: uncertainty, error margin

**Review decision**:
An expert's verdict on a correction or flagged issue: accept, reject, or override with a new value.
_Avoid_: approval (when meaning the record), feedback

**Sign-off**:
The expert act that turns a draft inventory into a published one. Until sign-off, every inventory figure is a draft.
_Avoid_: approval, release, publish
