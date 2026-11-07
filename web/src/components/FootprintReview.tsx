import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, Download, X } from 'lucide-react'
import { fmtTime } from '@/lib/api'
import { useApp } from '@/lib/app'
import {
  FAMILY, FAMILY_ORDER, GROUP_LABEL, PLAIN_STATUS, SEV, STATUS_GROUP, changeText, download, exportDecisions, fmt, fmtT, imp, loadFootprint, model, num,
  plainDt, rowLabel, sgnT, typeInfo, useDecisions,
  type Family, type Footprint, type Issue, type Model, type Severity, type StatusGroup,
} from '@/lib/footprint'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { IssuePanel } from './IssuePanel'
import { cn } from '@/lib/utils'

type SortKey = 'sev' | 'type' | 'src' | 'imp' | 'conf' | 'st'
type Filters = { fst: StatusGroup | null; fsrc: string | null; fkind: Family | null; fsev: Severity | null; q: string }
const NO_FILTERS: Filters = { fst: null, fsrc: null, fkind: null, fsev: null, q: '' }
const selectCls = 'h-8 rounded-lg border border-input bg-transparent px-2 text-[13px] dark:bg-input/30'

function useNarrow(q = '(max-width: 1099px)') {
  const [n, setN] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q), f = () => setN(m.matches)
    m.addEventListener('change', f); return () => m.removeEventListener('change', f)
  }, [q])
  return n
}

/** Deep link: ?year=&sel=&fst=&fsrc=&fkind=&fsev=&q= while this view is open. */
function readUrl() {
  const p = new URLSearchParams(location.search)
  return {
    year: p.get('year') ? +p.get('year')! : null, sel: p.get('sel'),
    f: { fst: p.get('fst') as StatusGroup | null, fsrc: p.get('fsrc'), fkind: p.get('fkind') as Family | null, fsev: p.get('fsev') as Severity | null, q: p.get('q') ?? '' },
  }
}

export function FootprintReview() {
  const [fp, setFp] = useState<Footprint | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { loadFootprint().then(setFp).catch((e) => setErr((e as Error).message)) }, [])
  if (err) return (
    <div className="p-6">
      <h2 className="text-[17px]">Data review</h2>
      <p role="alert" className="mt-2 text-[13px] text-reject">Couldn't load the pipeline output: {err}</p>
      <p className="mt-1 text-[13px] text-muted-foreground">Run <span className="num">python -m pipeline run</span> to build the lakehouse, then press Reload outputs in the sidebar.</p>
    </div>
  )
  if (!fp) return <p className="p-6 text-[13px] text-muted-foreground">Loading the pipeline output...</p>
  return <Workbench fp={fp} />
}

