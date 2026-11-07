import { useEffect, useState } from 'react'
import { useAui } from '@assistant-ui/react'
import { Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useApp } from '@/lib/app'
import { Badge } from '@/components/ui/badge'
import { ChartCard, type Chart } from '@/components/charts'
import { cn } from '@/lib/utils'

type Payload = { year: number; pages: Record<string, string[]>; charts: Record<string, Chart> }
const TABS: [string, string][] = [['overview', 'Overview'], ['drivers', 'What drives it'], ['farms', 'Farm to freezer'], ['trust', 'Can we trust it?'], ['target', 'Getting to target']]
const YEARS = [2025, 2024, 2023, 2022, 2021]
const WIDE = new Set(['kpis', 'levers', 'corrections', 'issues_by_type'])

export function Dashboard() {
  const { setView } = useApp()
  const aui = useAui()
  const [year, setYear] = useState(2025)
  const [tab, setTab] = useState('overview')
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    api<Payload>(`/api/dashboard?year=${year}`).then((d) => { if (live) { setData(d); setError('') } }).catch((e) => live && setError((e as Error).message))
    return () => { live = false }
  }, [year])

  const ask = (c: Chart) => {
    setView('ask')
    aui.thread().append({ role: 'user', content: [{ type: 'text', text: `Explain the "${c.title}" chart for ${c.year ?? year}: what does it mean and what should we do?` }] })
  }
  const status = data?.charts.kpis?.status
  const loading = !error && (!data || data.year !== year)

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6">
        <header className="flex flex-wrap items-center gap-3">
          <h2 className="text-lg">Climate dashboard</h2>
          {status && <Badge variant={status === 'published' ? 'ok' : 'warn'}>{status === 'published' ? 'Published' : 'Draft, not signed off'}</Badge>}
          <label className="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
            Year
            <select value={year} onChange={(e) => { setError(''); setYear(+e.target.value) }} className="h-8 rounded-md border border-border bg-card px-2 text-sm text-foreground">
              {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
        </header>
        <div role="tablist" aria-label="Dashboard pages" className="mt-4 flex gap-1 overflow-x-auto border-b border-border">
          {TABS.map(([k, label]) => (
            <button key={k} role="tab" type="button" aria-selected={tab === k} onClick={() => setTab(k)}
              className={cn('-mb-px shrink-0 border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground', tab === k && 'border-primary font-medium text-primary')}>
              {label}
            </button>
          ))}
        </div>
        {error && <p role="alert" className="mt-4 rounded-md border border-reject/30 bg-reject/10 px-3 py-2 text-sm text-reject">{error}</p>}
        {loading && <p role="status" className="mt-6 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 size={14} className="animate-spin motion-reduce:animate-none" /> Loading charts…</p>}
        {data && !loading && (
          <div role="tabpanel" className="mt-4 grid grid-flow-row-dense gap-4 lg:grid-cols-2">
            {(data.pages[tab] ?? []).map((id) => (
              <div key={id} className={cn('min-w-0', WIDE.has(id) && 'lg:col-span-2')}>
                <ChartCard chart={data.charts[id]} onAsk={() => ask(data.charts[id])} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
