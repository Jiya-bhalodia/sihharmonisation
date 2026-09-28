import { useState } from 'react'
import { PlusCircle, MinusCircle, RefreshCw, Ruler } from 'lucide-react'
import Topbar from '../components/Topbar'
import ConfidenceBadge from '../components/ConfidenceBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'

const CHANGE_ICONS: Record<string, any> = {
  new: PlusCircle,
  removed: MinusCircle,
  modified: RefreshCw,
  attribute_changed: RefreshCw,
  geometry_changed: Ruler,
}

const CHANGE_COLORS: Record<string, string> = {
  new: 'text-brand-600 bg-brand-50',
  removed: 'text-red-600 bg-red-50',
  modified: 'text-amber-600 bg-amber-50',
  attribute_changed: 'text-amber-600 bg-amber-50',
  geometry_changed: 'text-blue-600 bg-blue-50',
}

export default function ChangesPage({ freeDemoMode = false }: { freeDemoMode?: boolean }) {
  const [filter, setFilter] = useState('')
  const { data: changes, loading } = useApi(() => api.getChanges(filter || undefined), [filter])

  const counts = (changes || []).reduce<Record<string, number>>((acc, c) => {
    acc[c.change_type] = (acc[c.change_type] || 0) + 1
    return acc
  }, {})

  return (
    <div>
      <Topbar title="Change Detection" subtitle="Version-over-version comparison of the unified land record" />

      <div className="space-y-6 p-8">
        {freeDemoMode && <div className="card border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          Snapshot and raster change detection are disabled in the hosted evaluation profile. This demo does not claim vector change results until a durable before/after vector comparison is supported.
        </div>}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {['new', 'removed', 'modified', 'attribute_changed', 'geometry_changed'].map((type) => {
            const Icon = CHANGE_ICONS[type]
            return (
              <button
                key={type}
                onClick={() => setFilter(filter === type ? '' : type)}
                className={`card p-4 text-left transition-colors ${filter === type ? 'ring-2 ring-brand-400' : ''}`}
              >
                <div className={`mb-2 flex h-8 w-8 items-center justify-center rounded-lg ${CHANGE_COLORS[type]}`}>
                  <Icon size={16} />
                </div>
                <div className="text-xl font-extrabold text-ink-900">{counts[type] || 0}</div>
                <div className="text-[10.5px] font-medium capitalize text-ink-400">{type.replace(/_/g, ' ')}</div>
              </button>
            )
          })}
        </div>

        <div className="card overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-ink-100 bg-ink-50 text-[10.5px] uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-4 py-3 font-semibold">Feature</th>
                <th className="px-4 py-3 font-semibold">Change Type</th>
                <th className="px-4 py-3 font-semibold">Before</th>
                <th className="px-4 py-3 font-semibold">After</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold">Detected</th>
              </tr>
            </thead>
            <tbody>
              {(changes || []).map((c) => (
                <tr key={c.id} className="border-b border-ink-50">
                  <td className="px-4 py-3 font-mono text-[11px] font-semibold text-ink-800">{c.feature_ref}</td>
                  <td className="px-4 py-3">
                    <span className={`badge ${CHANGE_COLORS[c.change_type]}`}>{c.change_type.replace(/_/g, ' ')}</span>
                  </td>
                  <td className="px-4 py-3 max-w-[220px] truncate text-ink-500">
                    {c.before ? JSON.stringify(c.before) : '—'}
                  </td>
                  <td className="px-4 py-3 max-w-[220px] truncate text-ink-500">
                    {c.after ? JSON.stringify(c.after) : '—'}
                  </td>
                  <td className="px-4 py-3"><ConfidenceBadge value={c.confidence} showLabel={false} /></td>
                  <td className="px-4 py-3 text-ink-400">{new Date(c.detected_at).toLocaleString()}</td>
                </tr>
              ))}
              {!loading && (!changes || changes.length === 0) && (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-ink-400">
                  {freeDemoMode ? 'Vector before/after change comparison is not available in this hosted demo. Snapshot and raster processing are disabled.' : 'No changes detected yet. Upload a newer dataset version and re-run harmonization.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
