import { useState, type ReactNode } from 'react'
import { Check, ChevronLeft, ChevronRight, Undo2, X } from 'lucide-react'
import { fmtTime } from '@/lib/api'
import { useApp } from '@/lib/app'
import {
  ACTION, PLAIN_SCOPE, PLAIN_STATUS, SEV, fieldName, fmt, fmtT, humanize, mainCat, num, plainDt, pv, realChanges, sgnT, srcFrom, sure, typeInfo,
  type Decision, type Footprint, type Issue, type IssueStatus, type Model,
} from '@/lib/footprint'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export type PanelProps = {
  issue: Issue; fp: Footprint; m: Model
  position: { index: number; total: number; prev: string | null; next: string | null }
  onOpen: (id: string) => void; onClose: () => void
  statusOf: (i: Issue) => IssueStatus; decision: Decision | undefined
  decide: (decision: 'accept' | 'reject' | 'override', opts: { comment?: string; value?: string }) => void
  undo: () => void
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-border px-4 py-3">
      <h3 className="label mb-1.5">{title}</h3>
      {children}
    </section>
  )
}

/** Collapsible technical section; stays open while you step through issues. */
function Tech({ id, title, sub, children }: { id: string; title: string; sub?: string; children: ReactNode }) {
  const [open, setOpen] = useState(() => sessionStorage.getItem(`fp.tech.${id}`) === '1')
  return (
    <details className="group border-b border-border px-4 py-2.5" open={open}
      onToggle={(e) => { const o = (e.currentTarget as HTMLDetailsElement).open; setOpen(o); sessionStorage.setItem(`fp.tech.${id}`, o ? '1' : '0') }}>
      <summary className="flex cursor-pointer list-none items-baseline gap-1.5 text-[13px] [&::-webkit-details-marker]:hidden">
        <ChevronRight size={12} className="shrink-0 self-center transition-transform group-open:rotate-90" />
        <span className="font-medium">{title}</span>{sub && <span className="num truncate text-xs text-muted-foreground">{sub}</span>}
      </summary>
      <div className="mt-2 space-y-2 text-[13px]">{children}</div>
    </details>
  )
}

const B = ({ children }: { children: ReactNode }) => <b className="font-semibold">{children}</b>

function didText(i: Issue, st: IssueStatus, d: Decision | undefined): ReactNode {
  const f = fieldName(i.field) || 'the value', applied = ' This takes effect when the data team re-runs the numbers.'
  if (d) {
    if (d.decision === 'override') return <>You chose to use <B>{d.override_value}</B> for {f}.{applied}</>
    if (d.decision === 'reject') return i.status === 'open' ? 'You marked this as not a problem.'
      : <>You chose to keep the original value{i.observed != null && <> (<B>{pv(i.observed, i.field)}</B>)</>}.{applied}</>
    if (i.status === 'open') return <>You confirmed this is a problem.{i.proposed != null && <> Suggested value: <B>{pv(i.proposed, i.field)}</B>.</>}</>
  }
  if (st === 'rejected') return <>Nothing changed: a reviewer decided to keep the original value{i.observed != null && <> (<B>{pv(i.observed, i.field)}</B>)</>}.</>
  const who = st === 'accepted' ? ' A reviewer approved this.' : st === 'overridden' ? ' A reviewer then chose a different value.' : ''
  if (i.drop || (i.trace.s3?.excluded && i.type === 'duplicate_record')) return `We removed this entry because it is a copy of an earlier one, so it is only counted once.${who}`
  if (i.action === 'flag') return <>Nothing changed.{i.proposed != null ? <> A more likely value would be <B>{pv(i.proposed, i.field)}</B>, but a person needs to decide.</> : ' A person needs to check it.'}{i.type === 'area_mismatch' && ' The calculation already uses the registered field area.'}</>
  if (i.action === 'method') return 'Nothing changed in the data. The calculation already handles this (for example, by using the soil map). We note it so you know.'
  const chg = realChanges(i)
  if (chg.length) return <>We changed {chg.map((c, k) => <span key={k}>{k > 0 && ', and '}{fieldName(c.field) || 'the value'} from <B>{pv(c.old_value, c.field)}</B> to <B>{pv(c.new_value, c.field)}</B></span>)}{i.action === 'estimate' && ', using an estimate'}.{who}</>
  if (i.action === 'estimate') return <>We filled the gap with an estimate{i.proposed != null && <> of <B>{pv(i.proposed, i.field)}</B></>}.{who}</>
  if (i.observed != null || i.proposed != null) return <>We changed {f} from <B>{pv(i.observed, i.field)}</B> to <B>{pv(i.proposed, i.field)}</B>.{who}</>
  return `We corrected this automatically.${who}`
}

