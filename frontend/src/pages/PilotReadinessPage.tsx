import { CheckCircle2, CircleAlert, ClipboardCheck, RefreshCcw } from 'lucide-react'
import Topbar from '../components/Topbar'
import { LoadingState } from '../components/LoadingState'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'

export default function PilotReadinessPage() {
  const { data: readiness, loading, error, refetch } = useApi(() => api.getPilotReadiness())

  return (
    <div>
      <Topbar title="Pilot Readiness" subtitle="Technical evidence required before treating harmonized output as a pilot result" />
      <div className="space-y-6 p-8">
        {loading && <LoadingState label="Checking pilot evidence..." />}
        {error && <div className="card border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div>}
        {readiness && <>
          <div className={`card flex items-center justify-between border p-5 ${readiness.status === 'READY_FOR_REVIEW' ? 'border-brand-200 bg-brand-50/40' : 'border-amber-200 bg-amber-50/50'}`}>
            <div className="flex items-center gap-3">
              <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${readiness.status === 'READY_FOR_REVIEW' ? 'bg-brand-100 text-brand-700' : 'bg-amber-100 text-amber-700'}`}>
                {readiness.status === 'READY_FOR_REVIEW' ? <CheckCircle2 size={21} /> : <CircleAlert size={21} />}
              </div>
              <div>
                <div className="text-sm font-bold text-ink-900">{readiness.status === 'READY_FOR_REVIEW' ? 'Ready for departmental review' : `${readiness.blocker_count} blocker${readiness.blocker_count === 1 ? '' : 's'} before pilot use`}</div>
                <p className="mt-0.5 text-xs text-ink-500">{readiness.disclaimer}</p>
              </div>
            </div>
            <button onClick={refetch} className="rounded-lg border border-ink-200 p-2 text-ink-500 hover:bg-white"><RefreshCcw size={15} /></button>
          </div>

          <div className="card overflow-hidden">
            <div className="flex items-center gap-2 border-b border-ink-100 bg-ink-50 px-5 py-3 text-xs font-bold text-ink-700"><ClipboardCheck size={15} /> Readiness checklist</div>
            <div className="divide-y divide-ink-100">
              {readiness.checks.map((check) => (
                <div key={check.id} className="grid gap-3 px-5 py-4 md:grid-cols-[120px_1fr]">
                  <div><span className={`badge ${check.status === 'PASS' ? 'bg-brand-50 text-brand-700' : check.status === 'BLOCKER' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>{check.status}</span></div>
                  <div>
                    <div className="text-sm font-bold text-ink-800">{check.title}{check.required && <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-ink-400">Required</span>}</div>
                    <p className="mt-1 text-xs text-ink-500">{check.detail}</p>
                    {check.status !== 'PASS' && <p className="mt-2 text-xs font-medium text-ink-700">Next: {check.action}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>}
      </div>
    </div>
  )
}
