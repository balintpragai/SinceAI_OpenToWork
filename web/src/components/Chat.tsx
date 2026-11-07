import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  AssistantRuntimeProvider, AuiIf, ComposerPrimitive, MessagePrimitive, ThreadPrimitive, useAui, useAuiState, useLocalRuntime,
  type ChatModelAdapter, type ThreadAssistantMessagePart, type ThreadMessageLike, type ToolCallMessagePart,
} from '@assistant-ui/react'
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowUp, Square } from 'lucide-react'
import { api, friendlyError, stream, type AskResult, type Conversation, type StoredMessage } from '@/lib/api'
import { lsGet, lsSet, useApp } from '@/lib/app'
import { Button } from '@/components/ui/button'
import { ToolCallFallback } from './ToolStep'
import { cn } from '@/lib/utils'

type Conv = {
  convs: Conversation[]; activeId: string | undefined
  newConversation: () => void; openConversation: (id: string) => Promise<void>
}
const ConvCtx = createContext<Conv>(null!)
export const useConversations = () => useContext(ConvCtx)
export const useNewConversation = () => useContext(ConvCtx).newConversation

type Start = { key: number; id?: string; messages: ThreadMessageLike[] }

function Runtime({ start, onFinal, children }: { start: Start; onFinal: (id: string) => void; children: ReactNode }) {
  const threadId = useRef<string | undefined>(start.id)
  const [adapter] = useState<ChatModelAdapter>(() => ({
    async *run({ messages, abortSignal }) {
      const last = messages[messages.length - 1]
      const message = last.content.map((c) => (c.type === 'text' ? c.text : '')).join('')
      const parts: ThreadAssistantMessagePart[] = []
      const idx = new Map<string, number>()
      for await (const ev of stream('/api/chat', { message, thread_id: threadId.current }, abortSignal)) {
        if (ev.type === 'tool_start') {
          idx.set(ev.id, parts.length)
          parts.push({ type: 'tool-call', toolCallId: ev.id, toolName: ev.tool, args: ev.args as never, argsText: JSON.stringify(ev.args) })
          yield { content: [...parts] }
        } else if (ev.type === 'tool_end') {
          const i = idx.get(ev.id)
          if (i === undefined) continue
          parts[i] = { ...(parts[i] as ToolCallMessagePart), result: ev.result, artifact: { ms: ev.ms } }
          yield { content: [...parts] }
        } else if (ev.type === 'final') {
          threadId.current = ev.thread_id ?? threadId.current
          parts.push({ type: 'text', text: ev.answer })
          yield { content: [...parts], metadata: { custom: { final: ev } } }
          if (threadId.current) onFinal(threadId.current)
        } else if (ev.type === 'error') {
          throw new Error(friendlyError(ev.message))
        }
      }
    },
  }))
  const runtime = useLocalRuntime(adapter, { initialMessages: start.messages })
  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const { setSelectedMsgId, setChatReview } = useApp()
  const [start, setStart] = useState<Start>({ key: 0, messages: [] })
  const [activeId, setActiveId] = useState<string | undefined>()
  const [convs, setConvs] = useState<Conversation[]>([])
  const refresh = useCallback(async () => {
    try { setConvs(await api<Conversation[]>('/api/conversations')) } catch { /* sidebar list is best-effort */ }
  }, [])
  const activate = (id: string | undefined) => { setActiveId(id); lsSet('nav.thread', id ?? '') }

  const openConversation = useCallback(async (id: string) => {
    try {
      const c = await api<{ messages: StoredMessage[] }>(`/api/conversations/${id}`)
      const messages: ThreadMessageLike[] = c.messages.map((m) => {
        if (m.role === 'user') return { id: m.id, role: 'user', content: m.content }
        if (m.review) setChatReview(m.id, m.review)
        const final = m.result && { ...m.result, answer_id: m.id, thread_id: id }
        const calls = (m.result?.trace ?? []).map((t) => ({
          type: 'tool-call' as const, toolCallId: t.id, toolName: t.tool, args: t.args as never, argsText: JSON.stringify(t.args), result: t.result, artifact: { ms: t.ms },
        }))
        return { id: m.id, role: 'assistant', status: { type: 'complete', reason: 'stop' }, content: [...calls, { type: 'text' as const, text: m.content }], metadata: { custom: { final } } }
      })
      setSelectedMsgId(null)
      setStart((s) => ({ key: s.key + 1, id, messages }))
      activate(id)
    } catch { activate(undefined) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const newConversation = () => { setSelectedMsgId(null); setStart((s) => ({ key: s.key + 1, messages: [] })); activate(undefined) }

  useEffect(() => {
    void refresh()
    const id = lsGet('nav.thread')
    if (id) void openConversation(id)
  }, [refresh, openConversation])

  const onFinal = useCallback((id: string) => { setActiveId(id); lsSet('nav.thread', id); void refresh() }, [refresh])
  return (
    <ConvCtx.Provider value={{ convs, activeId, newConversation, openConversation }}>
      <Runtime key={start.key} start={start} onFinal={onFinal}>{children}</Runtime>
    </ConvCtx.Provider>
  )
}

export const finalOf = (m: { metadata?: { custom?: Record<string, unknown> } }) => m.metadata?.custom?.final as AskResult | undefined

const EXAMPLES = [
  'What were total Scope 1 emissions in 2024?',
  'Which refrigerant events at Säkylä drove Scope 1?',
  'Does cancelling wind-power GoOs reduce location-based Scope 2?',
  'How many tonnes of soy protein isolate were bought in 2025, net of returns?',
]

function Markdown() {
  return <MarkdownTextPrimitive className="md" remarkPlugins={[remarkGfm]} smooth={false} />
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end py-2">
      <div className="max-w-[80%] whitespace-pre-wrap rounded-md border border-border bg-card px-3 py-2 text-sm">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  )
}

function AssistantMessage() {
  const { selectedMsgId, setSelectedMsgId, setEvidenceOpen } = useApp()
  const id = useAuiState((s) => s.message.id)
  const final = useAuiState((s) => finalOf(s.message))
  const selected = selectedMsgId === id
  return (
    <MessagePrimitive.Root className="py-2">
      <div
        className={cn('rounded-md border border-transparent px-2 py-1.5 -mx-2', selected && 'border-border bg-card/60')}
        onClick={() => { if (final) { setSelectedMsgId(id); setEvidenceOpen(true) } }}
      >
        <MessagePrimitive.Parts components={{ Text: Markdown, tools: { Fallback: ToolCallFallback } }} />
        <MessagePrimitive.Error>
          <p role="alert" className="mt-1 rounded-md border border-reject/30 bg-reject/10 px-3 py-2 text-[13px] text-reject">
            <ErrorText />
          </p>
        </MessagePrimitive.Error>
        <AuiIf condition={(s) => s.message.status?.type === 'running' && s.message.content.length === 0}>
          <p className="text-[13px] text-muted-foreground">Waiting for the first tool call...</p>
        </AuiIf>
      </div>
    </MessagePrimitive.Root>
  )
}

function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message
  if (typeof e === 'string') return e
  if (e && typeof e === 'object' && 'message' in e) return String((e as { message: unknown }).message)
  try { return JSON.stringify(e) } catch { return String(e) }
}

function ErrorText() {
  const err = useAuiState((s) => {
    const st = s.message.status
    return st?.type === 'incomplete' && st.reason === 'error' ? errorMessage(st.error) : ''
  })
  return <>{friendlyError(err) || 'The request failed. Try again.'}</>
}

function Composer() {
  const newConv = useNewConversation()
  return (
    <div className="border-t border-border bg-background px-6 py-3">
      <ComposerPrimitive.Root className="mx-auto flex max-w-3xl items-end gap-2 rounded-md border border-border bg-card p-1.5 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/30">
        <ComposerPrimitive.Input
          rows={1} maxRows={6} placeholder="Ask a question" aria-label="Question"
          className="max-h-40 min-h-8 flex-1 resize-none bg-transparent px-2 py-1 text-sm outline-none placeholder:text-muted-foreground"
        />
        <AuiIf condition={(s) => !s.thread.isRunning}>
          <ComposerPrimitive.Send render={<Button size="sm" aria-label="Send" />}><ArrowUp /> Send</ComposerPrimitive.Send>
        </AuiIf>
        <AuiIf condition={(s) => s.thread.isRunning}>
          <ComposerPrimitive.Cancel render={<Button size="sm" variant="outline" aria-label="Stop" />}><Square /> Stop</ComposerPrimitive.Cancel>
        </AuiIf>
      </ComposerPrimitive.Root>
      <div className="mx-auto mt-1.5 flex max-w-3xl items-center justify-between text-xs text-muted-foreground">
        <span>Enter to send, Shift+Enter for a new line.</span>
        <button type="button" onClick={newConv} className="rounded-sm underline underline-offset-2 hover:text-foreground">New conversation</button>
      </div>
    </div>
  )
}

export function AskView() {
  const aui = useAui()
  return (
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col">
      <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-3xl">
          <AuiIf condition={(s) => s.thread.isEmpty}>
            <div className="pt-10">
              <p className="max-w-lg text-sm text-muted-foreground">
                Ask about the inventory, a data issue or a framework rule. Every number comes from a tool call you can inspect.
              </p>
              <div className="mt-4 flex max-w-lg flex-col items-start gap-1.5">
                {EXAMPLES.map((q) => (
                  <button
                    key={q} type="button"
                    onClick={() => aui.thread().append({ role: 'user', content: [{ type: 'text', text: q }] })}
                    className="rounded-md border border-border bg-card px-3 py-1.5 text-left text-[13px] hover:border-primary hover:text-primary"
                  >{q}</button>
                ))}
              </div>
            </div>
          </AuiIf>
          <ThreadPrimitive.Messages>
            {({ message }) => (message.role === 'user' ? <UserMessage /> : <AssistantMessage />)}
          </ThreadPrimitive.Messages>
        </div>
      </ThreadPrimitive.Viewport>
      <Composer />
    </ThreadPrimitive.Root>
  )
}