function Workbench({ fp }: { fp: Footprint }) {
  const m = useMemo(() => model(fp), [fp])
  const { reviewer } = useApp()
  const { decisions, statusOf, decide, undo, signOff } = useDecisions()
  const narrow = useNarrow()
  const [init] = useState(readUrl)
  const [year, setYear] = useState(() => {
    const s = init.sel ? fp.byId.get(init.sel)?.year : null
    const y = s ?? init.year ?? fp.inv.years[fp.inv.years.length - 1]
    return fp.inv.years.includes(y) ? y : fp.inv.years[fp.inv.years.length - 1]
  })
  const [sel, setSel] = useState<string | null>(init.sel && fp.byId.has(init.sel) ? init.sel : null)
  const [f, setF] = useState<Filters>({ ...NO_FILTERS, ...init.f })
  const [sort, setSort] = useState<{ k: SortKey; d: 1 | -1 }>({ k: 'sev', d: -1 })
  const [page, setPage] = useState(0)
  const [psize, setPsize] = useState(() => +(localStorage.getItem('fp.psize') ?? 25) || 25)
  const [chk, setChk] = useState<Set<string>>(new Set())
  const filter = (p: Partial<Filters>) => { setF((x) => ({ ...x, ...p })); setPage(0) }

  const yearIssues = useMemo(() => fp.iss.issues.filter((i) => i.year === year), [fp, year])
  const list = useMemo(() => {
    let l = yearIssues
    if (f.q) { const q = f.q.toLowerCase(); l = l.filter((i) => `${i.record_key} ${i.type} ${i.table} ${i.evidence} ${typeInfo(i.type).t} ${m.srcName(i.table)} ${i.observed} ${i.proposed}`.toLowerCase().includes(q)) }
    if (f.fst) l = l.filter((i) => STATUS_GROUP[f.fst!].includes(statusOf(i)))
    if (f.fsrc) l = l.filter((i) => i.table === f.fsrc)
    if (f.fkind) l = l.filter((i) => typeInfo(i.type).f === f.fkind)
    if (f.fsev) l = l.filter((i) => m.sevOf(i) === f.fsev)
    const key: Record<SortKey, (i: Issue) => number | string> = {
      sev: (i) => SEV[m.sevOf(i)][1] * 1e12 + Math.max(0, imp(i)), type: (i) => typeInfo(i.type).t,
      src: (i) => `${m.srcName(i.table)} ${String(i.trace.raw.row ?? 0).padStart(9, '0')}`, imp, conf: (i) => num(i.confidence) ? i.confidence : -1,
      st: (i) => ['open', 'overridden', 'accepted', 'auto_applied', 'rejected'].indexOf(statusOf(i)),
    }
    const k = key[sort.k]
    return [...l].sort((a, b) => { const x = k(a), y = k(b); return (typeof x === 'string' ? x.localeCompare(y as string) : x - (y as number)) * sort.d || a.id.localeCompare(b.id) })
  }, [yearIssues, f, sort, m, statusOf])

  const issue = sel ? fp.byId.get(sel) : undefined
  const shown = issue && issue.year === year ? issue : undefined
  const open = useCallback((id: string) => {
    const k = list.findIndex((i) => i.id === id)
    if (k >= 0) setPage(Math.floor(k / psize))
    setSel(id)
  }, [list, psize])

  // keep the URL shareable; clear it when leaving the view
  useEffect(() => {
    const p = new URLSearchParams({ year: String(year) })
    if (shown) p.set('sel', shown.id)
    for (const k of ['fst', 'fsrc', 'fkind', 'fsev', 'q'] as const) if (f[k]) p.set(k, String(f[k]))
    history.replaceState(null, '', `?${p}`)
  }, [year, shown, f])
  useEffect(() => () => history.replaceState(null, '', location.pathname), [])

  // j / k step through the list, Esc closes the panel
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable) return
      if (e.key === 'Escape' && sel) { setSel(null); return }
      if ((e.key !== 'j' && e.key !== 'k') || !list.length) return
      const k = list.findIndex((i) => i.id === sel), n = k < 0 ? 0 : Math.max(0, Math.min(list.length - 1, k + (e.key === 'j' ? 1 : -1)))
      e.preventDefault(); open(list[n].id)
      requestAnimationFrame(() => document.querySelector('[data-selected-issue]')?.scrollIntoView({ block: 'nearest' }))
    }
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey)
  }, [list, sel, open])

  const k = shown ? list.findIndex((i) => i.id === shown.id) : -1
  const panel = shown && (
    <IssuePanel issue={shown} fp={fp} m={m} statusOf={statusOf} decision={decisions[shown.id]}
      position={{ index: k, total: list.length, prev: k > 0 ? list[k - 1].id : null, next: k >= 0 && k < list.length - 1 ? list[k + 1].id : null }}
      onOpen={open} onClose={() => setSel(null)}
      decide={(d, o) => decide([shown], d, reviewer.trim(), o)} undo={() => undo(shown.id)} />
  )

  return (
    <div className="flex h-full min-h-0">
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <Header fp={fp} year={year} setYear={(y) => { setYear(y); setSel(null); setPage(0); setChk(new Set()) }} />
        <div className="space-y-4 px-6 py-4">
          <Summary fp={fp} m={m} year={year} issues={yearIssues} statusOf={statusOf} fst={f.fst} onFst={(g) => filter({ fst: f.fst === g ? null : g })} />
          <Breakdown fp={fp} m={m} year={year} issues={yearIssues} statusOf={statusOf} f={f} filter={filter} />
          <IssueTable m={m} year={year} all={yearIssues} list={list} f={f} filter={filter} sort={sort}
            onSort={(key) => { setSort((s) => s.k === key ? { k: key, d: (s.d * -1) as 1 | -1 } : { k: key, d: key === 'type' || key === 'src' ? 1 : -1 }); setPage(0) }}
            page={page} setPage={setPage} psize={psize} setPsize={(n) => { setPsize(n); localStorage.setItem('fp.psize', String(n)); setPage(0) }}
            selected={shown?.id ?? null} open={open} chk={chk} setChk={setChk} statusOf={statusOf} compact={!!shown && !narrow}
            onBulk={(d, comment) => { decide([...chk].map((id) => fp.byId.get(id)!).filter(Boolean), d, reviewer.trim(), { comment }); setChk(new Set()) }}
            reviewer={reviewer.trim()} />
          <ReviewLog fp={fp} m={m} year={year} decisions={decisions} issues={yearIssues} statusOf={statusOf} undo={undo} open={open}
            signOff={() => signOff(year, reviewer.trim())} reviewer={reviewer.trim()} />
        </div>
      </div>
      {!narrow && shown && <aside aria-label="Issue detail" className="h-full w-[440px] shrink-0 border-l border-border bg-card">{panel}</aside>}
      {narrow && (
        <Sheet open={!!shown} onOpenChange={(o) => !o && setSel(null)}>
          <SheetContent side="right" showCloseButton={false} className="!gap-0 !p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[480px]">
            <SheetTitle className="sr-only">Issue detail</SheetTitle>
            {panel}
          </SheetContent>
        </Sheet>
      )}
    </div>
  )
}

