import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, friendlyError, stream, type Question, type Stamp, type Status, type TraceStep } from './api'

export type View = 'ask' | 'sheet' | 'audit'
export type RunState = { qid: string; steps: TraceStep[]; error?: string; done: boolean }

type Ctx = {
  view: View; setView: (v: View) => void
  reviewer: string; setReviewer: (s: string) => void
  dark: boolean; toggleTheme: () => void
  status: Status | null; reloadOutputs: () => Promise<void>; reloading: boolean; statusError: string
  questions: Question[]; questionsError: string; refreshQuestions: () => Promise<void>
  selectedQid: string | null; setSelectedQid: (q: string | null) => void
  run: RunState | null; runQuestion: (qid: string) => Promise<void>
  selectedMsgId: string | null; setSelectedMsgId: (id: string | null) => void
  chatReviews: Record<string, Stamp>; setChatReview: (id: string, s: Stamp) => void
  recordKey: string | null; openRecord: (k: string | null) => void
  evidenceOpen: boolean; setEvidenceOpen: (b: boolean) => void
}
const C = createContext<Ctx>(null!)
export const useApp = () => useContext(C)

export const lsGet = (k: string) => { try { return localStorage.getItem(k) } catch { return null } }
export const lsSet = (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } }

export function AppProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<View>('ask')
  const [reviewer, setReviewerState] = useState(() => lsGet('nav.reviewer') ?? '')
  const setReviewer = (s: string) => { setReviewerState(s); lsSet('nav.reviewer', s) }

  const [dark, setDark] = useState(() => lsGet('nav.theme') === 'dark') // light unless the user chose dark
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    document.documentElement.classList.toggle('light', !dark)
  }, [dark])
  const toggleTheme = () => { lsSet('nav.theme', dark ? 'light' : 'dark'); setDark(!dark) }

  const [status, setStatus] = useState<Status | null>(null)
  const [statusError, setStatusError] = useState('')
  const [reloading, setReloading] = useState(false)
  const loadStatus = useCallback(async () => {
    try { setStatus(await api<Status>('/api/status')); setStatusError('') } catch (e) { setStatusError((e as Error).message) }
  }, [])
  useEffect(() => { loadStatus() }, [loadStatus])
  const reloadOutputs = async () => {
    setReloading(true)
    try { setStatus(await api<Status>('/api/reload', { method: 'POST' })); setStatusError('') } catch (e) { setStatusError((e as Error).message) }
    setReloading(false)
  }

  const [questions, setQuestions] = useState<Question[]>([])
  const [questionsError, setQuestionsError] = useState('')
  const refreshQuestions = useCallback(async () => {
    try { setQuestions(await api<Question[]>('/api/questions')); setQuestionsError('') } catch (e) { setQuestionsError((e as Error).message) }
  }, [])
  useEffect(() => { refreshQuestions() }, [refreshQuestions])
  const [selectedQid, setSelectedQid] = useState<string | null>(null)

  const [run, setRun] = useState<RunState | null>(null)
  const runQuestion = async (qid: string) => {
    setRun({ qid, steps: [], done: false })
    try {
      for await (const ev of stream(`/api/questions/${encodeURIComponent(qid)}/run`, {})) {
        if (ev.type === 'tool_start') setRun((r) => r && { ...r, steps: [...r.steps, { id: ev.id, tool: ev.tool, args: ev.args }] })
        else if (ev.type === 'tool_end') setRun((r) => r && { ...r, steps: r.steps.map((s) => (s.id === ev.id ? { ...s, result: ev.result, ms: ev.ms } : s)) })
        else if (ev.type === 'error') throw new Error(friendlyError(ev.message))
      }
      setRun((r) => r && { ...r, done: true })
    } catch (e) {
      setRun((r) => r && { ...r, done: true, error: (e as Error).message })
    }
    await refreshQuestions()
  }

  const [selectedMsgId, setSelectedMsgId] = useState<string | null>(null)
  const [chatReviews, setChatReviews] = useState<Record<string, Stamp>>({})
  const setChatReview = (id: string, s: Stamp) => setChatReviews((m) => ({ ...m, [id]: s }))
  const [recordKey, openRecord] = useState<string | null>(null)
  const [evidenceOpen, setEvidenceOpen] = useState(false)

  const value = useMemo<Ctx>(() => ({
    view, setView, reviewer, setReviewer, dark, toggleTheme, status, reloadOutputs, reloading, statusError,
    questions, questionsError, refreshQuestions, selectedQid, setSelectedQid, run, runQuestion,
    selectedMsgId, setSelectedMsgId, chatReviews, setChatReview, recordKey, openRecord, evidenceOpen, setEvidenceOpen,
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [view, reviewer, dark, status, reloading, statusError, questions, questionsError, selectedQid, run, selectedMsgId, chatReviews, recordKey, evidenceOpen])
  return <C.Provider value={value}>{children}</C.Provider>
}
