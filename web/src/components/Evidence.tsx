import { useEffect, useMemo, useState } from 'react'
import { useAuiState } from '@assistant-ui/react'
import { Check, Play, X } from 'lucide-react'
import { api, fmtTime, recordKeys, type AskResult, type Stamp } from '@/lib/api'
import { useApp } from '@/lib/app'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { finalOf } from './Chat'
import { ToolStep } from './ToolStep'

export const decisionBadge = (s: string) =>
  s === 'approved' ? <Badge variant="ok">Approved</Badge>
  : s === 'edited' ? <Badge variant="warn">Edited</Badge>
  : s === 'rejected' ? <Badge variant="reject">Rejected</Badge>
  : <Badge variant="pending">Pending</Badge>

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-border px-4 py-3">
      <h3 className="label mb-2">{title}</h3>
      {children}
    </section>
  )
}

type Subject = {
  key: string; source: 'chat' | 'answer_sheet'; qid?: string; answerId?: string; result: AskResult | null
  answer: string; evidence: string; review: Stamp | null; title: string
}

function useSubject(): Subject | null {
  const { view, selectedMsgId, chatReviews, questions, selectedQid } = useApp()
  const messages = useAuiState((s) => s.thread.messages)
  return useMemo(() => {
    if (view === 'sheet') {
      const q = questions.find((x) => x.question_id === selectedQid)
      if (!q) return null
      return { key: q.question_id, source: 'answer_sheet', qid: q.question_id, answerId: q.full?.answer_id, result: q.full, answer: q.answer, evidence: q.evidence, review: q.review, title: q.question }
    }
    const withFinal = messages.filter((m) => m.role === 'assistant' && finalOf(m))
    const m = withFinal.find((x) => x.id === selectedMsgId) ?? withFinal[withFinal.length - 1]
    if (!m) return null
    const res = finalOf(m)!
    const aid = res.answer_id ?? m.id
    return { key: aid, source: 'chat', answerId: aid, result: res, answer: res.answer, evidence: '', review: chatReviews[aid] ?? null, title: res.question ?? '' }
  }, [view, messages, selectedMsgId, chatReviews, questions, selectedQid])
}

function ReviewBar({ s }: { s: Subject }) {
  const { reviewer, setChatReview, refreshQuestions } = useApp()
  const [editing, setEditing] = useState(false)
  const [ans, setAns] = useState('')
  const [evi, setEvi] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { setEditing(false); setErr('') }, [s.key])

  const noName = !reviewer.trim()
  const noRun = !s.result || !s.answerId
  const disabledReason = noName ? 'Enter your name in the sidebar' : noRun ? 'Run the question first' : ''

  const submit = async (decision: 'approved' | 'edited' | 'rejected', answer: string, evidence: string) => {
    setBusy(true); setErr('')
    try {
      const st = await api<Stamp>('/api/review', {
        json: { reviewer: reviewer.trim(), decision, source: s.source, answer_id: s.answerId, thread_id: s.result?.thread_id, question_id: s.qid, result: s.result, final_answer: answer, final_evidence: evidence },
      })
      if (s.qid) await refreshQuestions(); else setChatReview(s.key, st)
      setEditing(false)
    } catch (e) { setErr((e as Error).message); if (s.qid) void refreshQuestions() }
    setBusy(false)
  }

  const btn = (label: string, onClick: () => void, variant: 'default' | 'outline', icon?: React.ReactNode) => {
    const b = <Button size="sm" variant={variant} disabled={busy || !!disabledReason} onClick={onClick}>{icon}{label}</Button>
    return disabledReason
      ? <Tooltip><TooltipTrigger render={<span tabIndex={0} className="inline-flex" />}>{b}</TooltipTrigger><TooltipContent>{disabledReason}</TooltipContent></Tooltip>
      : b
  }

  return (
    <div className="shrink-0 border-t border-border bg-card px-4 py-3">
      {s.review && (
        <div className="mb-2 flex items-center gap-2 text-[13px]">
          {decisionBadge(s.review.status)}
          <span className="text-muted-foreground">
            {s.review.status === 'approved' ? 'Approved' : s.review.status === 'edited' ? 'Edited' : 'Rejected'} by {s.review.reviewer} · <span className="num">{fmtTime(s.review.ts)}</span>
          </span>
        </div>
      )}
      {s.review ? null : editing ? (
        <div className="space-y-2">
          <label className="label block">Answer</label>
          <Textarea value={ans} onChange={(e) => setAns(e.target.value)} className="min-h-16 max-h-60" aria-label="Final answer" />
          {s.source === 'answer_sheet' && (<>
            <label className="label block">Evidence</label>
            <Textarea value={evi} onChange={(e) => setEvi(e.target.value)} className="min-h-16 max-h-40" aria-label="Final evidence" />
          </>)}
          <div className="flex gap-2">
            <Button size="sm" disabled={busy || !ans.trim()} onClick={() => submit('edited', ans, evi)}>Save</Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          {btn('Approve', () => submit('approved', s.answer, s.evidence), 'default', <Check />)}
          {btn('Edit', () => { setAns(s.review?.final_answer ?? s.answer); setEvi(s.review?.final_evidence ?? s.evidence); setEditing(true) }, 'outline')}
          {btn('Reject', () => submit('rejected', s.answer, s.evidence), 'outline', <X />)}
        </div>
      )}
      {err && <p role="alert" className="mt-2 text-[13px] text-reject">{err}</p>}
      {!s.review && !editing && <p className="mt-2 text-xs text-muted-foreground">Nothing is published until a person approves it.</p>}
    </div>
  )
}

