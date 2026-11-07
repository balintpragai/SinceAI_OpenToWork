import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useApp } from '@/lib/app'
import { useConversations } from '@/components/Chat'
import { Badge } from '@/components/ui/badge'
import { ChartCard, type Chart } from '@/components/charts'
import { cn } from '@/lib/utils'

type Section = { id: string; title: string; intro: string; charts: string[] }
type Payload = { year: number; sections: Section[]; charts: Record<string, Chart> }
const YEARS = [2025, 2024, 2023, 2022, 2021]
const WIDE = new Set(['kpis', 'farm_summary', 'corrections', 'issues_by_type', 'levers'])

export function Dashboard() {
  const { setView } = useApp()
  const { askNew } = useConversations()
  const [year, setYear] = useState(2025)
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState('')
  const [active, setActive] = useState('')
  const scroller = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let live = true
    api<Payload>(`/api/dashboard?year=${year}`).then((d) => { if (live) { setData(d); setError('') } }).catch((e) => live && setError((e as Error).message))
    return () => { live = false }
  }, [year])

  const loading = !error && (!data || data.year !== year)
  // scroll-spy: highlight the section nearest the top of the viewport
  useEffect(() => {
    if (!data || loading || !scroller.current) return
    const obs = new IntersectionObserver((es) => {
      const vis = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (vis[0]) setActive(vis[0].target.id)
    }, { root: scroller.current, rootMargin: '-120px 0px -60% 0px' })
    data.sections.forEach((s) => { const el = document.getElementById(s.id); if (el) obs.observe(el) })
    return () => obs.disconnect()
  }, [data, loading])

  const go = (id: string) => {
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    document.getElementById(id)?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
    setActive(id)
  }
  const ask = (c: Chart) => {
    setView('ask')
    askNew(`Explain the chart "${c.title}"${c.year ? ` (${c.year})` : ''}: key drivers and recommended actions.`)
  }
  const status = data?.charts.kpis?.status

  return (
    <div ref={scroller} className="h-full overflow-y-auto">
      <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 pt-3 sm:px-6">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h2 className="text-base">Climate &amp; Nature Dashboard</h2>
            {status && <Badge variant={status === 'published' ? 'ok' : 'warn'}>{status === 'published' ? 'Published' : 'Draft – not signed off'}</Badge>}
            <label className="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
              Reporting year
              <select value={year} onChange={(e) => { setError(''); setYear(+e.target.value) }} className="h-8 rounded-md border border-border bg-card px-2 text-sm text-foreground">
                {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
          </div>
          <nav aria-label="Dashboard sections" className="mt-2 flex gap-1 overflow-x-auto">
            {(data?.sections ?? []).map((s) => (
              <a key={s.id} href={`#${s.id}`} onClick={(e) => { e.preventDefault(); go(s.id) }} aria-current={active === s.id ? 'location' : undefined}
                className={cn('-mb-px shrink-0 whitespace-nowrap border-b-2 border-transparent px-2.5 py-2 text-sm text-muted-foreground hover:text-foreground', active === s.id && 'border-primary font-medium text-primary')}>
                {s.title}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-4 pb-10 sm:px-6">
        {error && <p role="alert" className="mt-4 rounded-md border border-reject/30 bg-reject/10 px-3 py-2 text-sm text-reject">{error}</p>}
        {loading && <p role="status" className="mt-6 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 size={14} className="animate-spin motion-reduce:animate-none" /> Loading dashboard…</p>}
        {data && !loading && data.sections.map((s) => (
          <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="scroll-mt-28 pt-6">
            <h2 id={`${s.id}-h`} className="text-[17px]">{s.title}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{s.intro}</p>
            <div className="mt-3 grid grid-flow-row-dense gap-4 lg:grid-cols-2">
              {s.charts.map((id) => (
                <div key={id} className={cn('min-w-0', WIDE.has(id) && 'lg:col-span-2')}>
                  <ChartCard chart={data.charts[id]} onAsk={() => ask(data.charts[id])} />
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
