import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useApp } from '@/lib/app'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

type Rec = { record_key: string; source?: string; csv_rows?: number[] | number | null; rows?: Record<string, unknown>[]; error?: string }

export function RecordSheet() {
  const { recordKey, openRecord } = useApp()
  const [rec, setRec] = useState<Rec | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setRec(null); setErr('')
    if (!recordKey) return
    api<Rec>(`/api/records?key=${encodeURIComponent(recordKey)}`).then(setRec).catch((e) => setErr(e.message))
  }, [recordKey])
  const rows = rec?.rows ?? []
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))]
  const csv = Array.isArray(rec?.csv_rows) ? rec.csv_rows.join(', ') : rec?.csv_rows ?? ''
  return (
    <Sheet open={!!recordKey} onOpenChange={(o) => !o && openRecord(null)}>
      <SheetContent side="right" className="data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle className="num text-[15px]">{recordKey}</SheetTitle>
          <SheetDescription className="text-[13px]">Source record behind this number.</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-auto px-4 pb-4">
          {err && <p role="alert" className="text-[13px] text-reject">{err}</p>}
          {!rec && !err && <p className="text-[13px] text-muted-foreground">Loading...</p>}
          {rec?.error && <p role="alert" className="text-[13px] text-reject">{rec.error}</p>}
          {rec && (
            <>
              <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
                <dt className="label self-center">Source file</dt><dd className="num">{rec.source ?? '-'}</dd>
                <dt className="label self-center">CSV rows</dt><dd className="num">{String(csv) || '-'}</dd>
              </dl>
              {rows.length === 0 ? <p className="text-[13px] text-muted-foreground">No rows found for this key.</p> : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="num w-full text-[12px]">
                    <thead><tr className="border-b border-border bg-subtle">{cols.map((c) => <th key={c} className="px-2 py-1 text-left font-medium whitespace-nowrap text-muted-foreground">{c}</th>)}</tr></thead>
                    <tbody>{rows.map((r, i) => (
                      <tr key={i} className="border-b border-border last:border-0">{cols.map((c) => <td key={c} className="px-2 py-1 whitespace-nowrap">{r[c] == null ? '' : String(r[c])}</td>)}</tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
