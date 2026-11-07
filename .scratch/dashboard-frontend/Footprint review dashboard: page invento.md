Footprint review dashboard: page inventory for the React frontend
Status: needs-triage

This describes every visualization and element of the current dashboard (dashboard/index.html), the data each one reads, and how it behaves. Use it to rebuild the page as a React frontend service. The current page is a single-file reference implementation with no framework; match its behaviour, not its code.

1. Data the page reads
python -m pipeline run writes the data to dashboard/data/ (code: pipeline/dashboard_json.py). Every file has the same envelope:

{ "schema": "ccn-dashboard/1", "kind": "run|inventory|issues|records", "run": { "run_id", "git_commit", "inputs_sha256", "started", "generated_at" }, "data": { ... } }

Reject any file whose schema is not ccn-dashboard/1.

File	Size	Load	data contains
run.json	small	at start	stages[], sources[], rules[], coverage, reference_check[], quality[], boundary[], reviews[], normalisations{}, unattributed_note
inventory.json	small	at start	years[], dev_years[], rows[], bridges[], as_recorded_available
issues.json	~1.5 MB	at start	issues[], missed[], line_columns[], rules[]
records/<source>.json	5 kB – 41 MB	on demand, one source at a time	source, file, description, columns[], normalisation, line_columns[], record_format{}, records[]
There are 37 record files. parcel_crop_history_and_plan.json alone is 41 MB with 284k records. Load record files lazily, and page or virtualise their tables. Never load them at start.

Key shapes
Inventory row (inventory.rows[]): {year, scope, category, t, t0, key, flagged_t, estimated_t, flag_t, lines}

