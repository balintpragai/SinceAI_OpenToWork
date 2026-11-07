import { useState } from 'react'
import { Download } from 'lucide-react'
import { api, type Question } from '@/lib/api'
import { useApp } from '@/lib/app'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

type St = 'Pending' | 'Approved' | 'Edited' | 'Rejected' | 'Error' | 'Not run'
const stateOf = (q: Question): St =>
  q.review ? (q.review.status === 'approved' ? 'Approved' : q.review.status === 'edited' ? 'Edited' : 'Rejected')
  : q.error ? 'Error' : q.full || q.answer ? 'Pending' : 'Not run'
const VARIANT = { Pending: 'pending', Approved: 'ok', Edited: 'warn', Rejected: 'reject', Error: 'reject', 'Not run': 'outline' } as const
const FILTERS = ['All', 'Numeric', 'Rubric', 'Pending', 'Approved'] as const

export function AnswerSheet() {
  const { questions, questionsError, selectedQid, setSelectedQid, setEvidenceOpen, run } = useApp()
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('All')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const approved = questions.filter((q) => q.review && q.review.status !== 'rejected').length
  const shown = questions.filter((q) => {
    const s = stateOf(q)
    return filter === 'All' || (filter === 'Pending' ? s === 'Pending' : filter === 'Approved' ? s === 'Approved' || s === 'Edited' : q.kind.toLowerCase().startsWith(filter.toLowerCase()))
  })
  const exportIt = async () => {
    try {
      const r = await api<{ approved: number; total: number; path: string }>('/api/export', { method: 'POST' })
      setMsg({ ok: true, text: `Exported ${r.approved} of ${r.total} answers to ${r.path}. Unapproved answers were left blank.` })
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }) }
  }
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-6 py-3">
        <div className="mr-auto">
          <h2 className="text-[17px]">Answer sheet</h2>
          <p className="num text-[13px] text-muted-foreground">{approved} of {questions.length} approved</p>
        </div>
        <div role="group" aria-label="Filter" className="flex rounded-md border border-border bg-card p-0.5">
          {FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}
              className={cn('rounded-[4px] px-2 py-0.5 text-[13px] text-muted-foreground hover:text-foreground', filter === f && 'bg-primary text-primary-foreground hover:text-primary-foreground')}>{f}</button>
          ))}
        </div>
        <Button size="sm" onClick={exportIt}><Download /> Export submission</Button>
      </header>
      {msg && <p role="status" className={cn('border-b border-border px-6 py-2 text-[13px]', msg.ok ? 'text-ok' : 'text-reject')}>{msg.text}</p>}
      {questionsError && <p role="alert" className="px-6 py-3 text-[13px] text-reject">{questionsError}</p>}
      <div className="min-h-0 flex-1 overflow-auto">
        <Table className="table-fixed text-[13px]">
          <TableHeader>
            <TableRow>
              <TableHead className="label h-8 w-16">ID</TableHead>
              <TableHead className="label h-8 w-20">Kind</TableHead>
              <TableHead className="label h-8">Question</TableHead>
              <TableHead className="label h-8 w-[22%]">Draft answer</TableHead>
              <TableHead className="label h-8 w-24">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((q) => {
              const st = run?.qid === q.question_id && !run.done ? null : stateOf(q)
              return (
                <TableRow key={q.question_id} onClick={() => { setSelectedQid(q.question_id); setEvidenceOpen(true) }}
                  data-state={selectedQid === q.question_id ? 'selected' : undefined} className="cursor-pointer data-[state=selected]:bg-subtle">
                  <TableCell className="num">
                    <button type="button" className="rounded-sm text-left outline-offset-2" aria-label={`Select ${q.question_id}`}
                      onKeyDown={(e) => e.key === 'Enter' && setSelectedQid(q.question_id)}>{q.question_id}</button>
                    {q.split === 'dev' && <span className="ml-1 rounded-[3px] border border-border px-1 text-[10px] text-muted-foreground">dev</span>}
                  </TableCell>
                  <TableCell><Badge variant="outline">{q.kind}</Badge></TableCell>
                  <TableCell className="max-w-0">
                    <Tooltip><TooltipTrigger render={<div className="truncate" />}>{q.question}</TooltipTrigger><TooltipContent>{q.question}</TooltipContent></Tooltip>
                  </TableCell>
                  <TableCell className="num max-w-0 truncate" title={q.review?.final_answer || q.answer}>{q.review?.final_answer || q.answer}</TableCell>
                  <TableCell>{st ? <Badge variant={VARIANT[st]}>{st}</Badge> : <Badge variant="warn">Running</Badge>}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        {questions.length > 0 && shown.length === 0 && <p className="p-6 text-[13px] text-muted-foreground">No questions match this filter.</p>}
      </div>
    </div>
  )
}
