import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { api, fmtTime, type AuditRow } from '@/lib/api'
import { useApp } from '@/lib/app'
import { useConversations } from '@/components/Chat'
import { buttonVariants } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { decisionBadge } from './Evidence'
import { cn } from '@/lib/utils'

export function AuditLog() {
  const [rows, setRows] = useState<AuditRow[] | null>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const { setView, setSelectedQid, setSelectedMsgId, setEvidenceOpen } = useApp()
  const { openConversation } = useConversations()
  const linked = (r: AuditRow) => Boolean(r.question_id || r.thread_id)
  // Open the decided answer where it lives: the answer sheet (E questions) or its chat, with Evidence showing it.
  const goTo = async (r: AuditRow, i: number) => {
    if (r.question_id) { setView('sheet'); setSelectedQid(r.question_id) }
    else if (r.thread_id) { await openConversation(r.thread_id); setView('ask'); setSelectedMsgId(r.answer_id) }
    else return setOpen(open === i ? null : i)
    setEvidenceOpen(true)
  }
  useEffect(() => { api<AuditRow[]>('/api/audit').then(setRows).catch((e) => setErr(e.message)) }, [])
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-4 border-b border-border px-6 py-3">
        <div className="mr-auto">
          <h2 className="text-[17px]">Audit log</h2>
          <p className="text-[13px] text-muted-foreground">Every review decision, newest first. Select a row to open the answer. {rows && <span className="num">{rows.length} entries.</span>}</p>
        </div>
        <a href="/api/export/audit.xlsx" download className={buttonVariants({ size: 'sm' })}><Download /> Download (Excel)</a>
      </header>
      <div className="min-h-0 flex-1 overflow-auto">
        {err && <p role="alert" className="p-6 text-[13px] text-reject">{err}</p>}
        {rows && rows.length === 0 && <p className="p-6 text-[13px] text-muted-foreground">No decisions recorded yet. Approve, edit or reject an answer and it will appear here.</p>}
        {rows && rows.length > 0 && (
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow>{['Time', 'Reviewer', 'Source', 'Question', 'Decision', 'Final answer'].map((h) => <TableHead key={h} className="label h-8">{h}</TableHead>)}</TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r, i) => (
                <TableRow key={i} onClick={() => goTo(r, i)} className="cursor-pointer align-top">
                  <TableCell className="num whitespace-nowrap">{fmtTime(r.timestamp_utc)}</TableCell>
                  <TableCell>{r.reviewer}</TableCell>
                  <TableCell className="text-muted-foreground">{r.source}</TableCell>
                  <TableCell className="max-w-0 w-[28%]">
                    <button type="button" title={linked(r) ? 'Open this answer' : r.question} onClick={(e) => { e.stopPropagation(); void goTo(r, i) }}
                      className={cn('block w-full truncate rounded-sm text-left', linked(r) && 'text-primary underline-offset-2 hover:underline')}>
                      {r.question_id && <span className="num mr-1.5 text-muted-foreground">{r.question_id}</span>}{r.question || '-'}
                    </button>
                  </TableCell>
                  <TableCell>{decisionBadge(r.decision)}</TableCell>
                  <TableCell className={cn('num max-w-0 w-[40%]', open === i ? 'whitespace-pre-wrap break-words' : 'truncate')}>
                    {r.final_answer}
                    {open === i && r.final_evidence && <div className="mt-1 text-muted-foreground">{r.final_evidence}</div>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
