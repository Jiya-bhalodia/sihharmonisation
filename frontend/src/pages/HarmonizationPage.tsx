import { useState } from 'react'
import { Play, CheckCircle2, AlertCircle, Loader2, ArrowRight } from 'lucide-react'
import Topbar from '../components/Topbar'
import { api } from '../services/api'
import { useApi } from '../hooks/useApi'
import type { HarmonizationJob } from '../types'

const PIPELINE_STAGE_NAMES = [
  'Ingestion', 'CRS Normalization', 'Schema Mapping', 'Topology Validation',
  'Spatial Matching', 'Conflict Detection', 'Conflict Resolution',
  'Confidence Scoring', 'Unified Land Record', 'Change Detection',
]

export default function HarmonizationPage() {
  const { data: mappings } = useApi(() => api.getMappings())
  const [job, setJob] = useState<HarmonizationJob | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleRun = async () => {
    setRunning(true)
    setError(null)
    setJob(null)
    try {
      const result = await api.runHarmonization()
      setJob(result)
    } catch (e: any) {
      setError(e.message || 'Harmonization failed. Check that the backend is running, then try again.')
    } finally {
      setRunning(false)
    }
  }

  const getStageStatus = (name: string) => {
    if (!job) return 'pending'
    const stage = job.stages.find((s) => s.name === name)
    return stage?.status || 'pending'
  }

  const getStageDetail = (name: string) => job?.stages.find((s) => s.name === name)

  return (
    <div>
      <Topbar title="Harmonization Pipeline" subtitle="Run the end-to-end GeoAI harmonization workflow across all connected data sources" />

      <div className="space-y-6 p-8">
        <div className="card flex items-center justify-between p-5">
          <div>
            <h3 className="text-sm font-bold text-ink-800">Harmonization Engine</h3>
            <p className="mt-1 text-xs text-ink-400">
              Executes CRS normalization → schema mapping → spatial matching → topology validation → conflict
              detection → confidence scoring → unified record generation, in sequence, against live data.
            </p>
          </div>
          <button
            onClick={handleRun}
            disabled={running}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-brand-700 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-800 disabled:opacity-60"
          >
            {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {running ? 'Running Harmonization…' : 'RUN HARMONIZATION'}
          </button>
        </div>

        {error && (
          <div className="card flex items-center gap-2 border-red-200 bg-red-50 px-4 py-3 text-xs font-semibold text-red-700">
            <AlertCircle size={15} /> {error}
          </div>
        )}

        <div className="card p-5">
          <h3 className="mb-5 text-sm font-bold text-ink-800">Pipeline Stages</h3>
          <div className="space-y-0">
            {PIPELINE_STAGE_NAMES.map((name, i) => {
              const status = getStageStatus(name)
              const detail = getStageDetail(name)
              return (
                <div key={name} className="flex gap-4">
                  <div className="flex flex-col items-center">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      status === 'completed' ? 'bg-brand-600 text-white' :
                      status === 'failed' ? 'bg-red-500 text-white' :
                      status === 'running' ? 'bg-amber-400 text-white' : 'bg-ink-100 text-ink-400'
                    }`}>
                      {status === 'completed' ? <CheckCircle2 size={15} /> : i + 1}
                    </div>
                    {i < PIPELINE_STAGE_NAMES.length - 1 && (
                      <div className={`w-0.5 flex-1 ${status === 'completed' ? 'bg-brand-300' : 'bg-ink-100'}`} style={{ minHeight: 28 }} />
                    )}
                  </div>
                  <div className="flex-1 pb-6">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-ink-800">{name}</span>
                      {status === 'completed' && <span className="badge bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200">Completed</span>}
                      {status === 'failed' && <span className="badge bg-red-50 text-red-700 ring-1 ring-inset ring-red-200">Failed</span>}
                      {status === 'pending' && <span className="badge bg-ink-100 text-ink-400">Pending</span>}
                    </div>
                    {detail ? (
                      <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-ink-500">
                        <span>{detail.detail}</span>
                        {detail.processed > 0 && <span className="font-mono text-ink-400">processed: {detail.processed}</span>}
                        {detail.warnings > 0 && <span className="font-mono text-amber-600">warnings: {detail.warnings}</span>}
                      </div>
                    ) : (
                      <div className="mt-1.5 text-xs text-ink-300">Awaiting pipeline run</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {job?.status === 'completed' && (
            <div className="mt-2 flex items-center justify-between rounded-lg bg-brand-50 px-4 py-3">
              <div className="text-xs font-semibold text-brand-800">
                Harmonization complete — {job.total_processed} unified parcel records generated
              </div>
              <a href="/records" className="flex items-center gap-1 text-xs font-bold text-brand-700 hover:underline">
                View Unified Records <ArrowRight size={12} />
              </a>
            </div>
          )}
        </div>

        <div className="card p-5">
          <h3 className="mb-3 text-sm font-bold text-ink-800">Intelligent Attribute Mapping</h3>
          <p className="mb-3 text-xs text-ink-400">
            Source fields are mapped to canonical fields using fuzzy string similarity + datatype inference,
            computed live against each dataset's schema.
          </p>
          <div className="overflow-hidden rounded-lg border border-ink-100">
            <table className="w-full text-left text-xs">
              <thead className="bg-ink-50 text-[10.5px] uppercase tracking-wide text-ink-400">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Source Field</th>
                  <th className="px-4 py-2.5 font-semibold"></th>
                  <th className="px-4 py-2.5 font-semibold">Canonical Field</th>
                  <th className="px-4 py-2.5 font-semibold">Confidence</th>
                  <th className="px-4 py-2.5 font-semibold">Method</th>
                </tr>
              </thead>
              <tbody>
                {(mappings || []).slice(0, 25).map((m) => (
                  <tr key={m.id} className="border-t border-ink-50">
                    <td className="px-4 py-2 font-mono text-[11px] text-ink-600">{m.source_field}</td>
                    <td className="px-4 py-2 text-ink-300"><ArrowRight size={12} /></td>
                    <td className="px-4 py-2 font-mono text-[11px] font-semibold text-brand-700">{m.canonical_field}</td>
                    <td className="px-4 py-2">
                      <span className={`badge ${m.confidence >= 80 ? 'bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200' : m.confidence >= 55 ? 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200' : 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200'}`}>
                        {m.confidence.toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-4 py-2 text-ink-400">{m.manual_override ? 'manual override' : m.method}</td>
                  </tr>
                ))}
                {(!mappings || mappings.length === 0) && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-ink-400">
                    Run the harmonization pipeline to generate schema mappings
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