t = tCO2e after the pipeline. t0 = tCO2e as recorded (the same calculation on the data before any fix). key = dev answer key, only for dev_years (2023, 2024), otherwise null.
Scope totals are rows with scope: "total" and category set to one of scope1_total, scope2_location_total, scope2_market_total, scope3_total.
Bridge (inventory.bridges[]): {year, scope, steps: [{type, dt, issues}]}. The steps are sorted by |dt|, largest first. A step whose type starts with ( is not an issue type: it is "(allocation / side effect)", explained by run.unattributed_note. Recorded total + sum of the dt values = total after the pipeline, exactly.

Issue (issues.issues[]):

id, table, record_key, year, type, rule, action (correct|estimate|method|flag), confidence (0–1),
field, observed, proposed, evidence, drop, status (open|auto_applied|accepted|overridden|rejected), reviewer,
effect: {dt, by: {"scope|category": dt}, shared_with},
dev: null | {in_key, type_match, key_types[], true_value, note},
trace: {raw:{file,row,sha256}, bronze:{value,row{}}, s1:{value,changes{}}, s2:{rule,evidence,confidence,observed,proposed},
        s3:{changes[],excluded,estimate,flagged}, s4:{status,links[[table,derived_key|null]]},
        gold:{t,t0,by{},lines[],lines0[]} | null}

gold.lines / lines0 are arrays in line_columns order: scope, category, line_item, component, activity_value, activity_unit, factor_id, factor_value, factor_unit, basis, allocation, tco2e. lines = after the pipeline, lines0 = as recorded.
effect.dt can be 0 (flag-only, method note, no emissions) or null (as-recorded calculation unavailable).
Missed issue (issues.missed[]): dev-key rows the pipeline did not catch: {table, record_key, issue_type, year, field, true_value, observed_value, note, record_found, gold}.

Record (records/<source>.json → records[]): compact. Each file explains the format in record_format.

Always present: key and s4: {status, links?}.
row, origin ("estimate"), year, bronze (array in columns order), s1, s2 (issue ids), s3, gold and values appear only when they have content. An absent field means "nothing happened at this stage".
s4.status is one of in, excluded, outside_boundary, direct.
Source stats (run.sources[]): {source, file, description, sha256, bytes, columns, records, s1_changed, issues, corrected, excluded, estimated, flagged, outside_boundary, in_s4, with_gold, t, t0}.

Stage (run.stages[]): {id, name, what, inputs[], outputs[], tables[{table,rows,columns}], counts{}}. The keys in counts differ per stage:

raw: files, bytes
bronze: tables, records
s1: records_changed, normalised_sources
s2: issues, rules, by_type{}
s3: corrections, by_kind{}, excluded, estimated, flagged, status{}, review_decisions
s4: canonical_tables, lineage_links, outside_boundary, rows{}
gold: line_items, reference_check_ok, years[]
Coverage (run.coverage): tables[], types[], unchecked_types[{type,label}], rules[[type,table]], key_labels[[type,table,count]].

Writing back: review decisions
The page does not write to the lakehouse. It collects decisions, and the user downloads them as review_decisions.json: a list of objects with exactly these columns:

decision_id, issue_id (null for sign_off), decision (accept|reject|override|sign_off), override_field, override_value, reviewer, decided_at (ISO UTC), comment

The user then runs python -m pipeline review review_decisions.json followed by python -m pipeline run. A React service could replace this with an API endpoint that appends to the review_decisions Delta table. The column contract stays the same.

2. Global state and conventions
State
Year: one of inventory.years (2021–2025). Default 2024. Years in dev_years are labelled "·key".
Scope: scope1, scope2_location, scope2_market or scope3. Default scope1.
Issue filters: matrix cell (type|table), bridge step (issue type, within the selected scope), status, free-text search over record key, type, table and evidence. A matrix cell replaces the bridge-step filter.
Selections: the selected issue, the open pipeline stage, the open source in the explorer, the selected record, and a page number for each table.
Decisions: keyed by issue id, persisted per browser. Reviewer name, persisted.
URL parameters: year, sel (issue id; also sets the year), stage, scope, src, rec. Keep these as deep links in React routing.
Effective status = the local decision's status if one exists (accept → accepted, reject → rejected, override → overridden), otherwise issue.status. Every view uses the effective status.

Issue → scope = the scope with the largest |dt| in effect.by. Issues with no effect have no scope.

Status colours
These are validated for colour-blind separation in the adjacent order below (the progress-bar order). Keep both the order and the values.

Status	Label	Light	Dark
open	Open · needs review	#b4407a	#d0619a
overridden	Overridden	#b07c00	#b8892a
accepted	Accepted	#2a78d6	#3987e5
auto_applied	Auto-applied	#16835f	#2fa77c
rejected	Rejected (neutral)	#8e9993	#6f7a74
Other semantic colours:

"As recorded" or a step that raises a total: orange #eb6834 / #d95926.
"After pipeline" or a step that lowers a total: the auto-applied green.
Dev key: ink colour, drawn as a diamond or a tick mark.
Unknown or not checked: a 45° hatch with a dashed outline.
Never rely on colour alone:

Open issues are drawn as rings; other statuses are filled dots.
Pills carry text.
Every chart has a legend and tooltips.
Number and scale rules
tCO2e values span 0.01 t to 17.5 Mt. All magnitude charts use log10 scales.
Scope tiles: 10 t – 100 Mt.
Bridges and the scatter: 0.1 t – 100 Mt.
The issue glyph scales to its own two values.
Negative changes are plotted by their absolute size, with sign shown by colour and a −/+ in the label.
null means unknown: show "unknown" or a hatched bar, never 0.
Format thousands with separators and use whole tonnes in summaries. Line-item tables show up to 3–4 decimals.
3. Page elements, top to bottom
3.1 Header
Title: "Footprint review".
Run badges from the run envelope and run.quality:
run id, git commit, inputs hash
reference check: ✓ "matches ccn_tools" or ✗ "mismatch", from stages[gold].counts.reference_check_ok
A1 dev F1 and score
A2 score for each dev year
Year selector: segmented control.
3.2 Scope tiles (4 dumbbells)
Data: for each scope, the total row for the selected year (t0, t, key).
Chart: a horizontal log axis (10 t – 100 Mt):
orange dot = as recorded
green dot = after pipeline
grey connecting line between them
hollow ink diamond = dev key, when present
Headline: t0 / t written as "21× overstated as recorded". If the ratio is within 0.5% of 1, show "no change". If either value is missing, show "ratio unknown".
Text: a legend with both values; "vs key ±x.xx%" in dev years; an open-issue count pill, using the issue → scope mapping.
Click: selects the scope (drives the bridge and the scope-filtered issue list).
Footnote: explains the log scale and what "as recorded" means.
3.3 Pipeline run (stage flow)
Seven stage cards in a row (2 columns on narrow screens), with arrows between them: Raw, Bronze, S1 Standardised, S2 Validated, S3 Corrected, S4 Canonical, Gold.

Each card shows a headline number, a unit and a sub-line:

Stage	Headline	Sub-line
Raw	files	MB
Bronze	records	tables
S1 Standardised	records normalised	sources
S2 Validated	issues	rules
S3 Corrected	changes	excluded · estimated
S4 Canonical	lineage links	outside boundary
Gold	line items	reference ✓/✗
Click a card to open a detail panel below the cards. The panel shows what, the inputs list, and the output tables with row counts (first 12, then "… n more"). It also shows a stage-specific chart; all are horizontal bar lists, label · bar · value:

Stage	Chart
Raw	bytes per file
Bronze	records per source (+ column count)
S1	records changed per source; expandable list of normalisation rules (run.normalisations)
S2	issues per type; expandable table of all rules (id, table, type, action, description)
S3	changes by kind; issue-status counts (status colours); per-source changes with "excl · est · flag" annotations
S4	rows per canonical table; organisational boundary table (site, from month, to month)
Gold	reference-check table for the selected year (scope, category, reference t, line-item t, diff, ✓/✗)
3.4 Review progress bar
Title: "{year} issues: N".
Bar: one segmented bar with segments in status order, sized by count and labelled "n Status". Click a segment to filter by that status (click again to clear); the other segments fade.
Right-hand text: "x decided in this browser".
3.5 Coverage matrix ("Where errors come from")
Grid: rows = error types, columns = source tables, for the selected year. Column headers are vertical text.

Columns: tables that have a rule, an issue, or a dev-key label.
Rows: coverage.types, then a second group "Not checked by any rule (suggestions)" from coverage.unchecked_types.
Cell states:

State	When	Look
Issues found	≥1 issue of that type in that table this year	filled with the most urgent effective status (open > overridden > accepted > auto > rejected); shows the count (cap at "99+"); clickable filter, toggles
Clean	a rule covers the cell, nothing found	soft tint with "·"
Key only	the dev key labels this cell, no rule covers it	orange outline with "!" (a known blind spot)
Missed	dev-key issues for this year the pipeline missed	orange ring, on top of any other state
Not checked	suggestion rows × tables that produce emissions (sources.with_gold > 0)	hatched
N/A	everything else	blank
Tooltips on every cell: type, table, count, status and missed count. Suggestion rows say "NOT CHECKED… Suggestion, not a finding."

Legends: two, one for status colours and one for cell states.

3.6 Impact × confidence scatter
Data: the year's issues after the matrix-cell, status and search filters, but not the scope/bridge-step filter.
Axes: x = |effect.dt| on a log scale (0.1 t – 100 Mt); y = confidence, from min(0.5, lowest confidence) to 100%.
No-effect strip: a column on the right labelled "no effect", separated by a dashed line, for issues where |dt| < 0.001 or dt is null. Jitter dots there by issue id so they don't stack.
Marks: colour = effective status; open issues are rings. The selected issue gets a thick ink outline and is drawn on top.
Hover: tooltip with record key, type · table, effect, confidence and status.
Click: selects the issue.
Caption: how to read it: bottom-right is where a human check matters most.
3.7 Bridge: as recorded → after pipeline (selected year × scope)
Rows:
"As recorded" (orange)
one row per bridges.steps entry, labelled "type (n issues)"; green if dt < 0, orange if > 0
"After pipeline" (green)
Bars: log length (0.1 t – 100 Mt), with the signed value on the right. Unknown values get a hatched full-width bar. The "After pipeline" row has a vertical ink tick at the dev-key value.
Click a step to filter the issue list by that type within the scope (toggles).
Side-effect note: shown when a (allocation / side effect) step exists, using unattributed_note.
By-category table below: one row per inventory row for the year × scope.
An inline log-scale dumbbell: recorded dot, after dot, key tick.
Columns: recorded, after, key, flagged t, estimated t.
3.8 Issue list
Title: count and a description of the active filters. Text search box; "Clear filters" button.
Columns:
record key (monospace)
type + table
effect (signed t)
confidence %
status pill
dev-key mark: "✓ key" (confirmed), "≈ other type" (record in the key with a different type), "✗ not in key" (possible false positive), "—" (no key that year)
Sorting: by |effect.dt|, largest first. 15 rows per page with Prev/Next.
Click a row to select the issue.
3.9 Issue detail (full trace)
Placeholder when nothing is selected: "Select an issue in the matrix, scatter, bridge or list…". With an issue selected, it shows, in order:

Header: record key, status pill, table, source file + row, issue id.

What's wrong: type, field, action (Correct / Estimate / Method note / Flag only), rule id.

Before/after glyph:

If observed and proposed are both positive numbers: two bars on a log scale scaled to the pair (orange observed, green proposed), labelled with the factor (÷1,000, ×10, or the exact ratio).
Otherwise: text observed → proposed, or "record excluded" when drop.
Known issue: for action: flag the glyph reads like a change even though nothing changed (e.g. farm_survey:FS01297, area 13.1 → 8.19 proposed). In React, show flag-only issues as "Not changed · suggested value", and say when the calculation already uses another source (area_mismatch: the footprint uses the declared parcel area).
Pipeline trace strip: seven boxes, one per stage. The record view (3.11) reuses it.

Box	Shows
Raw	file name, row, SHA-12; orange border, tag "error enters"
Bronze	field name + raw value
S1	normalised value if S1 changed the field, else "unchanged" / "n fields normalised"
S2	rule id, confidence; pink border, tag "caught"
S3	each correction field: old → new (kind · status), "excluded", or "flagged, value kept"; green border, tag "fixed" when something changed
S4	status (in / excluded / outside boundary / direct), up to 3 links table ← derived_key
Gold	t0 → t tonnes, line-item count, or "no direct emissions"
Boxes where nothing happened are dimmed.

Evidence: the rule's evidence text.

Effect on the inventory: signed total, plus a breakdown by scope · category. When the record has several issues, note "record has N issues; its change is split equally".

Dev key verdict: confirmed (with true value and note), different type, not in key, or no key for that year.

Expandable "Source row and line items":

Bronze row as a key/value table, with the flagged field marked.
Line-item tables "Gold as recorded" and "Gold after pipeline": scope · category · component, activity, factor value + unit + id + basis + allocation, tCO2e. First 12 rows.
Review panel:

If decided locally: decision, reviewer, time, override and comment, plus Undo.
Otherwise: a status-specific prompt, a comment input, and Accept / Reject / Override buttons, with an override-value input for field.
Rejecting or overriding requires a comment; overriding requires a value. The first decision asks for the reviewer's name.
3.10 Missed by the pipeline (dev years only)
Title: "In the dev key, missed by the pipeline", with the count for the year.
Table: record key + table, type, field, observed → true value, note, the record's current tCO2e.
Caption: these errors are still in the "after pipeline" total.
Empty state: "None. Every labelled error was found."
3.11 Record explorer ("All data: every record through every stage")
Source list: one row per run.sources, sorted by record count.
Name, record count, tCO2e.
A stacked bar with width proportional to √records. Segments: S1 normalised (blue), issues (pink), excluded (grey), estimated (amber), outside boundary (dark grey), untouched (tint).
Issue count.
Click to load records/<source>.json; click again to close. Show a loading state.
Source panel:
File path, description, S1 normalisation rule, emissions recorded → after (all years).
Stage funnel (horizontal bars): Bronze rows read, S1 normalised, S2 issues, S3 changed, S3 excluded, S3 estimated, S4 linked, S4 outside boundary, Gold with emissions.
Filter dropdown: All, Normalised in S1, Has issue, Changed in S3, Excluded, Estimated, Flagged, Outside boundary, Has emissions. Plus a key search box and a result count.
Records table: key, the first 5 Bronze columns ("(estimate)" for estimated rows), and a strip of stage chips S1 S2 S3 S4 G, each lit when something happened at that stage. 50 per page.
Record detail:
The same trace strip as 3.9, without "error enters" or "caught" tags.
Links to its issues; clicking one jumps to that issue's year and selects it.
S1 changed fields.
Bronze row as a key/value table (or the estimated row as JSON).
Gold totals by scope · category (as recorded → after) and the line-item table.
3.12 Review log
Header:
The reviewer's name.
A "Sign off {year}" button, which records a sign_off decision with override_value = year and shows the open count as a warning.
"Download review_decisions.json" (disabled when empty).
Help line: the two CLI commands that apply the decisions.
Timeline of local decisions, newest first: decision, record link (jumps to the issue), type, override, comment, reviewer, time.
Expandable table of decisions the pipeline has already applied (run.reviews).
4. Interaction map
Action	Effect
Year change	resets the cell, step, status and selection filters and the issue page
Scope tile click	sets scope; resets the bridge step
Stage card click	toggles the stage detail panel
Progress segment click	toggles the status filter (list, scatter, matrix colours stay)
Matrix cell click	toggles the cell filter (overrides the bridge step)
Bridge step click	toggles the type filter within the scope; clears the cell filter
Scatter dot / list row click	selects the issue → detail panel
Record issue link / log link	jumps to that issue (changes year, clears filters, scrolls to detail)
Accept / Reject / Override / Undo / Sign off	updates the local decisions → every status colour, count and pill updates immediately
5. Layout and states
Max content width about 1240 px.
Two-column pairs: matrix | scatter, and issue list | issue detail (about 1 : 1.25). These collapse to one column below 900 px. The stage flow and trace strip become 2-column grids below 900 px.
No horizontal page scroll at phone width. Wide tables and the matrix scroll inside their cards.
Light and dark themes, each with its own colour values (see §2).
States to design:
loading (initial and per source)
load error (explain how to serve or generate the data)
empty filters ("No issues match.")
no dev key for the year
as-recorded unavailable (inventory.as_recorded_available = false → every t0 is unknown)
Accessibility:
Every SVG has role="img" and an aria-label summarising it.
Tooltips duplicate the visual encodings.
Tables exist next to the charts (by-category, missed, reference check).