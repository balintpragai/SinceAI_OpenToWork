// Footprint review: data, plain-language wording and the review-decision store.
// Reads the pipeline's dashboard export (pipeline/dashboard_json.py, schema ccn-dashboard/1) through /api/footprint/*.
import { useCallback, useState } from 'react'
import { api } from './api'
import { lsGet, lsSet } from './app'

// ---- data shapes (only the fields this view reads) -------------------------------------------
export type IssueStatus = 'open' | 'auto_applied' | 'accepted' | 'overridden' | 'rejected'
export type Change = { issue_id: string; kind: string; field: string | null; old_value: unknown; new_value: unknown; status: string }
export type Trace = {
  raw: { file: string; row: number | null; sha256: string | null }
  bronze: { value: unknown; row: Record<string, unknown> | null }
  s1: { value: unknown; changes: Record<string, unknown> | null }
  s3: { changes: Change[]; excluded: boolean; estimate: boolean; flagged: boolean } | null
  s4: { status: string; links?: [string, string | null][] } | null
  gold: { t: number | null; t0: number | null; lines: unknown[][]; lines0?: unknown[][] } | null
}
export type Issue = {
  id: string; table: string; record_key: string; year: number | null; type: string; rule: string
  action: 'correct' | 'estimate' | 'method' | 'flag'; confidence: number | null; field: string | null
  observed: unknown; proposed: unknown; evidence: string; drop: boolean | null; status: IssueStatus
  effect: { dt: number | null; by: Record<string, number>; shared_with: number }
  dev: null | { in_key: boolean; type_match: boolean; key_types: string[]; true_value: unknown; note: unknown }
  trace: Trace
}
type Stage = { id: string; name: string; counts: Record<string, any> }
export type RunData = {
  stages: Stage[]; sources: { source: string; description: string }[]
  rules: { rule: string; table: string; type: string; action: string; description: string }[]
  coverage?: { rules?: [string, string][] }; quality: { check: string; years: string; f1?: number; score?: number }[]
  reviews?: Record<string, string>[]
}
type InvRow = { year: number; scope: string; category: string; t: number | null; t0: number | null }
type Meta = { run_id: string; git_commit: string; inputs_sha256: string; generated_at?: string; started?: string }
type Envelope<T> = { schema: string; kind: string; run: Meta; data: T }
export type Footprint = {
  meta: Meta; run: RunData; inv: { years: number[]; dev_years: number[]; rows: InvRow[] }
  iss: { issues: Issue[]; line_columns: string[] }; byId: Map<string, Issue>
}

export async function loadFootprint(): Promise<Footprint> {
  const get = async <T,>(n: string) => {
    const e = await api<Envelope<T>>(`/api/footprint/${n}`)
    if (e.schema !== 'ccn-dashboard/1') throw new Error(`Unexpected schema ${e.schema} in ${n}.json`)
    return e
  }
  const [r, v, i] = await Promise.all([get<RunData>('run'), get<Footprint['inv']>('inventory'), get<Footprint['iss']>('issues')])
  return { meta: r.run, run: r.data, inv: v.data, iss: i.data, byId: new Map(i.data.issues.map((x) => [x.id, x])) }
}

