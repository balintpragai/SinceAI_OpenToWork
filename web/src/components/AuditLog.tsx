import { useEffect, useState } from 'react'
import { api, fmtTime, type AuditRow } from '@/lib/api'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { decisionBadge } from './Evidence'
import { cn } from '@/lib/utils'

export function AuditLog() {
  const [rows, setRows] = useState<AuditRow[] | null>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  useEffect(() => { api<AuditRow[]>('/api/audit').then(setRows).catch((e) => setErr(e.message)) }, [])
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-border px-6 py-3">
        <h2 className="text-[17px]">Audit log</h2>
        <p className="text-[13px] text-muted-foreground">Every review decision, newest first. {rows && <span className="num">{rows.length} entries.</span>}</p>
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
                <TableRow key={i} onClick={() => setOpen(open === i ? null : i)} className="cursor-pointer align-top">
                  <TableCell className="num whitespace-nowrap">{fmtTime(r.timestamp_utc)}</TableCell>
                  <TableCell>{r.reviewer}</TableCell>
                  <TableCell className="text-muted-foreground">{r.source}</TableCell>
                  <TableCell className="num">{r.question_id || '-'}</TableCell>
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