function processingLine(fp: Footprint) {
  const c = (id: string) => fp.run.stages.find((s) => s.id === id)?.counts ?? {}, s3 = c('s3')
  const one = (n: unknown, l: string) => num(n) ? `${fmt(n, 0)} ${l}` : ''
  const fixes = [one(s3.corrections, 'values corrected'), one(s3.excluded, 'duplicates removed'), one(s3.estimated, 'estimates added')].filter(Boolean).join(', ')
  return [one(c('raw').files, 'files read'), one(c('bronze').records, 'records'), one(c('s2').issues, 'issues found (all years)'), fixes, one(c('gold').line_items, 'emission lines calculated')].filter(Boolean).join(' → ')
}

function Header({ fp, year, setYear }: { fp: Footprint; year: number; setYear: (y: number) => void }) {
  const ref = fp.run.stages.find((s) => s.id === 'gold')?.counts.reference_check_ok
  const d = new Date(fp.meta.generated_at ?? fp.meta.started ?? '')
  const a1 = fp.run.quality.find((x) => x.check === 'A1')
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-6 py-3">
      <div className="min-w-0 flex-1">
        <h2 className="text-[17px]">Data review</h2>
        <p className="text-[13px] text-muted-foreground">
          {!isNaN(+d) && <>Data checked {d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} · </>}
          <span className={ref ? 'text-ok' : 'text-reject'}>{ref ? '✓ totals match the reference calculator' : '✗ totals differ from the reference calculator'}</span>
        </p>
        <details className="group mt-0.5">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden">
            <ChevronRight size={12} className="transition-transform group-open:rotate-90" /> Run details
          </summary>
          <p className="mt-1 text-xs">{processingLine(fp)}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Badge className="num">run {fp.meta.run_id}</Badge><Badge className="num">commit {fp.meta.git_commit}</Badge><Badge className="num">inputs {fp.meta.inputs_sha256}</Badge>
            {a1 && <Badge>A1 dev {a1.years} · F1 {fmt(a1.f1, 2)} · score {fmt(a1.score, 1)}</Badge>}
            {fp.run.quality.filter((x) => x.check === 'A2').map((x) => <Badge key={x.years}>A2 {x.years} · {fmt(x.score, 1)}</Badge>)}
          </div>
        </details>
      </div>
      <div role="group" aria-label="Year" className="flex overflow-hidden rounded-lg border border-border">
        {fp.inv.years.map((y) => (
          <button key={y} type="button" onClick={() => setYear(y)} aria-pressed={y === year}
            title={fp.inv.dev_years.includes(y) ? `An answer sheet exists for ${y}` : undefined}
            className={cn('num px-3 py-1 text-[13px] hover:bg-subtle', y === year && 'bg-primary text-primary-foreground hover:bg-primary')}>{y}</button>
        ))}
      </div>
    </header>
  )
}

type Common = { fp: Footprint; m: Model; year: number; issues: Issue[]; statusOf: (i: Issue) => Issue['status'] }

