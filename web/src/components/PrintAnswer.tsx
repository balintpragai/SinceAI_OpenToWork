import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, type AskResult } from '@/lib/api'
import { ChartCard, type Chart } from '@/components/charts'

type Summary = Record<string, string | number | boolean | null> & { status: string; approved: boolean }

const Row = ({ k, v }: { k: string; v: unknown }) => (
  <tr><th className="w-44 py-0.5 pr-3 text-left align-top font-medium">{k}</th><td className="num break-all py-0.5">{v == null || v === '' ? '–' : String(v)}</td></tr>
)

/** Print the evidence working paper. Own React root, so app re-renders at print width (narrow layout) cannot unmount it. */
export function printAnswer(params: string, result: AskResult | null) {
  if (document.getElementById('print-root')) return // a print is already being prepared
  const host = document.createElement('div')
  host.id = 'print-root'
  document.body.appendChild(host)
  const root = createRoot(host)
  root.render(<PrintAnswer params={params} result={result} onDone={() => { root.unmount(); host.remove() }} />)
}

function PrintAnswer({ params, result, onDone }: { params: string; result: AskResult | null; onDone: () => void }) {
  const [s, setS] = useState<Summary | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api<Summary>(`/api/export/answer?${params}`).then(setS).catch((e) => setErr((e as Error).message)) }, [params])
  useEffect(() => {
    if (err) { window.alert(`Could not prepare the PDF: ${err}`); onDone(); return }
    if (!s) return
    const after = () => onDone()
    window.addEventListener('afterprint', after, { once: true })
    const t = setTimeout(() => window.print(), 600)  // let fonts and charts lay out first
    return () => { clearTimeout(t); window.removeEventListener('afterprint', after) }
  }, [s, err, onDone])
  if (!s) return null
  const charts = (result?.trace ?? []).filter((t) => t.tool === 'show_chart' && t.result && !t.result.error).map((t) => t.result as Chart)
  return (
    <div className="text-[12px] leading-relaxed text-black">
      {!s.approved && <div aria-hidden className="print-watermark">DRAFT</div>}
      <div className={`px-3 py-2 text-[14px] font-semibold text-white ${s.approved ? 'bg-[#2f7d4f]' : 'bg-[#b3412e]'}`}>{s.status}</div>
      <h1 className="mt-4 text-[20px]">Evidence working paper</h1>
      <p className="text-[11px] text-neutral-600">{String(s.note)}</p>
      <h2 className="mt-4 text-[13px] uppercase tracking-wide text-neutral-600">Question</h2>
      <p>{String(s.question)}</p>
      <h2 className="mt-4 text-[13px] uppercase tracking-wide text-neutral-600">Answer</h2>
      <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{String(s.answer)}</ReactMarkdown></div>
      {charts.map((c, i) => <div key={i} className="print-box mt-3"><ChartCard chart={c} /></div>)}
      {s.technical_evidence && (<>
        <h2 className="mt-4 text-[13px] uppercase tracking-wide text-neutral-600">Technical evidence</h2>
        <div className="md num text-[11px]"><ReactMarkdown remarkPlugins={[remarkGfm]}>{String(s.technical_evidence)}</ReactMarkdown></div>
      </>)}
      {!!result?.sources?.length && (<>
        <h2 className="mt-4 text-[13px] uppercase tracking-wide text-neutral-600">Sources</h2>
        <table className="print-box w-full border-collapse text-[11px]">
          <thead><tr className="border-b border-neutral-400 text-left"><th className="py-1">Source</th><th>File</th><th>Detail</th></tr></thead>
          <tbody>{result.sources.map((x, i) => <tr key={i} className="border-b border-neutral-200 align-top"><td className="py-1 pr-2">{x.label}</td><td className="num pr-2">{x.file}</td><td className="num">{x.detail}</td></tr>)}</tbody>
        </table>
      </>)}
      <div className="mt-4 grid grid-cols-2 gap-3 text-[11px]">
        <div className="print-box rounded border border-neutral-300 p-2">
          <h2 className="mb-1 text-[12px] font-semibold">Record</h2>
          <table><tbody>
            <Row k="Reviewer" v={s.reviewer} /><Row k="Decided at" v={s.decided_at} /><Row k="Model" v={s.model} />
            <Row k="Reference" v={s.reference} /><Row k="Content SHA-256" v={s.content_sha256} /><Row k="Exported at" v={s.exported_at} />
          </tbody></table>
        </div>
        <div className="print-box rounded border border-neutral-300 p-2">
          <h2 className="mb-1 text-[12px] font-semibold">Data run</h2>
          <table><tbody>
            <Row k="Run ID" v={s.run_id} /><Row k="Git commit" v={s.git_commit} /><Row k="Finished" v={s.run_finished} />
            <Row k="Inputs SHA-256" v={s.inputs_sha256} /><Row k="Input files" v={s.n_input_files} />
            <Row k="Reference check" v={s.reference_check_ok == null ? null : s.reference_check_ok ? 'Passed' : 'Failed'} />
            <Row k="Inventory status" v={s.inventory_status} />
          </tbody></table>
        </div>
      </div>
    </div>
  )
}
