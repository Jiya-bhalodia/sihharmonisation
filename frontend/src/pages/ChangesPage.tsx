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
  const { data: changes, loading, error } = useApi(() => api.getChanges(filter || undefined), [filter])

  const counts = (changes || []).reduce<Record<string, number>>((acc, c) => {
    acc[c.change_type] = (acc[c.change_type] || 0) + 1
    return acc
  }, {})

  return (
    <div>
      <Topbar title="Change Detection" subtitle="Version-over-version comparison of the unified land record" />

      <div className="space-y-6 p-8">
        <p className="text-xs text-ink-500">Changes are computed by comparing source versions using stable feature identifiers and stored geometry/attribute evidence.</p>
        <div className="card flex items-center justify-between px-5 py-4">
          <div><div className="text-[10.5px] font-semibold uppercase tracking-wide text-ink-400">{filter ? `${filter.replace(/_/g, ' ')} events` : 'Detected events'}</div>
            <div className="mt-1 text-2xl font-extrabold text-ink-900">{loading ? '…' : changes?.length ?? 0}</div></div>
          {freeDemoMode && <span className="text-xs text-ink-500">Compared against the bundled follow-up vector dataset</span>}
        </div>
        {error && <div role="alert" className="card border-red-200 bg-red-50 px-4 py-3 text-xs font-semibold text-red-700">Could not load change events: {error}</div>}
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
                <th className="px-4 py-3 font-semibold">Change Evidence</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold">Detected</th>
              </tr>
            </thead>
            <tbody>
              {(changes || []).map((c) => (
                <tr key={c.id} className="border-b border-ink-50">
                  <td className="px-4 py-3 font-mono text-[11px] font-semibold text-ink-800">{c.before?.feature_key ?? c.after?.feature_key ?? c.feature_ref}</td>
                  <td className="px-4 py-3">
                    <span className={`badge ${CHANGE_COLORS[c.change_type] || 'bg-ink-50 text-ink-600'}`}>{c.change_type.replace(/_/g, ' ')}</span>
                  </td>
                  <td className="px-4 py-3 text-ink-600">{summarizeChange(c.before, c.after, c.change_type)}</td>
                  <td className="px-4 py-3"><ConfidenceBadge value={c.confidence} showLabel={false} /></td>
                  <td className="px-4 py-3 text-ink-400">{new Date(c.detected_at).toLocaleString()}</td>
                </tr>
              ))}
              {!loading && !error && (!changes || changes.length === 0) && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-ink-400">
                  {freeDemoMode ? 'No differences were found between the available hosted vector source versions.' : 'No changes detected yet. Upload a newer dataset version and re-run harmonization.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function summarizeChange(before: Record<string, unknown> | null, after: Record<string, unknown> | null, type: string) {
  const beforeProps = (before?.properties && typeof before.properties === 'object' ? before.properties : before) as Record<string, unknown> | null
  const afterProps = (after?.properties && typeof after.properties === 'object' ? after.properties : after) as Record<string, unknown> | null
  if (type === 'new') return `Added feature${describeProperties(afterProps)}`
  if (type === 'removed') return `Feature removed${describeProperties(beforeProps)}`
  if (type === 'geometry_changed') return 'Feature geometry differs between source versions'
  const keys = [...new Set([...Object.keys(beforeProps || {}), ...Object.keys(afterProps || {})])]
    .filter((key) => key !== 'feature_key' && JSON.stringify(beforeProps?.[key]) !== JSON.stringify(afterProps?.[key]))
  if (keys.length) return `Attributes changed: ${keys.slice(0, 4).join(', ')}${keys.length > 4 ? ` +${keys.length - 4} more` : ''}`
  if (before?.geometry_geojson !== after?.geometry_geojson) return 'Geometry differs between source versions'
  return 'Source feature differs'
}

function describeProperties(properties: Record<string, unknown> | null) {
  if (!properties) return ''
  const key = properties.feature_key ?? properties.parcel_id ?? properties.linked_parcel ?? properties.building_id
  return key ? ` · ${String(key)}` : ''
}
