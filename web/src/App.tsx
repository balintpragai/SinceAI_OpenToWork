import { useEffect, useState } from 'react'
import { PanelRight } from 'lucide-react'
import { AppProvider, useApp } from '@/lib/app'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AnswerSheet } from '@/components/AnswerSheet'
import { AuditLog } from '@/components/AuditLog'
import { Dashboard } from '@/components/Dashboard'
import { FootprintReview } from '@/components/FootprintReview'
import { AskView, ChatProvider } from '@/components/Chat'
import { EvidencePanel } from '@/components/Evidence'
import { RecordSheet } from '@/components/RecordSheet'
import { Sidebar } from '@/components/Sidebar'

function useNarrow() {
  const q = '(max-width: 899px)'
  const [n, setN] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
    const f = () => setN(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  return n
}

function Shell() {
  const { view, evidenceOpen, setEvidenceOpen, status } = useApp()
  const narrow = useNarrow()
  const showEvidence = view !== 'audit' && view !== 'dashboard' && view !== 'review'
  return (
    <div className="flex h-full min-w-0">
      <Sidebar />
      <main className="relative flex min-w-0 flex-1 flex-col">
        {status?.fake && (
          <div role="status" className="shrink-0 border-b border-warn/30 bg-warn-bg px-4 py-1.5 text-[13px] text-warn">
            Demo mode: answers are scripted and no model is called. Restart the backend without COPILOT_FAKE=1 for real answers.
          </div>
        )}
        <div className="relative min-h-0 flex-1">
        {narrow && showEvidence && (
          <Button variant="outline" size="sm" className="absolute top-3 right-3 z-10" onClick={() => setEvidenceOpen(true)}>
            <PanelRight /> Evidence
          </Button>
        )}
        {view === 'dashboard' ? <Dashboard /> : view === 'review' ? <FootprintReview /> : view === 'ask' ? <AskView /> : view === 'sheet' ? <AnswerSheet /> : <AuditLog />}
        </div>
      </main>
      {showEvidence && !narrow && (
        <aside aria-label="Evidence" className="h-full w-[380px] shrink-0 border-l border-border bg-card"><EvidencePanel /></aside>
      )}
      {narrow && (
        <Sheet open={evidenceOpen} onOpenChange={setEvidenceOpen}>
          <SheetContent side="right" showCloseButton className="data-[side=right]:w-[380px] data-[side=right]:max-w-full !gap-0 !p-0">
            <SheetTitle className="sr-only">Evidence</SheetTitle>
            <EvidencePanel />
          </SheetContent>
        </Sheet>
      )}
      <RecordSheet />
    </div>
  )
}

export default function App() {
  return (
    <TooltipProvider delay={300}>
      <AppProvider>
        <ChatProvider>
          <Shell />
        </ChatProvider>
      </AppProvider>
    </TooltipProvider>
  )
}
