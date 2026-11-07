import { Moon, Plus, Sun } from 'lucide-react'
import { fmtAgo } from '@/lib/api'
import { useApp, type View } from '@/lib/app'
import { useConversations } from '@/components/Chat'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const NAV: [View, string][] = [['dashboard', 'Dashboard'], ['review', 'Data review'], ['ask', 'Ask'], ['sheet', 'Answer sheet'], ['audit', 'Audit log']]

export function Sidebar() {
  const { view, setView, status, statusError, reloadOutputs, reloading, reviewer, setReviewer, dark, toggleTheme } = useApp()
  const { convs, activeId, newConversation, openConversation } = useConversations()
  return (
    <aside className="flex h-full w-[232px] shrink-0 flex-col border-r border-border bg-card">
      <div className="px-4 pt-4 pb-3">
        <h1 className="text-[17px] leading-tight">Navigator</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Apetit × Since AI · synthetic data</p>
      </div>
      <nav aria-label="Views" className="flex flex-col">
        {NAV.map(([v, label]) => (
          <button key={v} type="button" onClick={() => setView(v)} aria-current={view === v ? 'page' : undefined}
            className={cn('border-l-2 border-transparent px-4 py-1.5 text-left text-sm hover:bg-subtle', view === v && 'border-primary font-medium text-primary')}>
            {label}
          </button>
        ))}
      </nav>
      {view === 'ask' && (
        <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-border pt-3">
          <div className="flex items-center justify-between px-4 pb-1">
            <h2 className="label">Conversations</h2>
            <Button variant="ghost" size="icon-sm" onClick={newConversation} aria-label="New conversation" title="New conversation"><Plus size={16} /></Button>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {convs.map((c) => (
              <li key={c.thread_id}>
                <button type="button" onClick={() => openConversation(c.thread_id)} aria-current={c.thread_id === activeId ? 'true' : undefined} title={c.title}
                  className={cn('flex w-full items-baseline justify-between gap-2 border-l-2 border-transparent px-4 py-1.5 text-left text-[13px] hover:bg-subtle', c.thread_id === activeId && 'border-primary font-medium text-primary')}>
                  <span className="truncate">{c.title}</span>
                  <span className="num shrink-0 text-[11px] text-muted-foreground">{fmtAgo(c.updated)}</span>
                </button>
              </li>
            ))}
            {convs.length === 0 && <li className="px-4 py-1 text-xs text-muted-foreground">No conversations yet.</li>}
          </ul>
        </div>
      )}
      <div className="mt-5 border-t border-border px-4 py-3">
        <h2 className="label mb-2">Data</h2>
        <ul className="space-y-1.5">
          {['2023', '2024', '2025'].map((y) => {
            const st = status?.data_status?.[y]
            return (
              <li key={y} className="flex items-center justify-between text-[13px]">
                <span className="num">{y}</span>
                {st ? <Badge variant={st === 'naive' ? 'warn' : 'ok'}>{st === 'naive' ? 'Uncleaned' : 'Pipeline'}</Badge> : <Badge>{statusError ? 'Offline' : '...'}</Badge>}
              </li>
            )
          })}
        </ul>
        <button type="button" onClick={reloadOutputs} disabled={reloading}
          className="mt-2 rounded-sm text-[13px] text-primary underline-offset-2 hover:underline disabled:opacity-50">
          {reloading ? 'Reloading...' : 'Reload outputs'}
        </button>
        {statusError && <p role="alert" className="mt-2 text-xs text-reject">{statusError}</p>}
      </div>
      <div className="mt-auto space-y-2 border-t border-border px-4 py-3">
        <label htmlFor="reviewer" className="label block">Reviewer</label>
        <Input id="reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name" className="h-8 text-[13px]" />
        <div className="flex items-center justify-between pt-1">
          <span className="num truncate text-xs text-muted-foreground" title={status?.model}>{status?.model ?? '-'}</span>
          <Button variant="ghost" size="icon-sm" onClick={toggleTheme} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </Button>
        </div>
      </div>
    </aside>
  )
}
