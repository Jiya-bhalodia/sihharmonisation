import { useMemo, useState } from 'react'
import Topbar from '../components/Topbar'
import StatusBadge from '../components/StatusBadge'
import MapView from '../components/MapView'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { buildLayerConfig, parcelsToFeatures } from '../services/geo'

const STATUS_OPTIONS = ['Open', 'Under Review', 'Resolved', 'Accepted', 'Rejected']

export default function ConflictsPage() {
  const { data: conflicts, refetch } = useApi(() => api.getConflicts())
  const { data: parcels } = useApi(() => api.getParcels({ limit: 300 }))
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterSeverity, setFilterSeverity] = useState('')

  const filtered = (conflicts || []).filter((c) =>
    (!filterStatus || c.status === filterStatus) && (!filterSeverity || c.severity === filterSeverity)
  )

  const selected = filtered.find((c) => c.id === selectedId)
  const highlightIds = selected?.parcel_id ? [selected.parcel_id] : []

  const parcelFeatures = useMemo(() => (parcels ? parcelsToFeatures(parcels) : []), [parcels])
  const layers = useMemo(() => [buildLayerConfig('unified-conflicts', 'unified', parcelFeatures)], [parcelFeatures])

  const handleResolve = async (id: string, status: string) => {
    await api.resolveConflict(id, status)
    refetch()
  }

  return (
    <div>
      <Topbar title="Conflict Resolution" subtitle="Review and resolve spatial and attribute conflicts detected across sources" />

      <div className="grid grid-cols-1 gap-6 p-8 xl:grid-cols-5">
        <div className="xl:col-span-3">
          <div className="mb-4 flex gap-2">
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-xs outline-none">
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-xs outline-none">
              <option value="">All severities</option>
              <option value="MINOR">Minor</option>
              <option value="MODERATE">Moderate</option>
              <option value="MAJOR">Major</option>
            </select>
            <div className="ml-auto flex items-center text-xs text-ink-400">{filtered.length} conflicts</div>
          </div>

          <div className="card max-h-[640px] overflow-y-auto">
            {filtered.map((c) => (
              <div
                key={c.id}
                onClick={() => setSelectedId(c.id)}
                className={`cursor-pointer border-b border-ink-50 px-4 py-3.5 hover:bg-ink-50/60 ${selectedId === c.id ? 'bg-brand-50/60' : ''}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10.5px] text-ink-400">{c.id}</span>
                    <StatusBadge status={c.severity} />
                    <span className="text-xs font-semibold text-ink-800">{c.conflict_type.replace(/_/g, ' ')}</span>
                  </div>
                  <StatusBadge status={c.status} />
                </div>
                <p className="mt-1.5 text-xs text-ink-500">{c.description}</p>
                {c.recommended_action && (
                  <p className="mt-1 text-[10.5px] italic text-ink-400">Recommended: {c.recommended_action}</p>
                )}
                {selectedId === c.id && (
                  <div className="mt-3 flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
                    {STATUS_OPTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => handleResolve(c.id, s)}
                        className={`rounded-full px-2.5 py-1 text-[10.5px] font-semibold ${
                          c.status === s ? 'bg-brand-700 text-white' : 'bg-ink-100 text-ink-500 hover:bg-ink-200'
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {filtered.length === 0 && (
              <div className="py-12 text-center text-xs text-ink-400">No conflicts match these filters</div>
            )}
          </div>
        </div>

        <div className="xl:col-span-2">
          <div className="card p-4">
            <h3 className="mb-3 text-sm font-bold text-ink-800">Conflict Location</h3>
            <MapView layers={layers} highlightedIds={highlightIds} height="560px" showLayerControl={false} />
          </div>
        </div>
      </div>
    </div>
  )
}