export function EvidencePanel() {
  const s = useSubject()
  const { view, run, runQuestion, openRecord } = useApp()
  const live = view === 'sheet' && s?.qid && run?.qid === s.qid ? run : null
  const running = !!live && !live.done

  if (!s) {
    return (
      <div className="p-4">
        <h2 className="mb-2 text-[15px]">Evidence</h2>
        <p className="text-[13px] text-muted-foreground">
          {view === 'sheet' ? 'Select a question to see its draft, citations and tool trace.' : 'Ask a question. Citations, record keys and the tool trace for the selected answer appear here.'}
        </p>
      </div>
    )
  }
  const r = s.result
  const keys = recordKeys(`${r?.answer ?? s.answer}\n${s.evidence}`)
  const naive = !!r?.data_status?.includes('naive')
  const steps = running ? live!.steps : r?.trace ?? []

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="border-b border-border px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-[15px]">Evidence</h2>
            {s.qid && (
              <Button size="sm" variant="outline" disabled={running} onClick={() => runQuestion(s.qid!)}>
                <Play /> {running ? 'Running' : r ? 'Re-run' : 'Run'}
              </Button>
            )}
          </div>
          <p className="mt-1 line-clamp-3 text-[13px] text-muted-foreground">{s.qid && <span className="num mr-1.5">{s.qid}</span>}{s.title}</p>
        </div>

        {naive && (
          <div role="status" className="border-b border-warn/30 bg-warn-bg px-4 py-2 text-[13px] text-warn">
            Built on uncleaned data. Numbers may be wrong until the pipeline outputs land.
          </div>
        )}
        {live?.error && <p role="alert" className="border-b border-reject/30 bg-reject/10 px-4 py-2 text-[13px] text-reject">{live.error}</p>}
        {s.qid && !r && !running && !live?.error && <p className="px-4 py-3 text-[13px] text-muted-foreground">This question has not been run. Press Run to draft an answer.</p>}

        {s.qid && s.answer && (
          <Section title="Draft answer">
            <p className="num break-words text-[13px]">{s.answer}</p>
            {s.evidence && <p className="num mt-1 break-words text-xs text-muted-foreground">{s.evidence}</p>}
          </Section>
        )}

        {r && (
          <Section title="Citations">
            {r.citations.length === 0 ? <p className="text-[13px] text-muted-foreground">No citations in this answer.</p> : (
              <ul className="space-y-1">
                {r.citations.map((c, i) => (
                  <li key={i} className="flex items-start gap-2 text-[13px]">
                    {c.valid ? <Check size={14} className="mt-0.5 shrink-0 text-ok" aria-label="valid" /> : <X size={14} className="mt-0.5 shrink-0 text-reject" aria-label="invalid" />}
                    <span className="min-w-0 break-words"><span className="num text-[12px]">{c.citation}</span>{!c.valid && <span className="ml-1.5 text-reject">not found in corpus</span>}</span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        )}

        {keys.length > 0 && (
          <Section title="Record keys">
            <div className="flex flex-wrap gap-1.5">
              {keys.map((k) => (
                <button key={k} type="button" onClick={() => openRecord(k)}
                  className="num max-w-full truncate rounded-[4px] border border-border bg-subtle px-1.5 py-0.5 text-[12px] hover:border-primary hover:text-primary">{k}</button>
              ))}
            </div>
          </Section>
        )}

        {(steps.length > 0 || running) && (
          <Section title={`Tool trace${steps.length ? ` (${steps.length})` : ''}`}>
            {steps.map((t, i) => <ToolStep stacked key={t.id} index={i + 1} tool={t.tool} args={t.args} result={t.result} ms={t.ms} />)}
            {running && steps.length === 0 && <p className="text-[13px] text-muted-foreground">Waiting for the first tool call...</p>}
          </Section>
        )}

        {r && (
          <Section title="Tokens">
            <p className="num text-[12.5px] text-muted-foreground">
              prompt {r.tokens.prompt ?? '-'} · cached {r.tokens.cached ?? '-'} · output {r.tokens.output ?? '-'}
            </p>
          </Section>
        )}
      </div>
      <ReviewBar s={s} />
    </div>
  )
}
