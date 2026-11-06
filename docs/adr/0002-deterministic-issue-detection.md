# Deterministic issue detection, no LLM in the pipeline

Issue detection (task A1) uses only rules and statistical checks: one or more per issue type, each with a `rule_id`, a confidence and an evidence note. No LLM runs inside the data pipeline. We chose this because every correction must be reproducible from bronze plus the logged corrections and review decisions (`docs/AZURE_FABRIC_QUICKSTART.md`, "Audit trail pattern"), and an LLM call can give a different answer on the next run. The Gemini agent (Part 2) explains issues and helps reviewers, but it does not create them.

## Consequences

- The rule catalogue that each run generates is the complete list of what the pipeline can detect, and it is indexed for the agent.
- Issue types that are hard to catch with rules (e.g. `material_mismatch`) may get lower recall. We accept that for reproducibility.
