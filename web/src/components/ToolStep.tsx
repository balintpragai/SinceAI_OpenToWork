import { useState } from 'react'
import { Check, ChevronRight, Loader2 } from 'lucide-react'
import type { ToolCallMessagePartProps } from '@assistant-ui/react'
import { argSummary, resultSummary } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = { index?: number; tool: string; args: Record<string, any>; result?: any; ms?: number; stacked?: boolean }

export function ToolStep({ index, tool, args, result, ms, stacked }: Props) {
  const [open, setOpen] = useState(false)
  const running = result === undefined
  const sum = resultSummary(result)
  return (
    <div className="border-b border-border/70 last:border-b-0">
      <button
        type="button" aria-expanded={open} onClick={() => setOpen(!open)} disabled={running}
        className={cn("flex w-full items-center gap-2 rounded-sm px-1 py-1 text-left text-[12.5px] hover:bg-subtle disabled:cursor-default disabled:hover:bg-transparent", stacked && "flex-wrap")}
      >
        <ChevronRight size={12} className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-90', running && 'invisible')} />
        {index !== undefined && <span className="num w-4 shrink-0 text-muted-foreground">{index}</span>}
        {running
          ? <Loader2 size={13} className="shrink-0 animate-spin text-muted-foreground" aria-label="running" />
          : <Check size={13} className={cn('shrink-0', sum.error ? 'text-reject' : 'text-ok')} aria-label="done" />}
        <span className="num shrink-0 font-medium">{tool}</span>
        <span className={cn("num min-w-0 flex-1 truncate text-muted-foreground", stacked && "order-last basis-full pl-[52px]")} title={argSummary(tool, args)}>{argSummary(tool, args)}</span>
        {!running && <span className={cn('num max-w-[40%] shrink-0 truncate', sum.error ? 'text-reject' : 'text-muted-foreground', stacked && 'flex-1')} title={sum.text}>{sum.text}</span>}
        {ms !== undefined && <span className="num w-14 shrink-0 text-right text-muted-foreground">{ms} ms</span>}
      </button>
      {open && !running && (
        <pre className="num mx-1 mb-2 max-h-64 overflow-auto rounded-md border border-border bg-subtle p-2 text-[11.5px] leading-snug whitespace-pre-wrap break-all">
          {JSON.stringify({ args, result }, null, 2)}
        </pre>
      )}
    </div>
  )
}

/** assistant-ui fallback renderer for every tool-call part. */
export function ToolCallFallback(p: ToolCallMessagePartProps) {
  const ms = (p.artifact as { ms?: number } | undefined)?.ms
  return <ToolStep tool={p.toolName} args={p.args} result={p.result} ms={ms} />
}
