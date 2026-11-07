export type Json = unknown
export type TraceStep = { id: string; tool: string; args: Record<string, unknown>; result?: any; ms?: number }
export type Citation = { citation: string; valid: boolean }
export type AskResult = {
  question?: string
  answer: string
  trace: TraceStep[]
  citations: Citation[]
  data_status: string[]
  model: string
  tokens: { prompt: number | null; cached: number | null; output: number | null }
  thread_id?: string
  answer_id?: string
  parsed_answer?: string
  parsed_evidence?: string
}
export type Stamp = { status: 'approved' | 'edited' | 'rejected'; reviewer: string; ts: string; final_answer: string; final_evidence: string | null }
export type Question = {
  question_id: string; split: string; kind: string; question: string; unit: string
  answer: string; evidence: string; error: string | null; full: AskResult | null; review: Stamp | null
}
export type Conversation = { thread_id: string; title: string; created: string; updated: string; n_messages: number }
export type StoredMessage = { id: string; role: 'user' | 'assistant'; content: string; result?: AskResult; review?: Stamp | null }
export const fmtAgo = (ts: string) => {
  const s = (Date.now() - +new Date(ts)) / 1000
  return isNaN(s) ? '' : s < 60 ? 'now' : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : `${Math.floor(s / 86400)}d`
}
export type Status = { model: string; fake?: boolean; gemini_key: boolean; data_status: Record<string, 'naive' | 'pipeline'> }
export type AuditRow = Record<string, string>
export type StreamEvent =
  | { type: 'tool_start'; id: string; tool: string; args: Record<string, unknown> }
  | ({ type: 'tool_end' } & TraceStep)
  | ({ type: 'final' } & AskResult)
  | { type: 'error'; message: string }

export function friendlyError(msg: string): string {
  if (/429|RESOURCE_EXHAUSTED|rate limit/i.test(msg))
    return 'Gemini rate limit reached. Wait a minute and try again, or enable billing on the API key.'
  if (/GEMINI_API_KEY/.test(msg)) return 'The backend has no Gemini key. Set GEMINI_API_KEY in the environment or .env and restart the server.'
  if (/503|UNAVAILABLE/.test(msg)) return 'Gemini is temporarily unavailable. Try again in a moment.'
  if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(msg)) return 'Cannot reach the backend. Start it with: python3 -m uvicorn server:app --port 8000'
  return msg
}

async function fail(r: Response): Promise<never> {
  let detail = `${r.status} ${r.statusText}`
  try { const j = await r.json(); if (j.detail) detail = String(j.detail) } catch { /* not json */ }
  throw new Error(friendlyError(detail))
}

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const r = await fetch(path, init?.json === undefined ? init : {
    ...init, method: init.method ?? 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(init.json),
  })
  if (!r.ok) await fail(r)
  return r.json()
}

/** POST and yield NDJSON events as they arrive. */
export async function* stream(path: string, json: unknown, signal?: AbortSignal): AsyncGenerator<StreamEvent> {
  let r: Response
  try {
    r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(json), signal })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new Error(friendlyError(String(e)))
  }
  if (!r.ok) await fail(r)
  const reader = r.body!.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    buf += dec.decode(value, { stream: !done })
    let i: number
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim()
      buf = buf.slice(i + 1)
      if (line) yield JSON.parse(line)
    }
    if (done) break
  }
  if (buf.trim()) yield JSON.parse(buf)
}

export const KEY_RE = /\b(erp|energy|fuel|goo|refrigerant|waste|travel|commute|ship|farm_survey|farm|pcf|report|ef|eli):[\w.\-:]+/g
export const recordKeys = (text: string): string[] => [...new Set((text.match(KEY_RE) ?? []).map((k) => k.replace(/[.:\-]+$/, '')))]

export function argSummary(tool: string, a: Record<string, any>): string {
  if (tool === 'sql') return String(a.query ?? '').replace(/\s+/g, ' ')
  if (tool === 'search_docs') return String(a.query ?? '')
  if (tool === 'get_inventory') return Object.entries(a).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}=${v}`).join(' ')
  if (tool === 'get_records') return (a.record_keys ?? []).join(', ')
  return Object.values(a).filter((v) => v !== '' && v != null).map((v) => (typeof v === 'object' ? JSON.stringify(v) : String(v))).join(' · ')
}

export function resultSummary(r: any): { text: string; error: boolean } {
  if (r == null) return { text: '', error: false }
  if (typeof r !== 'object') return { text: String(r), error: false }
  if (r.error) return { text: String(r.error), error: true }
  const bits: string[] = []
  if ('rows_matched' in r) bits.push(`rows_matched ${r.rows_matched}`)
  if ('rows_returned' in r) bits.push(`${r.rows_returned}${r.truncated ? '+' : ''} rows`)
  if (Array.isArray(r.chunks)) bits.push(`${r.chunks.length} chunks`)
  if (typeof r.flagged_share_pct === 'number') bits.push(`flagged ${r.flagged_share_pct}%`)
  if ('n_lines' in r) bits.push(`n_lines ${r.n_lines}`)
  if ('result' in r) bits.push(`result ${r.result}`)
  if ('target_tco2e' in r) bits.push(`target ${r.target_tco2e}`)
  if (Array.isArray(r.records)) bits.push(`${r.records.length} records`)
  return { text: bits.join(' · ') || 'ok', error: false }
}

export const fmtTime = (ts: string) => {
  const d = new Date(ts)
  return isNaN(+d) ? ts : d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}
