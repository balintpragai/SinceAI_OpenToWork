# Reconcile ERP capex lines with capex_projects (2022 gap)

Status: needs-triage

## Problem

ERP capex spend (materials M950/M951, `erp_purchase_lines`) does not match `capex_projects.csv` for some years. Source: run `run-20261106T221058Z-dc10ecab`, tables `s3_erp_purchase_lines` and `s3_capex_projects`.

| Year | ERP M950+M951 (EUR) | capex_projects (EUR) |
|---|---|---|
| 2021 | 4,423,355 | 7,519,462 |
| 2022 | 13,183,794 | 3,462,453 |
| 2023 | 2,812,369 | 2,812,369 |
| 2024 | 2,767,198 | 2,767,198 |
| 2025 | 10,326,256 | 10,326,256 |

2023–2025 match exactly, so the submission year is not affected. In 2022 one line alone, `erp:5100000008:10` (10.6 M€), is 36× the material median. That is above the 25× ceiling of rule ERP-CUR-02 (SEK booked as EUR), so the rule doesn't fire.

## To decide / do

- Add a reconciliation rule that compares ERP capex per year (and per `wbs_element` where present) with `capex_projects.csv`, and explains the difference: SEK booked as EUR, a duplicate posting, or a project missing from the list.
- Check whether a planted issue type applies (likely `currency_error` or `duplicate_record`), or whether the gap should only be a flagged issue.
- Category 2 carries 3 % of the A2 score. The years affected (2021, 2022) are not auto-scored, but they feed the base-year discussion in track B.

## Comments
