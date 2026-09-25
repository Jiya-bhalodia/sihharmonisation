import { useMemo, useState } from 'react'
import { Layers } from 'lucide-react'
import Topbar from '../components/Topbar'
import ConfidenceBadge from '../components/ConfidenceBadge'
import { LoadingState } from '../components/LoadingState'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-[10.5px] text-ink-500">
        <span>{label}</span><span className="font-semibold text-ink-700">{value.toFixed(0)}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
        <div className="h-full rounded-full bg-brand-500" style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

export default function SpatialMatchingPage() {
  const { data: matches, loading } = useApi(() => api.getMatches({ limit: 400 }))
  const [minConfidence, setMinConfidence] = useState(0)

  const groups = useMemo(() => {
    if (!matches) return {}
    const g: Record<string, typeof matches> = {}
    for (const m of matches) {
      if (m.overall_confidence < minConfidence) continue
      g[m.matched_group_id] = g[m.matched_group_id] || []
      g[m.matched_group_id].push(m)
    }
    return g
  }, [matches, minConfidence])

  const groupIds = Object.keys(groups).slice(0, 40)

  return (
    <div>
      <Topbar title="AI Spatial Matching" subtitle="Explainable GeoAI-assisted feature matching across independently sourced datasets" />

      <div className="space-y-6 p-8">
        <div className="card flex items-center justify-between p-4">
          <div className="flex items-center gap-2 text-xs text-ink-500">
            <Layers size={14} /> {Object.keys(groups).length} matched feature groups · weighted scoring model:
            <span className="font-mono text-[10.5px] text-ink-400">
              30% proximity + 30% overlap + 20% area + 20% attribute
            </span>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-ink-400">Min confidence</label>
            <input type="range" min={0} max={100} value={minConfidence}
              onChange={(e) => setMinConfidence(parseInt(e.target.value))} className="w-32 accent-brand-600" />
            <span className="w-9 text-xs font-bold text-ink-700">{minConfidence}%</span>
          </div>
        </div>

        {loading && !matches && <div className="card"><LoadingState label="Loading match groups…" /></div>}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {groupIds.map((groupId) => {
            const records = groups[groupId]
            const overall = records.reduce((s, r) => s + r.overall_confidence, 0) / records.length
            const avg = (key: 'spatial_proximity' | 'geometry_overlap' | 'area_similarity' | 'attribute_similarity') =>
              records.reduce((s, r) => s + r[key], 0) / records.length

            return (
              <div key={groupId} className="card p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-bold text-ink-800">{groupId}</div>
                    {/* +1 accounts for the group's anchor record (typically the
                        cadastral parcel), which has no separate match row
                        since it is the reference point being matched against,
                        not a match itself. */}
                    <div className="text-[10.5px] text-ink-400">{records.length + 1} sources in this record</div>
                  </div>
                  <ConfidenceBadge value={overall} />
                </div>
                <div className="space-y-2.5">
                  <ScoreBar label="Spatial proximity" value={avg('spatial_proximity')} />
                  <ScoreBar label="Geometry overlap (IoU)" value={avg('geometry_overlap')} />
                  <ScoreBar label="Area similarity" value={avg('area_similarity')} />
                  <ScoreBar label="Attribute similarity" value={avg('attribute_similarity')} />
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-ink-50 pt-3">
                  {records.map((r) => (
                    <span key={r.id} className="rounded bg-ink-50 px-2 py-1 font-mono text-[10px] text-ink-500">
                      {r.feature_id} · {r.overall_confidence.toFixed(0)}%
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
          {!loading && groupIds.length === 0 && (
            <div className="card col-span-2 py-12 text-center text-xs text-ink-400">
              No matches yet. Run the harmonization pipeline first.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}