function Summary({ m, year, issues, statusOf, fst, onFst }: Common & { fst: StatusGroup | null; onFst: (g: StatusGroup) => void }) {
  const t0 = m.footprint(year, 't0'), t = m.footprint(year, 't'), ch = num(t0) && num(t) && t0 ? ((t - t0) / t0) * 100 : null
  const mx = Math.max(t0 ?? 0, t ?? 0, 1)
  const cnt = (g: StatusGroup) => issues.filter((i) => STATUS_GROUP[g].includes(statusOf(i))).length
  const card = 'rounded-md border border-border border-l-4 bg-card px-3.5 py-3 text-left'
  const kpi = (g: StatusGroup, accent: string, sub: string) => (
    <button key={g} type="button" onClick={() => onFst(g)} aria-pressed={fst === g}
      className={cn(card, accent, 'hover:bg-subtle', fst === g && 'ring-2 ring-primary/50')}>
      <span className="label block">{GROUP_LABEL[g]}</span>
      <span className="num block text-[22px] leading-tight font-medium">{fmt(cnt(g), 0)}</span>
      <span className="block text-xs text-muted-foreground">{sub}</span>
    </button>
  )
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3">
      <div className={cn(card, 'border-l-primary')}>
        <span className="label block">{year} footprint after fixes</span>
        <span className="num block text-[22px] leading-tight font-medium">{fmtT(t)}</span>
        <span className="block text-xs text-muted-foreground">{num(t0) ? <>{fmtT(t0)} as first recorded{num(ch) && Math.abs(ch) >= 0.5 && ` · ${ch > 0 ? '+' : '−'}${fmt(Math.abs(ch), 0)}%`}</> : 'figure before fixes unavailable'}</span>
        {num(t0) && num(t) && (
          <div className="mt-1.5 space-y-1" role="img" aria-label={`As first recorded ${fmtT(t0)}, after fixes ${fmtT(t)}`}>
            <div className="h-1.5 rounded-full" style={{ width: `${(100 * t0) / mx}%`, background: 'var(--series-2)' }} />
            <div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.max(0.5, (100 * t) / mx)}%` }} />
          </div>
        )}
      </div>
      {kpi('open', 'border-l-warn', "flagged, can't be fixed automatically")}
      {kpi('auto', 'border-l-pending', 'clear mistakes we corrected')}
      {kpi('done', 'border-l-ok', 'approved, changed or kept')}
    </div>
  )
}

function Breakdown({ fp, m, year, issues, statusOf, f, filter }: Common & { f: Filters; filter: (p: Partial<Filters>) => void }) {
  const [kind, setKind] = useState(false)
  const [all, setAll] = useState(false)
  const L = issues.filter((i) => !f.fst || STATUS_GROUP[f.fst].includes(statusOf(i)))
  const g: Record<string, { n: number; open: number; abs: number; net: number }> = {}
  for (const i of L) {
    const key = kind ? typeInfo(i.type).f : i.table, s = (g[key] ??= { n: 0, open: 0, abs: 0, net: 0 }), d = plainDt(i)
    s.n++; if (statusOf(i) === 'open') s.open++; if (num(d)) { s.abs += Math.abs(d); s.net += d }
  }
  const rows = Object.entries(g).sort((a, b) => b[1].abs - a[1].abs || b[1].n - a[1].n), mx = Math.max(1e-9, ...rows.map((r) => r[1].abs)), TOP = 8
  const cur = kind ? f.fkind : f.fsrc
  const label = (k: string) => kind ? FAMILY[k as Family].name : m.srcName(k)
  // what the checks covered but found nothing in this year
  const rules = fp.run.coverage?.rules ?? []
  const clean = [...new Set(rules.map(([t, tb]) => kind ? typeInfo(t).f : tb))].filter((k) => !g[k]).map(label).sort()
  return (
    <section className="rounded-md border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[15px]">Where the changes came from</h3>
        <div role="group" aria-label="Group by" className="flex overflow-hidden rounded-lg border border-border text-[13px]">
          {[['By source', false], ['By kind of mistake', true]].map(([l, v]) => (
            <button key={String(l)} type="button" aria-pressed={kind === v} onClick={() => setKind(v as boolean)}
              className={cn('px-2.5 py-1 hover:bg-subtle', kind === v && 'bg-primary text-primary-foreground hover:bg-primary')}>{l}</button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">Bar length = how much these problems moved the {year} footprint{f.fst && ` (${GROUP_LABEL[f.fst].toLowerCase()} only)`}. Click a row to filter the issue list.</p>
      <ul className="mt-2 space-y-0.5">
        {rows.slice(0, all ? rows.length : TOP).map(([k, s]) => (
          <li key={k}>
            <button type="button" aria-pressed={cur === k} onClick={() => filter(kind ? { fkind: cur === k ? null : (k as Family) } : { fsrc: cur === k ? null : k })}
              className={cn('grid w-full grid-cols-[minmax(120px,210px)_minmax(0,1fr)_minmax(110px,auto)_minmax(110px,auto)] items-center gap-3 rounded-sm px-1.5 py-1 text-left text-[13px] hover:bg-subtle max-sm:grid-cols-[minmax(0,1fr)_auto]', cur === k && 'bg-subtle font-medium')}>
              <span className="truncate">{label(k)}</span>
              <span className="h-2 overflow-hidden rounded-full bg-subtle max-sm:col-span-2 max-sm:row-start-2"><span className="block h-full rounded-full bg-primary" style={{ width: `${s.abs >= 0.5 ? Math.max(1, (100 * s.abs) / mx) : 0}%` }} /></span>
              <span className="num text-right font-medium whitespace-nowrap max-sm:row-start-1 max-sm:col-start-2">{s.abs >= 0.5 ? sgnT(s.net) : 'no change'}</span>
              <span className="text-right text-xs text-muted-foreground max-sm:col-span-2 max-sm:text-left">{s.n} issue{s.n === 1 ? '' : 's'}{s.open > 0 && <> · <span className="font-medium text-warn">{s.open} open</span></>}</span>
            </button>
          </li>
        ))}
        {!rows.length && <li className="text-[13px] text-muted-foreground">No issues.</li>}
      </ul>
      {rows.length > TOP && <Button variant="link" size="sm" className="mt-1 h-auto px-0" onClick={() => setAll(!all)}>{all ? `Show top ${TOP}` : `Show all ${rows.length}`}</Button>}
      {!f.fst && clean.length > 0 && <p className="mt-1.5 text-xs text-muted-foreground">Also checked in {year}, nothing found: {clean.join(', ')}.</p>}
    </section>
  )
}

const COLS: [SortKey, string, string?][] = [['sev', 'Severity'], ['type', 'Problem'], ['src', 'Source'], ['imp', 'Impact', 'text-right'], ['conf', 'Confidence', 'text-right'], ['st', 'Status']]

function IssueTable({ m, year, all, list, f, filter, sort, onSort, page, setPage, psize, setPsize, selected, open, chk, setChk, statusOf, compact, onBulk, reviewer }: {
  m: Model; year: number; all: Issue[]; list: Issue[]; f: Filters; filter: (p: Partial<Filters>) => void
  sort: { k: SortKey; d: number }; onSort: (k: SortKey) => void; page: number; setPage: (n: number) => void; psize: number; setPsize: (n: number) => void
  selected: string | null; open: (id: string) => void; chk: Set<string>; setChk: (s: Set<string>) => void; statusOf: (i: Issue) => Issue['status']
  compact: boolean; onBulk: (d: 'accept' | 'reject', comment?: string) => void; reviewer: string
}) {
  const [reason, setReason] = useState<string | null>(null)
  const pages = Math.max(1, Math.ceil(list.length / psize)), p = Math.min(page, pages - 1), rows = list.slice(p * psize, (p + 1) * psize)
  const srcs = useMemo(() => [...new Set(all.map((i) => i.table))].sort((a, b) => m.srcName(a).localeCompare(m.srcName(b))), [all, m])
  const pageAll = rows.length > 0 && rows.every((i) => chk.has(i.id))
  const toggle = (ids: string[], on: boolean) => { const n = new Set(chk); ids.forEach((id) => on ? n.add(id) : n.delete(id)); setChk(n) }
  const chips: [keyof Filters, string][] = []
  if (f.fst) chips.push(['fst', GROUP_LABEL[f.fst]])
  if (f.fsrc) chips.push(['fsrc', `Source: ${m.srcName(f.fsrc)}`])
  if (f.fkind) chips.push(['fkind', FAMILY[f.fkind].name])
  if (f.fsev) chips.push(['fsev', `Severity: ${SEV[f.fsev][0]}`])
  if (f.q) chips.push(['q', `“${f.q}”`])
  const exportCsv = () => {
    const head = ['severity', 'problem', 'kind_of_mistake', 'source', 'file', 'row', 'year', 'field', 'recorded_value', 'proposed_value', 'impact_tco2e', 'confidence', 'status', 'issue_id', 'record_key']
    const c = (v: unknown) => v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v)
    const body = list.map((i) => { const d = plainDt(i); return [SEV[m.sevOf(i)][0], typeInfo(i.type).t, FAMILY[typeInfo(i.type).f].name, m.srcName(i.table), i.trace.raw.file, i.trace.raw.row, i.year, i.field, i.observed, i.proposed, num(d) ? +d.toFixed(3) : '', i.confidence, PLAIN_STATUS[statusOf(i)][0], i.id, i.record_key] })
    download(`issues_${year}.csv`, [head, ...body].map((r) => r.map(c).join(',')).join('\n'), 'text/csv')
  }
  const nSel = chk.size
  return (
    <section className="rounded-md border border-border bg-card">
      <div className="space-y-2 px-4 pt-3 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-[15px]">Issues <span className="num text-[13px] font-normal text-muted-foreground">{fmt(list.length, 0)} of {fmt(all.length, 0)} in {year}</span></h3>
          <Button size="sm" variant="outline" disabled={!list.length} onClick={exportCsv}><Download /> Export CSV</Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <form className="min-w-[200px] flex-1" onSubmit={(e) => { e.preventDefault(); filter({ q: String(new FormData(e.currentTarget).get('q') ?? '').trim() }) }}>
            <Input key={f.q} name="q" type="search" defaultValue={f.q} onBlur={(e) => e.target.value.trim() !== f.q && filter({ q: e.target.value.trim() })}
              placeholder="Search problems, sources, values..." aria-label="Search issues" className="h-8 text-[13px]" />
          </form>
          <select aria-label="Status" className={selectCls} value={f.fst ?? ''} onChange={(e) => filter({ fst: (e.target.value || null) as StatusGroup | null })}>
            <option value="">All statuses</option>{(Object.keys(GROUP_LABEL) as StatusGroup[]).map((g) => <option key={g} value={g}>{GROUP_LABEL[g]}</option>)}
          </select>
          <select aria-label="Severity" className={selectCls} value={f.fsev ?? ''} onChange={(e) => filter({ fsev: (e.target.value || null) as Severity | null })}>
            <option value="">All severities</option>{(Object.keys(SEV) as Severity[]).map((k) => <option key={k} value={k}>{SEV[k][0]}</option>)}
          </select>
          <select aria-label="Source" className={selectCls} value={f.fsrc ?? ''} onChange={(e) => filter({ fsrc: e.target.value || null })}>
            <option value="">All sources</option>
            {srcs.map((s) => <option key={s} value={s}>{m.srcName(s)}</option>)}
          </select>
          <select aria-label="Kind of mistake" className={selectCls} value={f.fkind ?? ''} onChange={(e) => filter({ fkind: (e.target.value || null) as Family | null })}>
            <option value="">All kinds of mistake</option>{FAMILY_ORDER.map((k) => <option key={k} value={k}>{FAMILY[k].name}</option>)}
          </select>
        </div>
        {chips.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">Filtered by</span>
            {chips.map(([k, l]) => (
              <span key={k} className="inline-flex items-center gap-1 rounded-full border border-border bg-subtle py-0.5 pr-1 pl-2.5">
                {l}<button type="button" aria-label={`Remove filter ${l}`} className="rounded-full p-0.5 hover:bg-background" onClick={() => filter({ [k]: k === 'q' ? '' : null })}><X size={12} /></button>
              </span>
            ))}
            <Button variant="link" size="xs" className="h-auto px-1" onClick={() => filter(NO_FILTERS)}>Clear all</Button>
          </div>
        )}
        {nSel > 0 && (
          <div role="region" aria-label="Bulk actions" className="flex flex-wrap items-center gap-2 rounded-md bg-subtle px-3 py-1.5 text-[13px]">
            <b className="font-medium">{nSel} selected</b>
            {reason === null ? (<>
              <Button size="sm" disabled={!reviewer} title={reviewer ? undefined : 'Enter your name in the sidebar'} onClick={() => onBulk('accept', 'Approved in bulk')}>Approve</Button>
              <Button size="sm" variant="outline" disabled={!reviewer} onClick={() => setReason('')}>Keep original...</Button>
              <Button size="sm" variant="ghost" onClick={() => setChk(new Set())}>Clear selection</Button>
              {!reviewer && <span className="text-xs text-muted-foreground">Enter your name in the sidebar to record decisions.</span>}
            </>) : (
              <form className="flex flex-1 flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) { onBulk('reject', reason.trim()); setReason(null) } }}>
                <Input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder={`Why keep the original values for ${nSel} issue${nSel === 1 ? '' : 's'}?`} className="h-7 min-w-[220px] flex-1 text-[13px]" />
                <Button size="sm" type="submit" disabled={!reason.trim()}>Keep original</Button>
                <Button size="sm" variant="ghost" type="button" onClick={() => setReason(null)}>Cancel</Button>
              </form>
            )}
          </div>
        )}
      </div>
      <Table className="text-[13px]">
        <TableHeader>
          <TableRow>
            <TableHead className="h-8 w-8 pl-4"><input type="checkbox" className="accent-primary" aria-label="Select all on this page" checked={pageAll} onChange={(e) => toggle(rows.map((i) => i.id), e.target.checked)} /></TableHead>
            {COLS.filter(([k]) => !(compact && k === 'conf')).map(([key, l, cls]) => (
              <TableHead key={key} className={cn('label h-8', cls)} aria-sort={sort.k === key ? (sort.d < 0 ? 'descending' : 'ascending') : 'none'}>
                <button type="button" onClick={() => onSort(key)} className="inline-flex items-center gap-0.5 uppercase">{l}{sort.k === key && <ChevronDown size={12} className={cn(sort.d > 0 && 'rotate-180')} />}</button>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((i) => {
            const d = plainDt(i), st = statusOf(i), sev = m.sevOf(i), on = selected === i.id
            return (
              <TableRow key={i.id} onClick={() => open(i.id)} data-selected-issue={on || undefined} data-state={on ? 'selected' : undefined} className="cursor-pointer">
                <TableCell className="pl-4" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" className="accent-primary" aria-label="Select this issue" checked={chk.has(i.id)} onChange={(e) => toggle([i.id], e.target.checked)} />
                </TableCell>
                <TableCell><Badge variant={SEV[sev][2]}>{SEV[sev][0]}</Badge></TableCell>
                <TableCell className="max-w-[340px] whitespace-normal"><span className="font-medium">{typeInfo(i.type).t}</span><span className="block truncate text-xs text-muted-foreground" title={changeText(i)}>{changeText(i)}</span></TableCell>
                <TableCell className="whitespace-normal">{m.srcName(i.table)}<span className="block text-xs text-muted-foreground">{rowLabel(i)}</span></TableCell>
                <TableCell className="num text-right">{num(d) && Math.abs(d) >= 0.5 ? sgnT(d) : '—'}</TableCell>
                {!compact && <TableCell className="num text-right">{num(i.confidence) ? `${Math.round(i.confidence * 100)}%` : '—'}</TableCell>}
                <TableCell><Badge variant={PLAIN_STATUS[st][1]}>{PLAIN_STATUS[st][0]}</Badge></TableCell>
              </TableRow>
            )
          })}
          {!rows.length && <TableRow><TableCell colSpan={7} className="px-4 py-6 text-muted-foreground">No issues match these filters.</TableCell></TableRow>}
        </TableBody>
      </Table>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={p === 0} onClick={() => setPage(p - 1)}><ChevronLeft /> Previous</Button>
          <span className="num text-xs text-muted-foreground">{list.length ? `${p * psize + 1}–${Math.min(list.length, (p + 1) * psize)} of ${fmt(list.length, 0)}` : '0 of 0'}</span>
          <Button size="sm" variant="outline" disabled={p >= pages - 1} onClick={() => setPage(p + 1)}>Next <ChevronRight /></Button>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="max-sm:hidden">Keys: <kbd className="num rounded border border-border px-1">j</kbd>/<kbd className="num rounded border border-border px-1">k</kbd> next/previous, <kbd className="num rounded border border-border px-1">Esc</kbd> close</span>
          <select aria-label="Rows per page" className={selectCls} value={psize} onChange={(e) => setPsize(+e.target.value)}>
            {[25, 50, 100].map((n) => <option key={n} value={n}>{n} per page</option>)}
          </select>
        </div>
      </div>
    </section>
  )
}

function ReviewLog({ fp, m, year, decisions, issues, statusOf, undo, open, signOff, reviewer }: Common & {
  decisions: ReturnType<typeof useDecisions>['decisions']; undo: (id: string) => void; open: (id: string) => void; signOff: () => void; reviewer: string
}) {
  const [showAll, setShowAll] = useState(false)
  const all = Object.values(decisions)
  const ds = all.filter((d) => d._year === year).sort((a, b) => b.decided_at.localeCompare(a.decided_at) || b.decision_id.localeCompare(a.decision_id))
  const iss = ds.filter((d) => d.issue_id), t = m.footprint(year, 't')
  const undone = iss.filter((d) => d.decision === 'reject' && ['auto_applied', 'accepted'].includes(fp.byId.get(d.issue_id!)?.status ?? ''))
  const back = undone.reduce((a, d) => a + (plainDt(fp.byId.get(d.issue_id!)!) ?? 0), 0), ov = iss.filter((d) => d.decision === 'override').length
  const openN = issues.filter((i) => statusOf(i) === 'open').length
  const what = (d: (typeof ds)[number]) => d.decision === 'sign_off' ? `Marked ${d.override_value} as reviewed` : d.decision === 'accept' ? 'Approved' : d.decision === 'reject' ? 'Kept original' : `Changed to ${d.override_value}`
  return (
    <section className="rounded-md border border-border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[15px]">Review log</h3>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={!reviewer} title={reviewer ? (openN ? `${openN} still need a decision` : undefined) : 'Enter your name in the sidebar'} onClick={signOff}>
            Mark {year} as reviewed{openN > 0 && ` (${openN} open)`}
          </Button>
          <Button size="sm" disabled={!all.length} onClick={() => exportDecisions(decisions)}><Download /> Download decisions{all.length > 0 && ` (${all.length})`}</Button>
        </div>
      </div>
      <p className="mt-1.5 text-[13px]">
        {!iss.length ? `No decisions for ${year} yet.` : `${iss.length} decision${iss.length === 1 ? '' : 's'} for ${year}.`}
        {iss.length > 0 && (undone.length && num(t) ? <> If the data team applies them, the {year} footprint would be about <b className="font-semibold">{fmtT(t - back)}</b> instead of {fmtT(t)}.</> : " They don't change the footprint figures.")}
        {ov > 0 && ` ${ov} typed-in value${ov === 1 ? "" : "s"} ${ov === 1 ? "isn't" : "aren't"} included in this estimate.`}
      </p>
      <p className="text-xs text-muted-foreground">Decisions are saved in this browser until you download them. Send the file to the data team; they apply it and refresh the numbers.</p>
      {ds.length > 0 && (
        <ul className="mt-2 space-y-1.5 border-l-2 border-primary/40 pl-3">
          {ds.slice(0, showAll ? ds.length : 8).map((d) => {
            const i = d.issue_id ? fp.byId.get(d.issue_id) : undefined
            return (
              <li key={d.decision_id + (d.issue_id ?? '')} className="text-[13px]">
                <span className="font-medium">{what(d)}</span>
                {i && <> <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => open(i.id)}>{typeInfo(i.type).t} · {m.srcName(i.table)}, {rowLabel(i).toLowerCase()}</button></>}
                {d.comment && <span className="text-muted-foreground"> · “{d.comment}”</span>}
                <span className="block text-xs text-muted-foreground">{d.reviewer} · <span className="num">{fmtTime(d.decided_at)}</span>
                  {i && <> · <button type="button" className="underline-offset-2 hover:underline" onClick={() => undo(i.id)}>undo</button></>}</span>
              </li>
            )
          })}
        </ul>
      )}
      {ds.length > 8 && <Button variant="link" size="sm" className="h-auto px-0" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : `Show all ${ds.length}`}</Button>}
      <details className="group mt-2">
        <summary className="flex cursor-pointer list-none items-center gap-1 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden">
          <ChevronRight size={12} className="transition-transform group-open:rotate-90" /> For the data team: applying the file
        </summary>
        <p className="mt-1 text-xs">Run <span className="num">python -m pipeline review review_decisions.json</span>, then <span className="num">python -m pipeline run</span>.</p>
        {(fp.run.reviews ?? []).length > 0 && <p className="text-xs text-muted-foreground">{fp.run.reviews!.length} decisions already applied by the pipeline.</p>}
      </details>
    </section>
  )
}