function meansText(i: Issue, m: Model): ReactNode {
  const dt = plainDt(i), mc = mainCat(i)
  if (!num(dt)) return "We can't tell how much this changed the footprint, because the figure before the fixes couldn't be calculated."
  if (Math.abs(dt) < 0.001) return `No change to the footprint.${i.action === 'flag' || i.action === 'method' ? ' It is only flagged so a person can check it.' : ''}`
  const cat = mc && i.year != null ? m.catTotal(i.year, mc[0], mc[1]) : null
  return (
    <>
      This {dt < 0 ? 'lowered' : 'raised'} the {i.year} footprint by <B>{fmtT(Math.abs(dt))}</B> of CO₂e
      {mc && <>, mostly in <B>{humanize(mc[1].replace(/^cat\d+_/, '')).toLowerCase()}</B> ({PLAIN_SCOPE[mc[0]] ?? humanize(mc[0])}){num(cat) && <>. That category is now {fmtT(cat)} in total</>}</>}.
      {i.effect.shared_with > 0 && <span className="text-muted-foreground"> This entry has {i.effect.shared_with + 1} problems, so the change is split equally between them.</span>}
    </>
  )
}

function DecisionBox({ issue: i, st, decision: d, decide, undo }: { issue: Issue; st: IssueStatus; decision: Decision | undefined } & Pick<PanelProps, 'decide' | 'undo'>) {
  const { reviewer } = useApp()
  const [why, setWhy] = useState('')
  const [val, setVal] = useState('')
  const [err, setErr] = useState('')
  if (d) {
    const what = { accept: i.status === 'open' ? 'Confirmed as a problem' : 'Approved', reject: i.status === 'open' ? 'Not a problem' : 'Keep the original value', override: 'Use a different value', sign_off: '' }[d.decision]
    return (
      <div className="space-y-1.5 text-[13px]">
        <div className="flex items-center gap-2"><Badge variant={PLAIN_STATUS[st][1]}>{what}</Badge>{d.override_value != null && <span className="num">{d.override_value}</span>}</div>
        <p className="text-muted-foreground">{d.reviewer} · <span className="num">{fmtTime(d.decided_at)}</span>{d.comment && <> · “{d.comment}”</>}</p>
        <Button size="sm" variant="outline" onClick={undo}><Undo2 /> Change my mind</Button>
      </div>
    )
  }
  const open = st === 'open'
  const labels = open ? ["Yes, it's a problem", "No, it's fine", 'Use a different value'] : ['Approve this fix', 'Undo the fix, keep the original', 'Use a different value']
  const prompt = {
    open: "Our checks can't settle this alone. What do you think?", auto_applied: 'We fixed this automatically. Do you agree?',
    accepted: 'A reviewer approved this earlier. You can still change it.', overridden: 'A reviewer chose a different value earlier. You can still change it.',
    rejected: 'A reviewer kept the original value earlier. You can still change it.',
  }[st]
  const noName = !reviewer.trim()
  const go = (kind: 'accept' | 'reject' | 'override') => {
    if (kind !== 'accept' && !why.trim()) return setErr('Add a short reason first. It is saved with your decision.')
    if (kind === 'override' && !val.trim()) return setErr('Type the value you want to use first.')
    decide(kind, { comment: why.trim(), value: val.trim() })
  }
  const btn = (label: string, kind: 'accept' | 'reject' | 'override', variant: 'default' | 'outline', icon?: ReactNode) => {
    const b = <Button size="sm" variant={variant} disabled={noName} onClick={() => go(kind)}>{icon}{label}</Button>
    return noName ? <Tooltip><TooltipTrigger render={<span tabIndex={0} className="inline-flex" />}>{b}</TooltipTrigger><TooltipContent>Enter your name in the sidebar</TooltipContent></Tooltip> : b
  }
  return (
    <div className="space-y-2 text-[13px]">
      <p>{prompt}</p>
      <div className="flex flex-wrap gap-2">{btn(labels[0], 'accept', 'default', <Check />)}{btn(labels[1], 'reject', 'outline', <X />)}</div>
      <Input value={why} onChange={(e) => { setWhy(e.target.value); setErr('') }} placeholder="Why? (needed unless you approve)" aria-label="Reason for your decision" className="h-8 text-[13px]" />
      <div className="flex gap-2">
        <Input value={val} onChange={(e) => { setVal(e.target.value); setErr('') }} placeholder={`New value${i.field ? ` for ${fieldName(i.field)}` : ''}`} aria-label="Different value" className="h-8 text-[13px]" />
        {btn(labels[2], 'override', 'outline')}
      </div>
      {err && <p role="alert" className="text-reject">{err}</p>}
      {noName && <p className="text-xs text-muted-foreground">Enter your name in the sidebar to record a decision.</p>}
    </div>
  )
}

