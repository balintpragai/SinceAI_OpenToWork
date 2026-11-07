import { useState, type ReactNode } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { MessageCircleQuestion, TriangleAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

type Row = Record<string, any>
export type Chart = {
  id: string; title: string; kind: string; unit: string; rows: Row[]; year: number | null; status: string | null
  sources: string[]; note?: string | null; trust?: { measured_pct: number; estimated_pct: number; review_pct: number }
  series?: string[]; error?: string
}

// Fixed categorical order (dataviz palette); colour follows the series, never its rank.
const S = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)']
const WARN = 'var(--status-warning)'
const INK = 'var(--muted-foreground)'
const GRID = 'var(--border)'

const fmt = (v: unknown) =>
  typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v == null ? '–' : String(v)

const axis = { tick: { fill: INK, fontSize: 12 }, stroke: GRID, tickLine: false }
const tip = (
  <Tooltip
    formatter={(v) => fmt(v)}
    cursor={{ fill: 'var(--subtle)' }}
    contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, color: 'var(--foreground)' }}
    labelStyle={{ color: 'var(--foreground)', fontWeight: 500 }}
  />
)
const legend = <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} formatter={(v) => <span style={{ color: INK }}>{v}</span>} />
const short = (v: number) => Math.abs(v) >= 1e6 ? `${+(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `${+(v / 1e3).toFixed(0)}k` : String(v)

function Box({ h, children }: { h: number; children: ReactNode }) {
  return <div style={{ height: h }} className="w-full min-w-0"><ResponsiveContainer>{children as any}</ResponsiveContainer></div>
}

/** Labelled segmented 100 % bar (trust strip, land-use split). */
function Segments({ parts }: { parts: { label: string; pct: number; color: string; icon?: boolean }[] }) {
  return (
    <div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded-[4px]" role="img" aria-label={parts.map((p) => `${p.pct} % ${p.label}`).join(', ')}>
        {parts.filter((p) => p.pct > 0).map((p) => <div key={p.label} style={{ width: `${p.pct}%`, background: p.color }} title={`${p.label}: ${p.pct} %`} />)}
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-1.5">
            {p.icon ? <TriangleAlert size={12} style={{ color: p.color }} aria-hidden /> : <span className="size-2 rounded-full" style={{ background: p.color }} />}
            <span className="num text-foreground">{fmt(p.pct)} %</span> {p.label}
          </li>
        ))}
      </ul>
    </div>
  )
}

function hbarHeight(n: number) { return Math.max(140, n * 30 + 30) }

function Plot({ c }: { c: Chart }) {
  const rows = c.rows
  const series = c.series ?? []
  switch (c.kind) {
    case 'kpis':
      return (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {rows.map((r) => (
              <div key={r.label} className="rounded-md border border-border p-3">
                <div className="text-xs text-muted-foreground">{r.label}</div>
                <div className="num mt-1 text-2xl font-medium">
                  {r.unit === '%' && typeof r.value === 'number' && r.value > 0 ? '+' : ''}{fmt(r.value)}
                  <span className="ml-1 text-xs font-normal text-muted-foreground">{r.unit}</span>
                </div>
              </div>
            ))}
          </div>
          {c.trust && (
            <div>
              <div className="label mb-1.5">How the total was measured</div>
              <Segments parts={[
                { label: 'measured', pct: c.trust.measured_pct, color: S[0] },
                { label: 'estimated', pct: c.trust.estimated_pct, color: S[1] },
                { label: 'needs review', pct: c.trust.review_pct, color: WARN, icon: true },
              ]} />
            </div>
          )}
        </div>
      )
    case 'split_bar':
      return <Segments parts={rows.map((r, i) => ({ label: `${r.label} (${fmt(r.value)} ${c.unit})`, pct: r.pct, color: S[i] }))} />
    case 'donut':
      return (
        <div className="flex flex-wrap items-center gap-4">
          <div className="h-[200px] w-[200px] shrink-0">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={rows} dataKey="value" nameKey="label" innerRadius={58} outerRadius={92} stroke="var(--card)" strokeWidth={2} isAnimationActive={false}>
                  {rows.map((r, i) => <Cell key={r.label} fill={S[i]} />)}
                </Pie>
                {tip}
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="space-y-2 text-sm">
            {rows.map((r, i) => (
              <li key={r.label} className="flex items-center gap-2">
                <span className="size-2.5 rounded-full" style={{ background: S[i] }} />
                <span>{r.label}</span><span className="num text-muted-foreground">{fmt(r.value)} {c.unit} · {fmt(r.pct)} %</span>
              </li>
            ))}
          </ul>
        </div>
      )
    case 'stacked_bar':
      return (
        <Box h={280}>
          <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="year" {...axis} />
            <YAxis {...axis} tickFormatter={short} width={48} />
            {tip}{legend}
            {series.map((s, i) => (
              <Bar key={s} dataKey={s} stackId="a" fill={S[i]} stroke="var(--card)" strokeWidth={1}
                radius={i === series.length - 1 ? [4, 4, 0, 0] : 0} isAnimationActive={false} />
            ))}
            <Scatter dataKey="Previously published" fill="var(--foreground)" shape="circle" isAnimationActive={false} />
          </ComposedChart>
        </Box>
      )
    case 'hbar':
    case 'lever_bars': {
      const lever = c.kind === 'lever_bars'
      const data: Row[] = lever ? rows.map((r) => ({ ...r, label: `${r.label} · €${fmt(r.cost)}/t` })) : rows
      return (
        <>
          <Box h={hbarHeight(rows.length)}>
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, left: 0, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="label" {...axis} width={lever ? 280 : 200} interval={0} tick={{ fill: INK, fontSize: 11.5 }} />
              {tip}
              <Bar dataKey="value" name={c.unit} fill={S[0]} radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false}>
                {lever && data.map((r) => <Cell key={r.label} fill={r.cost <= 0 ? S[2] : S[0]} />)}
                <LabelList dataKey="value" position="right" formatter={(v: any) => fmt(v)} style={{ fill: INK, fontSize: 11 }} />
              </Bar>
            </BarChart>
          </Box>
          {lever && (
            <ul className="mt-2 flex gap-4 text-xs text-muted-foreground">
              <li className="flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: S[2] }} />Saves money</li>
              <li className="flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: S[0] }} />Costs money (€ per tonne shown)</li>
            </ul>
          )}
        </>
      )
    }
    case 'hbar_stacked': {
      const outcomes = series
      const byLabel = new Map<string, Row>()
      for (const r of rows) byLabel.set(r.label, { ...(byLabel.get(r.label) ?? { label: r.label }), [r.outcome]: r.value })
      const data = [...byLabel.values()]
      const color = (o: string) => (o === 'Needs expert review' ? WARN : S[outcomes.indexOf(o)])
      return (
        <>
          <Box h={hbarHeight(data.length)}>
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="label" {...axis} width={210} interval={0} tick={{ fill: INK, fontSize: 11.5 }} />
              {tip}
              {outcomes.map((o) => <Bar key={o} dataKey={o} stackId="a" fill={color(o)} stroke="var(--card)" strokeWidth={1} barSize={16} isAnimationActive={false} />)}
            </BarChart>
          </Box>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {outcomes.map((o) => (
              <li key={o} className="flex items-center gap-1.5">
                {o === 'Needs expert review' ? <TriangleAlert size={12} style={{ color: WARN }} aria-hidden /> : <span className="size-2 rounded-full" style={{ background: color(o) }} />}
                {o}
              </li>
            ))}
          </ul>
        </>
      )
    }
    case 'waterfall': {
      // running total before each row: totals reset it, deltas float from it
      const before = rows.map((_, i) => rows.slice(0, i).reduce((acc, r) => (r.type === 'total' ? r.value : acc + r.value), 0))
      const data = rows.map((r, i) => r.type === 'total'
        ? { label: r.label, base: 0, bar: r.value, value: r.value, kind: 'Total' }
        : { label: r.label, base: Math.min(before[i], before[i] + r.value), bar: Math.abs(r.value), value: r.value, kind: r.value < 0 ? 'Decrease' : 'Increase' })
      const col = { Total: S[0], Decrease: S[2], Increase: S[1] } as Record<string, string>
      return (
        <>
          <Box h={300}>
            <BarChart data={data} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="label" {...axis} interval={0} tick={{ fill: INK, fontSize: 11, width: 72 } as any} height={64} />
              <YAxis {...axis} tickFormatter={short} width={52} />
              <Tooltip
                formatter={(_v, _n, p: any) => [fmt(p.payload.value), p.payload.kind]}
                cursor={{ fill: 'var(--subtle)' }}
                contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, color: 'var(--foreground)' }}
              />
              <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
              <Bar dataKey="bar" stackId="w" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                {data.map((d) => <Cell key={d.label} fill={col[d.kind]} />)}
                <LabelList dataKey="value" position="top" formatter={(v: any) => short(v)} style={{ fill: INK, fontSize: 11 }} />
              </Bar>
            </BarChart>
          </Box>
          <ul className="mt-1 flex gap-4 text-xs text-muted-foreground">
            {Object.entries(col).map(([k, v]) => <li key={k} className="flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: v }} />{k}</li>)}
          </ul>
        </>
      )
    }
    case 'grouped_bar':
      return (
        <Box h={260}>
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="year" {...axis} />
            <YAxis {...axis} tickFormatter={short} width={48} />
            {tip}{legend}
            {series.map((s, i) => <Bar key={s} dataKey={s} fill={S[i]} radius={[4, 4, 0, 0]} isAnimationActive={false} />)}
          </BarChart>
        </Box>
      )
    case 'line':
      return (
        <Box h={260}>
          <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="year" {...axis} />
            <YAxis {...axis} tickFormatter={short} width={48} />
            {tip}{legend}
            {series.map((s, i) => (
              <Line key={s} dataKey={s} stroke={S[i]} strokeWidth={2} strokeDasharray={/target/i.test(s) ? '5 4' : undefined}
                dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
            ))}
          </LineChart>
        </Box>
      )
    case 'scatter_map': {
      const soils = [...new Set(rows.map((r) => r.soil))].sort()
      return (
        <Box h={340}>
          <ScatterChart margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={GRID} />
            <XAxis type="number" dataKey="lon" name="Longitude" domain={['dataMin - 0.1', 'dataMax + 0.1']} {...axis} tickFormatter={(v) => `${(+v).toFixed(1)}°E`} />
            <YAxis type="number" dataKey="lat" name="Latitude" domain={['dataMin - 0.1', 'dataMax + 0.1']} {...axis} tickFormatter={(v) => `${(+v).toFixed(1)}°N`} width={52} />
            <ZAxis type="number" dataKey="value" range={[16, 320]} name={c.unit} />
            {tip}{legend}
            {soils.map((s) => <Scatter key={s} name={s} data={rows.filter((r) => r.soil === s)} fill={S[['No peat soil', 'Some peat soil', 'Mostly peat soil'].indexOf(s)] ?? S[0]} fillOpacity={0.75} stroke="var(--card)" isAnimationActive={false} />)}
          </ScatterChart>
        </Box>
      )
    }
    default:
      return <p className="text-sm text-muted-foreground">This chart type ({c.kind}) is not supported yet.</p>
  }
}

function DataTable({ rows }: { rows: Row[] }) {
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))]
  return (
    <div className="max-h-80 overflow-auto">
      <Table>
        <TableHeader><TableRow>{cols.map((k) => <TableHead key={k}>{k}</TableHead>)}</TableRow></TableHeader>
        <TableBody>
          {rows.map((r, i) => <TableRow key={i}>{cols.map((k) => <TableCell key={k} className={typeof r[k] === 'number' ? 'num' : ''}>{fmt(r[k])}</TableCell>)}</TableRow>)}
        </TableBody>
      </Table>
    </div>
  )
}

export function ChartCard({ chart: c, onAsk }: { chart: Chart; onAsk?: () => void }) {
  const [table, setTable] = useState(false)
  if (!c || c.error) return <div className="rounded-md border border-border bg-card p-4 text-sm text-muted-foreground">Chart unavailable: {c?.error ?? 'no data'}</div>
  const empty = !c.rows?.length
  return (
    <section className="flex min-w-0 flex-col rounded-md border border-border bg-card p-4" aria-label={c.title}>
      <h3 className="text-[15px] leading-snug">{c.title}</h3>
      {c.kind !== 'kpis' && <p className="mt-0.5 text-xs text-muted-foreground">{c.unit}{c.year ? ` · ${c.year}` : ''}</p>}
      <div className="mt-3 min-w-0">
        {empty ? <p className="text-sm text-muted-foreground">No data for this view.</p> : table ? <DataTable rows={c.rows} /> : <Plot c={c} />}
      </div>
      {c.note && <p className="mt-3 text-xs text-muted-foreground">{c.note}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-3 text-xs text-muted-foreground">
        {c.status && <>How sure: <Badge variant={c.status === 'published' ? 'ok' : 'warn'}>{c.status === 'published' ? 'Published' : 'Draft'}</Badge> ·</>}
        <span>Sources: {c.sources.join(' · ')}</span>
        <span className="ml-auto flex gap-1">
          {!empty && <Button variant="ghost" size="sm" onClick={() => setTable(!table)} aria-pressed={table}>{table ? 'Show chart' : 'Show as table'}</Button>}
          {onAsk && <Button variant="outline" size="sm" onClick={onAsk}><MessageCircleQuestion /> Ask about this</Button>}
        </span>
      </div>
    </section>
  )
}