// ---- formatting --------------------------------------------------------------------------------
export const num = (v: unknown): v is number => typeof v === 'number' && isFinite(v)
export const fmt = (v: unknown, d = 1) => !num(v) ? 'unknown' : v.toLocaleString('en-US', { maximumFractionDigits: Math.abs(v) < 10 ? 2 : d })
export const fmtT = (v: unknown) => !num(v) ? 'unknown' : `${fmt(v, 0)} t`
export const sgnT = (v: unknown) => !num(v) ? 'unknown' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmt(Math.abs(v), 0)} t`
export const humanize = (s: string | null | undefined) => s ? (s.charAt(0).toUpperCase() + s.slice(1)).replace(/_/g, ' ') : ''

// ---- plain-language wording (one place; unknown codes fall back to a humanised name) ------------
export type BadgeVariant = 'pending' | 'ok' | 'warn' | 'reject' | 'outline'
export type Family = 'slip' | 'dup' | 'gap' | 'ref' | 'check'
export const FAMILY: Record<Family, { name: string; explain: string }> = {
  slip: { name: 'Typing or unit slips', explain: 'A number was entered in the wrong unit, currency or decimal place, or a code was typed wrong.' },
  dup: { name: 'Counted twice', explain: 'The same purchase or trip was entered more than once.' },
  gap: { name: 'Missing or broken readings', explain: 'Data was missing, or a reading was clearly wrong, so it had to be estimated.' },
  ref: { name: "Doesn't match another record", explain: "Two records that should agree don't, for example an invoice and the product list, or our own log and an official registry." },
  check: { name: 'Looks unusual: needs a person', explain: "Something looks unlikely but can't be fixed automatically. A person should check it." },
}
export const FAMILY_ORDER: Family[] = ['slip', 'dup', 'gap', 'ref', 'check']
// f = cause family, t = plain title, e = what happened and what we do about it
const PLAIN_TYPE: Record<string, { f: Family; t: string; e: string }> = {
  unit_error: { f: 'slip', t: 'Wrong unit', e: 'A number was entered in the wrong unit (for example kWh in a MWh column, or grams in a kilograms column), so it was about 1,000 times too big or too small. We converted it.' },
  decimal_shift: { f: 'slip', t: 'Decimal point in the wrong place', e: 'The value is about 10 times bigger or smaller than similar entries, so the decimal point was probably typed in the wrong place. We moved it back.' },
  pcf_unit_error: { f: 'slip', t: 'Supplier footprint in the wrong unit', e: "A supplier's product footprint is about 1,000 times its other years, most likely grams instead of kilograms. We converted it." },
  currency_error: { f: 'slip', t: 'Wrong currency', e: 'An amount was booked in the wrong currency (for example Swedish kronor entered as euros), which makes the spend look about 11 times bigger. We restored the right currency.' },
  wrong_gas_code: { f: 'slip', t: 'Wrong refrigerant gas', e: 'A service record names a different cooling gas than this equipment normally uses. We used the gas it normally uses.' },
  mode_mislabel: { f: 'slip', t: 'Travel mode typed freely', e: "A commuting answer used free text (like 'Car') instead of one of the survey's options. We matched it to the right option." },
  coordinate_swap: { f: 'slip', t: 'Map coordinates swapped', e: "A farm's latitude and longitude were swapped. We switched them back." },
  duplicate_record: { f: 'dup', t: 'Counted twice', e: 'The same entry appears twice, a few days apart, with identical details. We removed the later copy.' },
  missing_record: { f: 'gap', t: 'Missing meter reading', e: "A month is missing from a meter's readings. We estimated it from the site's usual seasonal pattern." },
  meter_spike: { f: 'gap', t: 'Unusual meter spike', e: 'A meter reading is more than twice what the site normally uses that month. We replaced it with an estimate from the usual pattern.' },
  missing_leg: { f: 'gap', t: 'Missing transport step', e: 'A shipment is missing a transport step that similar shipments have. We estimated it from similar shipments.' },
  material_mismatch: { f: 'ref', t: "Product name and code don't match", e: 'On an invoice line, the product name and product code point to different products. We used the code that matches the name.' },
  certificate_mismatch: { f: 'ref', t: "Green-electricity certificate doesn't match the registry", e: "Our own record of renewable-electricity certificates disagrees with the official national registry. We used the registry's figures." },
  pcf_stale_period: { f: 'ref', t: 'Outdated supplier footprint', e: "A supplier's product footprint covers a different period than the year it was filed for, so we used a standard average value instead." },
  total_mismatch: { f: 'ref', t: "Report total doesn't add up", e: "The draft report's total isn't the sum of its lines. Two digits look swapped, so we corrected that line." },
  outlier_implausible: { f: 'check', t: 'Unbelievable harvest figure', e: 'A harvest figure is about 10 times the typical value for that crop and year. Nothing was changed: please check it.' },
  area_mismatch: { f: 'check', t: "Field size doesn't match", e: 'The reported crop area differs by more than 20% from the registered field area. Nothing was changed: the calculation already uses the registered area.' },
  soil_misreport: { f: 'check', t: "Soil type doesn't match the soil map", e: 'The survey says mineral soil, but the soil map shows a large share of peat soil. Nothing was changed: the calculation already uses the soil map.' },
}
export const typeInfo = (t: string) => PLAIN_TYPE[t] ?? { f: 'check' as Family, t: humanize(t), e: '' }
// table -> [plain name, where it comes from]
const PLAIN_SOURCE: Record<string, [string, string]> = {
  erp_purchase_lines: ['Purchase invoices', 'the purchasing (ERP) system'], energy_meter_readings: ['Energy meter readings', 'site electricity and heat meters'],
  fuel_deliveries: ['Fuel deliveries', 'fuel supplier delivery notes'], goo_cancellations: ['Green-electricity certificates', 'our certificate log'],
  refrigerant_service_log: ['Cooling-equipment servicing', 'the refrigerant service log'], waste_transfer_notes: ['Waste collections', 'waste transfer notes'],
  travel_bookings: ['Business travel', 'the travel booking system'], commuting_survey: ['Staff commuting survey', 'the staff commuting survey'],
  shipments: ['Inbound shipments', 'transport documents'], supplier_pcfs: ['Supplier product footprints', 'footprint files sent by suppliers'],
  farm_survey: ['Farm survey', 'the contract-farm survey'], farm_registry: ['Farm register', 'the contract-farm register'],
  draft_report_summary: ['Draft climate report', 'the draft report summary'],
}
export const srcFrom = (tb: string) => PLAIN_SOURCE[tb]?.[1] ?? ''
export const PLAIN_STATUS: Record<IssueStatus, [string, BadgeVariant]> = {
  open: ['Needs your decision', 'warn'], auto_applied: ['Fixed automatically', 'pending'], accepted: ['Approved', 'ok'],
  overridden: ['Changed by a reviewer', 'outline'], rejected: ['Kept as recorded', 'reject'],
}
export type StatusGroup = 'open' | 'auto' | 'done'
export const STATUS_GROUP: Record<StatusGroup, IssueStatus[]> = { open: ['open'], auto: ['auto_applied'], done: ['accepted', 'overridden', 'rejected'] }
export const GROUP_LABEL: Record<StatusGroup, string> = { open: 'Needs your decision', auto: 'Fixed automatically', done: 'Reviewed' }
export const PLAIN_SCOPE: Record<string, string> = {
  scope1: 'our own sites: fuel and refrigerants', scope2_location: 'purchased electricity and heat',
  scope2_market: 'purchased electricity and heat', scope3: 'the value chain: purchases, transport, travel, waste and farms',
}
export const ACTION: Record<string, string> = { correct: 'Correct', estimate: 'Estimate', method: 'Method note', flag: 'Flag only' }
const FIELD: Record<string, string> = {
  net_amount: 'amount', currency: 'currency', quantity: 'quantity', uom: 'unit', material_id: 'product code', material_text: 'product name',
  kg_added: 'refrigerant added (kg)', gas_code: 'gas type', lat: 'latitude', lon: 'longitude', latitude: 'latitude', longitude: 'longitude',
  mode: 'travel mode', one_way_km: 'one-way distance (km)', mwh: 'energy (MWh)',
}
export const fieldName = (f: string | null | undefined) => f ? FIELD[f] ?? f.replace(/_/g, ' ') : ''
const RAW_FIELD = /(^|_)(year|month|day|date|id|no|code|line)$/ // shown as-is: no "2,024"
/** A value as a person reads it: numbers with separators, ids and years as written. */
export const pv = (v: unknown, f?: string | null) => {
  if (v == null || v === '') return 'empty'
  if (f && RAW_FIELD.test(f)) return String(v)
  const n = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' && isFinite(+v) ? +v : null
  return n != null ? fmt(n, 2) : String(v)
}
export const sure = (c: number | null) => !num(c) ? '' : c >= 0.9 ? 'Very sure' : c >= 0.7 ? 'Fairly sure' : 'Not very sure'
export const rowLabel = (i: Issue) => i.trace.raw.row ? `Row ${i.trace.raw.row}` : 'Estimated entry'

export type Severity = 'high' | 'med' | 'low' | 'info'
export const SEV: Record<Severity, [string, number, BadgeVariant]> = {
  high: ['High', 3, 'reject'], med: ['Medium', 2, 'warn'], low: ['Low', 1, 'outline'], info: ['Info', 0, 'pending'],
}

// Headline footprint = Scope 1 + Scope 2 (market-based) + Scope 3; Scope 2 location-based is left out so it isn't counted twice.
const FOOT_CATS = ['scope1_total', 'scope2_market_total', 'scope3_total']
const plainBy = (i: Issue) => Object.entries(i.effect.by ?? {}).filter(([k]) => !k.startsWith('scope2_location|'))
/** The issue's effect on the headline footprint (t CO2e), or null when the before-fix figure is unknown. */
export const plainDt = (i: Issue) => !num(i.effect.dt) ? null : plainBy(i).reduce((a, [, v]) => a + (v || 0), 0)
export const imp = (i: Issue) => { const v = plainDt(i); return num(v) ? Math.abs(v) : -1 }
export const mainCat = (i: Issue): [string, string] | null => {
  const e = plainBy(i).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0]
  return e ? (e[0].split('|') as [string, string]) : null
}

/** Helpers that need the loaded data. */
export function model(fp: Footprint) {
  const srcName = (tb: string) => PLAIN_SOURCE[tb]?.[0] ?? fp.run.sources.find((s) => s.source === tb)?.description ?? humanize(tb)
  const totalRow = (y: number, cat: string) => fp.inv.rows.find((r) => r.year === y && r.scope === 'total' && r.category === cat)
  const footprint = (y: number, k: 't' | 't0') => {
    let s = 0
    for (const c of FOOT_CATS) { const v = totalRow(y, c)?.[k]; if (!num(v)) return null; s += v }
    return s
  }
  const foot = new Map(fp.inv.years.map((y) => [y, footprint(y, 't')]))
  // Severity = size of the issue's effect relative to the year's footprint after fixes.
  const sevOf = (i: Issue): Severity => {
    const d = plainDt(i), f = i.year != null ? foot.get(i.year) : null
    if (!num(d) || Math.abs(d) < 0.5) return 'info'
    const r = num(f) && f > 0 ? Math.abs(d) / f : 0
    return r >= 0.01 ? 'high' : r >= 0.001 ? 'med' : 'low'
  }
  const catTotal = (y: number, scope: string, cat: string) => fp.inv.rows.find((r) => r.year === y && r.scope === scope && r.category === cat)?.t ?? null
  const ruleText = (id: string) => fp.run.rules.find((r) => r.rule === id)?.description ?? ''
  return { srcName, footprint, sevOf, catTotal, ruleText }
}
export type Model = ReturnType<typeof model>

/** Short "field: recorded → proposed" line for list rows. */
export function changeText(i: Issue) {
  const f = fieldName(i.field), pre = f ? `${f}: ` : ''
  if (i.drop) return 'Duplicate copy removed'
  if (i.action === 'estimate' && i.observed == null) return `Estimate added${i.proposed != null ? `: ${pv(i.proposed, i.field)}` : ''}`
  if (i.action === 'flag' || i.action === 'method')
    return i.proposed != null ? `${pre}${pv(i.observed, i.field)} (suggested ${pv(i.proposed, i.field)}, not changed)` : `${pre}${pv(i.observed, i.field)} looks unusual (not changed)`
  if (i.observed != null || i.proposed != null) return `${pre}${pv(i.observed, i.field)} → ${pv(i.proposed, i.field)}`
  return typeInfo(i.type).t
}
/** The changes that actually happened for this issue: old != new, the problem field first, bookkeeping fields left out. */
export function realChanges(i: Issue) {
  const seen = new Set<string>()
  const real = (i.trace.s3?.changes ?? []).filter((c) => c.issue_id === i.id && String(c.old_value) !== String(c.new_value))
    .filter((c) => { const k = `${c.old_value}|${c.new_value}`; if (seen.has(k)) return false; seen.add(k); return true })
  const own = real.filter((c) => c.field === i.field)
  return own.length ? own : real.filter((c) => !/^estimate/.test(c.field ?? ''))
}

// ---- review decisions (browser-local until downloaded; same file contract as the pipeline expects) ----
export type DecisionKind = 'accept' | 'reject' | 'override' | 'sign_off'
export type Decision = {
  decision_id: string; issue_id: string | null; decision: DecisionKind; override_field: string | null; override_value: string | null
  reviewer: string; decided_at: string; comment: string | null; _record_key?: string; _type?: string; _year?: number | null
}
const DEC_STATUS: Record<string, IssueStatus> = { accept: 'accepted', reject: 'rejected', override: 'overridden' }
const LS_KEY = 'ccn.decisions' // shared with the earlier static page, so decisions carry over
const now = () => new Date().toISOString().slice(0, 19) + 'Z'

export function useDecisions() {
  const [decisions, setDecisions] = useState<Record<string, Decision>>(() => {
    try { return JSON.parse(lsGet(LS_KEY) ?? '{}') } catch { return {} }
  })
  const update = useCallback((f: (d: Record<string, Decision>) => Record<string, Decision>) => {
    setDecisions((prev) => { const n = f(prev); lsSet(LS_KEY, JSON.stringify(n)); return n })
  }, [])
  const statusOf = useCallback((i: Issue): IssueStatus => decisions[i.id] ? DEC_STATUS[decisions[i.id].decision] : i.status, [decisions])
  const decide = useCallback((issues: Issue[], decision: Exclude<DecisionKind, 'sign_off'>, reviewer: string, opts: { comment?: string; value?: string } = {}) => {
    const base = Date.now(), at = now()
    update((d) => {
      const n = { ...d }
      issues.forEach((i, k) => {
        n[i.id] = {
          decision_id: 'dec:' + (base + k).toString(36), issue_id: i.id, decision,
          override_field: decision === 'override' ? i.field : null, override_value: decision === 'override' ? opts.value ?? null : null,
          reviewer, decided_at: at, comment: opts.comment || null, _record_key: i.record_key, _type: i.type, _year: i.year,
        }
      })
      return n
    })
  }, [update])
  const undo = useCallback((id: string) => update((d) => { const n = { ...d }; delete n[id]; return n }), [update])
  const signOff = useCallback((year: number, reviewer: string) => update((d) => ({
    ...d, [`signoff:${year}`]: {
      decision_id: 'dec:' + Date.now().toString(36), issue_id: null, decision: 'sign_off', override_field: null, override_value: String(year),
      reviewer, decided_at: now(), comment: 'Signed off from the dashboard', _year: year,
    },
  })), [update])
  return { decisions, statusOf, decide, undo, signOff }
}

export function download(name: string, text: string, type: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
/** review_decisions.json: exactly the columns `python -m pipeline review` reads. */
export function exportDecisions(decisions: Record<string, Decision>) {
  const rows = Object.values(decisions).map(({ _record_key, _type, _year, ...d }) => d)
  download('review_decisions.json', JSON.stringify(rows, null, 2), 'application/json')
}