/** The seven pipeline stages for one issue, stacked vertically. */
function TraceList({ i }: { i: Issue }) {
  const t = i.trace, s3 = t.s3 ?? { changes: [], excluded: false, estimate: false, flagged: false }, s4 = t.s4, g = t.gold
  const chg = s3.changes.filter((c) => c.issue_id === i.id)
  const s1chg = !!(i.field && t.s1?.changes && i.field in t.s1.changes)
  const nS1 = Object.keys(t.s1?.changes ?? {}).length
  const rows: { name: string; state: string; body: ReactNode; tag?: string }[] = [
    { name: 'Raw', state: 'enter', body: <><span className="num block">{(t.raw.file || '').split('/').pop()}{t.raw.row ? ` : row ${t.raw.row}` : ''}</span><span className="num text-muted-foreground">{(t.raw.sha256 || '').slice(0, 12)}</span></>, tag: 'error enters' },
    { name: 'Bronze', state: '', body: i.field ? <><span className="text-muted-foreground">{i.field} </span><span className="num">{String(t.bronze.value ?? '—')}</span></> : <span className="text-muted-foreground">row parsed</span> },
    { name: 'S1', state: s1chg ? '' : 'dim', body: s1chg ? <><span className="text-muted-foreground">normalised </span><span className="num">{String(t.s1.value)}</span></> : <span className="text-muted-foreground">{nS1 ? `${nS1} fields normalised` : 'unchanged'}</span> },
    { name: 'S2', state: 'caught', body: <><span className="num block">{i.rule}</span><span className="text-muted-foreground">{num(i.confidence) ? `${Math.round(i.confidence * 100)}% confidence` : ''}</span></>, tag: 'caught' },
    { name: 'S3', state: chg.length || s3.excluded || s3.estimate ? 'fixed' : 'dim', body: s3.excluded ? <span className="num">excluded</span>
        : chg.length ? chg.map((c, k) => <span key={k} className="block"><span className="num">{c.field}: {String(c.old_value ?? '∅')} → {String(c.new_value)}</span> <span className="text-muted-foreground">{c.kind} · {c.status}</span></span>)
          : <span className="text-muted-foreground">{s3.flagged ? 'flagged, value kept' : 'no change'}</span>, tag: chg.length || s3.excluded ? 'fixed' : undefined },
    { name: 'S4', state: s4?.status === 'in' ? '' : 'dim', body: <><span className="num block">{(s4?.status ?? '—').replace('_', ' ')}</span>{(s4?.links ?? []).slice(0, 3).map(([tb, dk], k) => <span key={k} className="num block text-muted-foreground">{tb}{dk ? ` ← ${dk}` : ''}</span>)}</> },
    { name: 'Gold', state: g ? '' : 'dim', body: g ? <><span className="num block">{num(g.t0) ? `${fmt(g.t0, 2)} → ` : ''}{fmt(g.t, 2)} t</span><span className="text-muted-foreground">{(g.lines ?? []).length} line item(s)</span></> : <span className="text-muted-foreground">no direct emissions</span> },
  ]
  const tone: Record<string, string> = { enter: 'border-reject/60', caught: 'border-warn/60', fixed: 'border-ok/60', dim: 'opacity-60', '': '' }
  return (
    <>
      <ol className="space-y-1">
        {rows.map(({ name, state, body, tag }) => (
          <li key={name} className={cn('grid grid-cols-[52px_1fr] gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-xs', tone[state])}>
            <span className="font-medium">{name}</span>
            <span className="min-w-0 break-words">{body}{tag && <span className="ml-1 text-[11px] font-medium text-muted-foreground">· {tag}</span>}</span>
          </li>
        ))}
      </ol>
      <p className="text-xs text-muted-foreground">Raw = the file as received · Bronze = parsed into a table · S1 = units and formats standardised · S2 = checks run · S3 = fixes applied · S4 = mapped to reporting tables · Gold = emission figures.</p>
    </>
  )
}

