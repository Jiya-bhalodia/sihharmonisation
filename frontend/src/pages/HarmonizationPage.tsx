import { useEffect, useRef, useState } from 'react'
import { Play, CheckCircle2, AlertCircle, Loader2, ArrowRight } from 'lucide-react'
import Topbar from '../components/Topbar'
import { api } from '../services/api'
import { useApi } from '../hooks/useApi'
import type { HarmonizationJob } from '../types'

const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds))

const PIPELINE_STAGE_NAMES = [
  'Ingestion', 'CRS Normalization', 'Schema Mapping', 'Topology Validation',
  'Spatial Matching', 'Conflict Detection', 'Conflict Resolution',
  'Confidence Scoring', 'Unified Land Record', 'Change Detection',
]
const CANONICAL_FIELDS = [
  'parcel_id', 'owner_name', 'area', 'land_use', 'survey_number',
  'building_count', 'ward', 'address', 'status',
]

export default function HarmonizationPage({ userRole, freeDemoMode = false }: { userRole?: string; freeDemoMode?: boolean }) {
  const { data: mappings, refetch: refetchMappings } = useApi(() => api.getMappings())
  const { data: matches } = useApi(() => api.getMatches({ limit: 400 }))
  const { data: conflicts } = useApi(() => api.getConflicts())
  const { data: topology } = useApi(() => api.getTopologyResults())
  const { data: parcels } = useApi(() => api.getParcels({ limit: 300 }))
  const { data: statistics } = useApi(() => api.getStatistics())
  const [job, setJob] = useState<HarmonizationJob | null>(null)
  const [running, setRunning] = useState(false)
  const [estimatedStageIndex, setEstimatedStageIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [mappingError, setMappingError] = useState<string | null>(null)
  const [savingMappingId, setSavingMappingId] = useState<string | null>(null)
  const latestJobId = useRef<string | null>(null)
  const activeRunId = useRef(0)
  const canReviewMappings = !userRole || userRole === 'reviewer' || userRole === 'administrator'

  // The hosted POST is synchronous, so it cannot provide a job id until the
  // pipeline is over. Keep the UI moving conservatively while it is in flight;
  // this is presentation progress only and never marks the job complete.
  useEffect(() => {
    if (!running || !freeDemoMode) return
    const timer = window.setInterval(() => {
      setEstimatedStageIndex((index) => Math.min(PIPELINE_STAGE_NAMES.length - 2, index + 1))
    }, 1600)
    return () => window.clearInterval(timer)
  }, [running, freeDemoMode])

  useEffect(() => {
    let active = true
    const startupRunId = activeRunId.current
    const loadLatestJob = async () => {
      try {
        const jobs = await api.listJobs()
        if (!active || activeRunId.current !== startupRunId || jobs.length === 0) return
        let latest = jobs[0]
        latestJobId.current = latest.id
        setJob(latest)
        if (latest.status === 'queued' || latest.status === 'running') setRunning(true)
        while (active && (latest.status === 'queued' || latest.status === 'running')) {
          await wait(1200)
          if (!active || activeRunId.current !== startupRunId) return
          latest = await api.getJob(latest.id)
          if (!active || activeRunId.current !== startupRunId) return
          setJob(latest)
        }
        if (active && latest.status === 'failed') {
          const failure = latest.stages.find((stage) => stage.status === 'failed')
          setError(failure?.detail || 'Automatic harmonization failed. Check the worker logs.')
        }
        if (active && latest.status === 'completed') {
          window.dispatchEvent(new Event('bhumix:data-updated'))
        }
      } catch (reason) {
        if (active && activeRunId.current === startupRunId) setError(reason instanceof Error ? reason.message : 'Could not load harmonization status.')
      } finally {
        if (active && activeRunId.current === startupRunId) setRunning(false)
      }
    }
    void loadLatestJob()
    return () => { active = false }
  }, [refetchMappings])

  const handleMappingOverride = async (mappingId: string, canonicalField: string) => {
    setSavingMappingId(mappingId)
    setMappingError(null)
    try {
      await api.overrideMapping(mappingId, canonicalField)
      refetchMappings()
    } catch (reason) {
      setMappingError(reason instanceof Error ? reason.message : 'Could not save this mapping.')
    } finally {
      setSavingMappingId(null)
    }
  }

  const handleRun = async () => {
    const requestStartedAt = Date.now()
    const previousJobId = latestJobId.current
    const runId = ++activeRunId.current
    setRunning(true)
    setError(null)
    setJob(null)
    setEstimatedStageIndex(0)
    let completionConfirmed = false
    try {
      let requestSettled = false
      const request = api.runHarmonization()
      void request.then(() => { requestSettled = true }, () => { requestSettled = true })

      // Observe committed hosted stages without making job discovery a gate
      // for the synchronous POST response or its completion handling.
      if (freeDemoMode) {
        void (async () => {
          while (!requestSettled && !completionConfirmed && activeRunId.current === runId) {
            await wait(900)
            if (requestSettled || activeRunId.current !== runId) return
            try {
              const jobs = await api.listJobs()
              if (requestSettled || activeRunId.current !== runId) return
              const activeJob = jobs.find((candidate) => {
                if (candidate.id === previousJobId) return false
                // SQLAlchemy serializes naive UTC datetimes without a timezone.
                const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(candidate.started_at)
                  ? candidate.started_at
                  : `${candidate.started_at}Z`
                return Date.parse(timestamp) >= requestStartedAt - 60_000
              })
              if (activeJob?.status === 'completed') {
                // The committed database job is the backend's completion
                // signal. This also recovers results if the synchronous POST
                // response is delayed after the pipeline itself has finished.
                completionConfirmed = true
                latestJobId.current = activeJob.id
                setJob(activeJob)
                window.dispatchEvent(new Event('bhumix:data-updated'))
              } else if (activeJob) {
                latestJobId.current = activeJob.id
                setJob(activeJob)
              }
            } catch {
              // Transient status discovery failures do not block the POST.
            }
          }
        })()
      }

      let result = await request
      requestSettled = true
      if (activeRunId.current !== runId) return
      latestJobId.current = result.id
      setJob(result)
      while (result.status === 'queued' || result.status === 'running') {
        await wait(1200)
        result = await api.getJob(result.id)
        if (activeRunId.current !== runId) return
        latestJobId.current = result.id
        setJob(result)
      }
      if (result.status === 'failed') {
        const failure = result.stages.find((stage) => stage.status === 'failed')
        setError(failure?.detail || 'Harmonization failed. Check the backend worker logs for details.')
      }
      if (result.status === 'completed') {
        completionConfirmed = true
        window.dispatchEvent(new Event('bhumix:data-updated'))
      } else if (result.status !== 'failed') {
        setError(`Harmonization returned an unexpected status: ${result.status || 'unknown'}.`)
      }
    } catch (e: unknown) {
      if (activeRunId.current === runId && !completionConfirmed) {
        setError(e instanceof Error ? e.message : 'Harmonization failed. Check that the backend is running, then try again.')
      }
    } finally {
      if (activeRunId.current === runId) setRunning(false)
    }
  }

  const getStageStatus = (name: string, index: number) => {
    const stage = job?.stages.find((s) => s.name === name)
    if (stage?.status === 'failed' || stage?.status === 'disabled' || stage?.status === 'completed') return stage.status
    if (job?.status === 'completed') return 'completed'
    if (job?.status === 'failed') {
      const failedAt = PIPELINE_STAGE_NAMES.findIndex((stageName) =>
        job.stages.some((item) => item.name === stageName && item.status === 'failed'))
      const activeAt = PIPELINE_STAGE_NAMES.findIndex((stageName) =>
        job.stages.some((item) => item.name === stageName && item.status === 'running'))
      const lastCompleted = PIPELINE_STAGE_NAMES.reduce((last, stageName, stageIndex) =>
        job.stages.some((item) => item.name === stageName && item.status === 'completed') ? stageIndex : last, -1)
      const failureIndex = failedAt >= 0 ? failedAt : activeAt >= 0 ? activeAt : Math.min(lastCompleted + 1, PIPELINE_STAGE_NAMES.length - 1)
      return index === failureIndex ? 'failed' : index < failureIndex ? (stage?.status || 'completed') : 'pending'
    }
    if (freeDemoMode && running) {
      // The hosted POST is synchronous; persisted stage rows can remain on an
      // early "running" stage during a long operation. Advance the display
      // conservatively while the request is active, using backend progress
      // whenever it is further ahead. Completion still requires backend proof.
      const backendActiveIndex = PIPELINE_STAGE_NAMES.findIndex((stageName) =>
        job?.stages.some((item) => item.name === stageName && item.status === 'running'))
      const visibleActiveIndex = Math.max(estimatedStageIndex, backendActiveIndex, 0)
      if (index < visibleActiveIndex) return 'completed'
      if (index === visibleActiveIndex) return 'running'
      return 'pending'
    }
    if (stage?.status === 'running') return 'running'
    if (job?.status === 'queued' || job?.status === 'running' || (running && !job)) {
      const backendActive = job?.stages.find((item) => item.status === 'running')
      if (backendActive) return backendActive.name === name ? 'running' : (stage?.status || 'pending')
      if (running && !job && freeDemoMode) {
        if (index < estimatedStageIndex) return 'completed'
        if (index === estimatedStageIndex) return 'running'
        return 'pending'
      }
      const nextStage = PIPELINE_STAGE_NAMES.find((stageName) =>
        !job?.stages.some((item) => item.name === stageName && (item.status === 'completed' || item.status === 'disabled')))
      if (nextStage === name) return job?.status === 'queued' ? 'queued' : 'running'
    }
    return stage?.status || 'pending'
  }

  const getStageDetail = (name: string) => job?.stages.find((s) => s.name === name)
  const stageStatuses = PIPELINE_STAGE_NAMES.map((name, index) => getStageStatus(name, index))
  const completedStageCount = stageStatuses.filter((status) => status === 'completed').length
  const progressPercent = job?.status === 'completed' ? 100 : Math.min(95, Math.round((completedStageCount / PIPELINE_STAGE_NAMES.length) * 100))
  const resultsReady = job?.status === 'completed'

  return (
    <div>
      <Topbar title="Harmonization Pipeline" subtitle="Run the end-to-end GeoAI harmonization workflow across all connected data sources" />

      <div className="space-y-6 p-8">
        <div className="card flex items-center justify-between p-5">
          <div>
            <h3 className="text-sm font-bold text-ink-800">Harmonization Engine</h3>
            <p className="mt-1 text-xs text-ink-400">
              New uploads automatically refresh outputs. This runs CRS normalization → schema mapping → spatial matching → topology validation → conflict
              detection → confidence scoring → unified record generation, in sequence, against live data.
            </p>
          </div>
          {(userRole !== 'evaluator' || freeDemoMode) && <button
            onClick={handleRun}
            disabled={running}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {running ? 'Running Harmonization…' : 'RUN HARMONIZATION'}
          </button>}
        </div>

        {error && (
          <div className="card flex items-center gap-2 border-red-200 bg-red-50 px-4 py-3 text-xs font-semibold text-red-700">
            <AlertCircle size={15} /> {error}
          </div>
        )}
        {job?.status === 'completed' && !error && (
          <div role="status" className="card border-brand-200 bg-brand-50 px-4 py-3 text-xs font-semibold text-brand-800">
            Harmonization completed successfully. Results below have been refreshed from the API.
          </div>
        )}

        <div className="card p-5">
          <div className="mb-5 flex items-center justify-between gap-3">
            <h3 className="text-sm font-bold text-ink-800">Pipeline Stages</h3>
            {job?.status === 'queued' && <span className="badge bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200">Queued for worker</span>}
            {running && !job && <span className="badge bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200">Starting</span>}
          </div>
          <div className="mb-6">
            <div className="mb-2 flex items-center justify-between text-xs text-ink-500">
              <span>{job?.status === 'completed' ? 'Pipeline complete' : job?.status === 'failed' ? 'Pipeline failed' : running ? 'Processing pipeline' : 'Ready to run'}</span>
              <span className="font-semibold text-ink-700">{progressPercent}%</span>
            </div>
            <div role="progressbar" aria-label="Harmonization progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPercent} className="h-2 overflow-hidden rounded-full bg-ink-100">
              <div className={`h-full rounded-full transition-[width] duration-500 ${job?.status === 'failed' ? 'bg-red-500' : 'bg-brand-600'}`} style={{ width: `${progressPercent}%` }} />
            </div>
          </div>
          <div className="space-y-0">
            {PIPELINE_STAGE_NAMES.map((name, i) => {
              const status = getStageStatus(name, i)
              const detail = getStageDetail(name)
              const isActive = status === 'running' || status === 'queued'
              return (
                <div key={name} className="flex gap-4">
                  <div className="flex flex-col items-center">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      status === 'completed' ? 'bg-emerald-700 text-white' :
                      status === 'failed' ? 'bg-red-500 text-white' :
                      isActive ? 'bg-amber-400 text-white ring-4 ring-amber-100' : 'bg-ink-100 text-ink-400'
                    }`}>
                      {status === 'completed' ? <CheckCircle2 size={15} /> : isActive ? <Loader2 size={15} className="animate-spin" /> : i + 1}
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
                      {status === 'disabled' && <span className="badge bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200">Disabled in hosted demo</span>}
                      {status === 'pending' && <span className="badge bg-ink-100 text-ink-400">Pending</span>}
                      {status === 'running' && <span className="badge bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200">Running</span>}
                      {status === 'queued' && <span className="badge bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200">Queued</span>}
                    </div>
                    {detail ? (
                      <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-ink-500">
                        <span>{detail.detail}</span>
                        {detail.processed > 0 && <span className="font-mono text-ink-400">processed: {detail.processed}</span>}
                        {detail.warnings > 0 && <span className="font-mono text-amber-600">warnings: {detail.warnings}</span>}
                      </div>
                    ) : (
                      <div className="mt-1.5 text-xs text-ink-300">{status === 'disabled' ? 'Snapshot change detection needs durable before/after storage.' : 'Awaiting pipeline run'}</div>
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

        {resultsReady ? <section className="card p-5" aria-label="Latest harmonization results">
          <h3 className="mb-4 text-sm font-bold text-ink-800">Latest Results</h3>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <ResultCount label="Matches" value={matches?.length} />
            <ResultCount label="Conflicts" value={conflicts?.length} />
            <ResultCount label="Attribute mappings" value={mappings?.length} />
            <ResultCount label="Topology results" value={topology?.length} />
            <ResultCount label="Unified parcels" value={parcels?.length} />
          </div>
          <p className="mt-3 text-xs text-ink-500">
            {parcels?.length ? `Mean parcel confidence: ${(parcels.reduce((sum, parcel) => sum + parcel.confidence_score, 0) / parcels.length).toFixed(1)}%` : 'Confidence results appear when unified parcels are available.'}
            {statistics && ` · Statistics API: ${statistics.total_datasets} datasets, ${statistics.total_parcels} parcels, ${statistics.matched_features} matched features, ${statistics.total_conflicts} conflicts`}
          </p>
        </section> : <div className="card p-5 text-xs text-ink-500" role="status">
          {job?.status === 'failed' || error ? 'Results remain hidden because this harmonization run did not complete successfully.' : 'Run harmonization to generate and review current results.'}
        </div>}

        {resultsReady && <div className="card p-5">
          <h3 className="mb-3 text-sm font-bold text-ink-800">Intelligent Attribute Mapping</h3>
          <p className="mb-3 text-xs text-ink-400">
            Source fields are mapped to canonical fields using fuzzy string similarity + datatype inference,
            computed live against each dataset's schema.
          </p>
          {mappingError && <p role="alert" className="mb-3 text-xs font-medium text-red-700">{mappingError}</p>}
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
                    <td className="px-4 py-2">
                      {canReviewMappings ? (
                        <label className="sr-only" htmlFor={`mapping-${m.id}`}>Canonical field for {m.source_field}</label>
                      ) : null}
                      {canReviewMappings ? (
                        <select
                          id={`mapping-${m.id}`}
                          value={m.canonical_field}
                          disabled={savingMappingId === m.id}
                          onChange={(event) => { void handleMappingOverride(m.id, event.target.value) }}
                          className="max-w-full rounded border border-ink-200 bg-white px-2 py-1 font-mono text-[11px] font-semibold text-brand-700 disabled:opacity-60"
                        >
                          {!CANONICAL_FIELDS.includes(m.canonical_field) && <option value={m.canonical_field}>{m.canonical_field}</option>}
                          {CANONICAL_FIELDS.map((field) => <option key={field} value={field}>{field}</option>)}
                        </select>
                      ) : <span className="font-mono text-[11px] font-semibold text-brand-700">{m.canonical_field}</span>}
                    </td>
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
        </div>}
      </div>
    </div>
  )
}

function ResultCount({ label, value }: { label: string; value: number | undefined }) {
  return <div className="rounded-lg bg-ink-50 p-3">
    <div className="text-xl font-extrabold text-ink-900">{value ?? '—'}</div>
    <div className="mt-1 text-[10.5px] font-medium text-ink-500">{label}</div>
  </div>
}
