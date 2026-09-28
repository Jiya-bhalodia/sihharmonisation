import { useMemo } from 'react'
import { CheckCircle2, ShieldAlert } from 'lucide-react'
import Topbar from '../components/Topbar'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { displayDatasetName } from '../services/displayNames'

export default function TopologyPage() {
  const { data: quality } = useApi(() => api.getDataQuality())
  const { data: results } = useApi(() => api.getTopologyResults())
  const { data: stats } = useApi(() => api.getStatistics())

  const totalInvalid = useMemo(() => (quality || []).reduce((s, d) => s + d.invalid_geometry_count, 0), [quality])

  return (
    <div>
      <Topbar title="Topology Validation" subtitle="Geometry integrity checks powered by Shapely/GeoPandas across every dataset" />

      <div className="space-y-6 p-8">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="card p-4">
            <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">Total Topology Issues</div>
            <div className="mt-1.5 text-2xl font-extrabold text-ink-900">{stats?.topology_errors ?? totalInvalid}</div>
          </div>
          <div className="card p-4">
            <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">Datasets Checked</div>
            <div className="mt-1.5 text-2xl font-extrabold text-ink-900">{quality?.length ?? 0}</div>
          </div>
          <div className="card p-4">
            <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">Correction Method</div>
            <div className="mt-1.5 text-sm font-bold text-brand-700">make_valid() / buffer(0)</div>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="mb-1 text-sm font-bold text-ink-800">Validation Pipeline</h3>
          <p className="mb-4 text-xs text-ink-400">
            Original geometry is always preserved — corrected geometry is stored alongside it, never overwriting the source.
          </p>
          <div className="flex items-center gap-3 overflow-x-auto rounded-lg bg-ink-50 px-4 py-4 text-xs font-semibold text-ink-500">
            <span className="rounded-full bg-white px-3 py-1.5 shadow-sm">Invalid Geometry</span>
            <span>→</span>
            <span className="rounded-full bg-white px-3 py-1.5 shadow-sm text-brand-700">make_valid</span>
            <span>→</span>
            <span className="rounded-full bg-white px-3 py-1.5 shadow-sm">Corrected Geometry</span>
            <span>→</span>
            <span className="rounded-full bg-brand-600 px-3 py-1.5 text-white shadow-sm">Validated</span>
          </div>
        </div>

        <div className="card overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-ink-100 bg-ink-50 text-[10.5px] uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-4 py-3 font-semibold">Dataset</th>
                <th className="px-4 py-3 font-semibold">Source Type</th>
                <th className="px-4 py-3 font-semibold">Feature Count</th>
                <th className="px-4 py-3 font-semibold">Invalid Geometries</th>
                <th className="px-4 py-3 font-semibold">Result</th>
              </tr>
            </thead>
            <tbody>
              {(quality || []).map((d) => (
                <tr key={d.dataset_id} className="border-b border-ink-50">
                  <td className="px-4 py-3 font-semibold text-ink-800">{displayDatasetName(d.name)}</td>
                  <td className="px-4 py-3 text-ink-500">{d.source_type}</td>
                  <td className="px-4 py-3 text-ink-700">{d.feature_count}</td>
                  <td className="px-4 py-3 text-ink-700">{d.invalid_geometry_count}</td>
                  <td className="px-4 py-3">
                    {d.invalid_geometry_count === 0 ? (
                      <span className="flex items-center gap-1.5 font-semibold text-brand-700">
                        <CheckCircle2 size={14} /> Clean
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 font-semibold text-amber-600">
                        <ShieldAlert size={14} /> {d.invalid_geometry_count} corrected
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {(!quality || quality.length === 0) && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-ink-400">Run harmonization to generate a topology report</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="card overflow-hidden">
          <div className="border-b border-ink-100 px-5 py-3 text-xs font-bold text-ink-700">Validation Evidence</div>
          <table className="w-full text-left text-xs">
            <thead className="border-b border-ink-100 bg-ink-50 text-[10.5px] uppercase tracking-wide text-ink-400"><tr>
              <th className="px-4 py-3">Feature</th><th className="px-4 py-3">Issue</th><th className="px-4 py-3">Corrected</th><th className="px-4 py-3">Geometry audit</th>
            </tr></thead>
            <tbody>{(results || []).map((result) => <tr key={result.id} className="border-b border-ink-50">
              <td className="px-4 py-3 font-mono">{result.feature_id}</td><td className="px-4 py-3">{result.issue_type || '—'}</td>
              <td className="px-4 py-3">{result.corrected ? 'Yes' : 'No'}</td><td className="px-4 py-3">
                <details><summary className="cursor-pointer text-brand-700">Original and corrected geometry</summary>
                  <div className="mt-2 grid gap-2 md:grid-cols-2"><pre className="max-h-40 overflow-auto rounded bg-ink-50 p-2 text-[9px]">Original: {result.original_geometry || '—'}</pre><pre className="max-h-40 overflow-auto rounded bg-ink-50 p-2 text-[9px]">Corrected: {result.corrected_geometry || '—'}</pre></div>
                </details>
              </td></tr>)}
              {(!results || results.length === 0) && <tr><td colSpan={4} className="px-4 py-8 text-center text-ink-400">No validation issues recorded yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