function LineTable({ lines, cols, title }: { lines?: unknown[][]; cols: string[]; title: string }) {
  if (!lines?.length) return <p className="text-xs text-muted-foreground">{title}: no line items.</p>
  const ix = (n: string) => cols.indexOf(n), v = (r: unknown[], n: string) => r[ix(n)]
  return (
    <div>
      <h4 className="label mb-1">{title} ({lines.length})</h4>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-[12px]">
          <thead><tr className="border-b border-border bg-subtle text-left text-muted-foreground">{['Scope · category', 'Activity', 'Factor', 't CO₂e'].map((h, k) => <th key={h} className={cn('px-2 py-1 font-medium', k === 3 && 'text-right')}>{h}</th>)}</tr></thead>
          <tbody>
            {lines.slice(0, 12).map((r, k) => (
              <tr key={k} className="border-b border-border align-top last:border-0">
                <td className="px-2 py-1">{String(v(r, 'scope'))}<div className="text-muted-foreground">{String(v(r, 'category'))}{v(r, 'component') ? ` · ${v(r, 'component')}` : ''}</div></td>
                <td className="num px-2 py-1 whitespace-nowrap">{fmt(v(r, 'activity_value'), 2)} {String(v(r, 'activity_unit') ?? '')}</td>
                <td className="num px-2 py-1">{fmt(v(r, 'factor_value'), 4)} {String(v(r, 'factor_unit') ?? '')}<div className="text-muted-foreground">{String(v(r, 'factor_id') ?? '')}</div></td>
                <td className="num px-2 py-1 text-right">{fmt(v(r, 'tco2e'), 3)}</td>
              </tr>
            ))}
            {lines.length > 12 && <tr><td colSpan={4} className="px-2 py-1 text-muted-foreground">… {lines.length - 12} more</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Glyph({ i }: { i: Issue }) {
  const a = parseFloat(String(i.observed)), b = parseFloat(String(i.proposed))
  if (!(num(a) && num(b) && a > 0 && b > 0 && a !== b)) return null
  const lo = Math.floor(Math.log10(Math.min(a, b))) - 1, hi = Math.ceil(Math.log10(Math.max(a, b)))
  const w = (x: number) => `${Math.max(1, ((Math.log10(x) - lo) / (hi - lo)) * 100)}%`
  const r = a / b, lab = r >= 1 ? `÷${fmt(r, 2)}` : `×${fmt(1 / r, 2)}`
  return (
    <div className="space-y-1 text-xs">
      <div className="h-2 rounded-r" style={{ width: w(a), background: 'var(--series-2)' }} />
      <div className="h-2 rounded-r bg-primary" style={{ width: w(b) }} />
      <p className="text-muted-foreground"><span className="num">{pv(i.observed, i.field)}</span> recorded → <span className="num">{pv(i.proposed, i.field)}</span> proposed · <b>{lab}</b> (log scale)</p>
    </div>
  )
}

export function IssuePanel({ issue: i, fp, m, position, onOpen, onClose, statusOf, decision, decide, undo }: PanelProps) {
  const ti = typeInfo(i.type), st = statusOf(i), t = i.trace, row = t.bronze?.row, file = (t.raw.file || '').split('/').pop()
  const by = Object.entries(i.effect.by ?? {})
  const related = fp.iss.issues.filter((x) => x.record_key === i.record_key && x.table === i.table && x.id !== i.id)
  const sev = m.sevOf(i)
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
        <div className="flex items-center gap-1">
          <Button size="icon-sm" variant="ghost" disabled={!position.prev} onClick={() => position.prev && onOpen(position.prev)} aria-label="Previous issue"><ChevronLeft /></Button>
          <span className="num text-xs text-muted-foreground">{position.index >= 0 ? `${position.index + 1} of ${position.total}` : 'not in the current filter'}</span>
          <Button size="icon-sm" variant="ghost" disabled={!position.next} onClick={() => position.next && onOpen(position.next)} aria-label="Next issue"><ChevronRight /></Button>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close issue panel"><X /></Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="border-b border-border px-4 py-3">
          <div className="flex gap-1.5"><Badge variant={SEV[sev][2]}>{SEV[sev][0]}</Badge><Badge variant={PLAIN_STATUS[st][1]}>{PLAIN_STATUS[st][0]}</Badge></div>
          <h2 className="mt-1.5 text-[15px]">{ti.t}</h2>
          <p className="text-[13px] text-muted-foreground">{m.srcName(i.table)} · {(t.raw.row ? `row ${t.raw.row}` : 'estimated entry')}{i.year ? ` · ${i.year}` : ''}</p>
        </div>

        <Section title="Where it came from">
          <p className="text-[13px]"><B>{m.srcName(i.table)}</B>{srcFrom(i.table) && ` (from ${srcFrom(i.table)})`}.{' '}
            {t.raw.row ? <>File <span className="num">{file}</span>, row {t.raw.row}.</> : "This entry wasn't in the file: we added it as an estimate to fill a gap."}{i.year ? ` Year ${i.year}.` : ''}</p>
          {row && (
            <details className="group mt-1.5">
              <summary className="flex cursor-pointer list-none items-center gap-1 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden">
                <ChevronRight size={12} className="transition-transform group-open:rotate-90" /> The original entry, exactly as it was recorded
              </summary>
              <div className="mt-1.5 overflow-x-auto rounded-md border border-border">
                <table className="w-full text-[12px]"><tbody>
                  {Object.entries(row).map(([k, v]) => (
                    <tr key={k} className={cn('border-b border-border last:border-0', i.field === k && 'bg-reject/10 font-medium')}>
                      <td className="px-2 py-1 text-muted-foreground">{fieldName(k)}</td>
                      <td className="num px-2 py-1">{pv(v, k)}{i.field === k && <span className="ml-1 font-sans text-reject">← the problem</span>}</td>
                    </tr>
                  ))}
                </tbody></table>
              </div>
            </details>
          )}
        </Section>
        <Section title="What we noticed">
          <p className="text-[13px]">{ti.e}</p>
          {(i.field || i.observed != null) && <p className="mt-1 text-[13px]">The value in question{i.field && <>: <B>{fieldName(i.field)}</B></>}{i.observed != null && <> = <B>{pv(i.observed, i.field)}</B></>}.</p>}
          {num(i.confidence) && <p className="mt-0.5 text-xs text-muted-foreground">How sure our check is: {sure(i.confidence)} ({Math.round(i.confidence * 100)}%)</p>}
        </Section>
        <Section title="What we did"><p className="text-[13px]">{didText(i, st, decision)}</p></Section>
        <Section title="What it means for the footprint"><p className="text-[13px]">{meansText(i, m)}</p></Section>
        <Section title="Your decision"><DecisionBox key={i.id} issue={i} st={st} decision={decision} decide={decide} undo={undo} /></Section>

        <h3 className="label px-4 pt-3 pb-1">Technical details</h3>
        <Tech id="trace" title="Pipeline trace" sub="file → footprint"><TraceList i={i} /></Tech>
        <Tech id="rule" title="Detection rule" sub={i.rule}>
          <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted-foreground">Rule</dt><dd><span className="num">{i.rule}</span>{m.ruleText(i.rule) && <div>{m.ruleText(i.rule)}</div>}</dd>
            <dt className="text-muted-foreground">Action</dt><dd>{ACTION[i.action] ?? i.action}</dd>
            <dt className="text-muted-foreground">Confidence</dt><dd className="num">{num(i.confidence) ? `${Math.round(i.confidence * 100)}%` : '—'}</dd>
            {i.field && <><dt className="text-muted-foreground">Field</dt><dd className="num">{i.field}</dd></>}
            <dt className="text-muted-foreground">Evidence</dt><dd className="break-words">{i.evidence || '—'}</dd>
          </dl>
          <Glyph i={i} />
        </Tech>
        <Tech id="calc" title="Calculation before and after" sub="emission line items">
          {by.length
            ? <ul className="space-y-0.5">{by.map(([k, v]) => <li key={k}>{k.replace('|', ' · ')}: <span className="num font-medium">{sgnT(v)}</span></li>)}</ul>
            : <p className="text-muted-foreground">No change to any total (flag only, method note, or no emissions).</p>}
          {i.effect.shared_with > 0 && <p className="text-xs text-muted-foreground">The record has {i.effect.shared_with + 1} issues; its change is split equally.</p>}
          {t.gold ? <><LineTable lines={t.gold.lines0} cols={fp.iss.line_columns} title="Line items as recorded" /><LineTable lines={t.gold.lines} cols={fp.iss.line_columns} title="Line items after fixes" /></>
            : <p className="text-muted-foreground">This record has no emission line items of its own.</p>}
        </Tech>
        {related.length > 0 && (
          <Tech id="rel" title={`Other issues on this record (${related.length})`}>
            <ul className="space-y-0.5">{related.map((x) => <li key={x.id}><button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => onOpen(x.id)}>{typeInfo(x.type).t}</button> <span className="num text-xs text-muted-foreground">{x.year}</span></li>)}</ul>
          </Tech>
        )}
        {i.dev && (
          <Tech id="dev" title="Answer-sheet check" sub={i.dev.type_match ? 'confirmed' : i.dev.in_key ? 'different type' : 'not listed'}>
            {i.dev.type_match ? <p className="text-ok">✓ Confirmed: the answer sheet labels this record {i.dev.key_types.join(', ')}{i.dev.true_value != null && `, true value ${String(i.dev.true_value)}`}{i.dev.note != null && ` (“${String(i.dev.note)}”)`}</p>
              : i.dev.in_key ? <p className="text-warn">≈ The record is on the answer sheet, but as {i.dev.key_types.join(', ')}</p>
                : <p className="text-reject">✗ Not on the answer sheet: possibly a false alarm.</p>}
          </Tech>
        )}
        <Tech id="ids" title="Identifiers">
          <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted-foreground">Record key</dt><dd className="num break-all">{i.record_key}</dd>
            <dt className="text-muted-foreground">Issue id</dt><dd className="num break-all">{i.id}</dd>
            <dt className="text-muted-foreground">Source file</dt><dd className="num break-all">{t.raw.file}{t.raw.row ? ` · row ${t.raw.row}` : ''}</dd>
            <dt className="text-muted-foreground">SHA-256</dt><dd className="num">{(t.raw.sha256 || '').slice(0, 16)}…</dd>
          </dl>
        </Tech>
      </div>
    </div>
  )
}
