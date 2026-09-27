import { useMemo, useState } from 'react'
import { Search, Download, Map as MapIcon, Table as TableIcon, X } from 'lucide-react'
import Topbar from '../components/Topbar'
import ConfidenceBadge from '../components/ConfidenceBadge'
import StatusBadge from '../components/StatusBadge'
import MapView from '../components/MapView'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { buildLayerConfig, parcelsToFeatures } from '../services/geo'
import type { UnifiedParcel } from '../types'

export default function RecordsPage({ userRole }: { userRole?: string }) {
  const [view, setView] = useState<'table' | 'map'>('table')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('confidence_score')
  const [selected, setSelected] = useState<UnifiedParcel | null>(null)

  const { data: parcels, loading } = useApi(
    () => api.getParcels({ search: search || undefined, sort_by: sortBy, sort_dir: 'desc', limit: 500 }),
    [search, sortBy]
  )

  const parcelFeatures = useMemo(() => (parcels ? parcelsToFeatures(parcels) : []), [parcels])
  const layers = useMemo(() => [buildLayerConfig('unified-records', 'unified', parcelFeatures)], [parcelFeatures])

  const handleFeatureClick = (props: Record<string, any>) => {
    const parcel = (parcels || []).find((p) => p.id === props.id)
    if (parcel) setSelected(parcel)
  }

  const download = async (type: 'geojson' | 'csv') => {
    const blob = await api.exportFile(type)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = type === 'csv' ? 'bhumix_unified_land_records.csv' : 'bhumix_unified_land_records.geojson'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <Topbar title="Unified Land Records" subtitle="Canonical, harmonized cadastral/urban land dataset with full source lineage" />

      <div className="space-y-6 p-8">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 items-center gap-2 rounded-lg border border-ink-200 bg-white px-3 py-2">
            <Search size={14} className="text-ink-300" />
            <input
              value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by parcel ID or owner name…"
              className="flex-1 text-xs outline-none"
            />
          </div>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}
            className="rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none">
            <option value="confidence_score">Sort: Confidence</option>
            <option value="area">Sort: Area</option>
            <option value="last_updated">Sort: Last Updated</option>
          </select>
          <div className="flex overflow-hidden rounded-lg border border-ink-200">
            <button onClick={() => setView('table')} className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold ${view === 'table' ? 'bg-brand-600 text-white' : 'bg-white text-ink-500'}`}>
              <TableIcon size={13} /> Table
            </button>
            <button onClick={() => setView('map')} className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold ${view === 'map' ? 'bg-brand-600 text-white' : 'bg-white text-ink-500'}`}>
              <MapIcon size={13} /> Map
            </button>
          </div>
          {userRole !== 'evaluator' && <button onClick={() => download('geojson')} className="flex items-center gap-1.5 rounded-lg border border-ink-200 px-3 py-2 text-xs font-semibold text-ink-600 hover:bg-ink-50">
            <Download size={13} /> GeoJSON
          </button>}
          {userRole !== 'evaluator' && <button onClick={() => download('csv')} className="flex items-center gap-1.5 rounded-lg border border-ink-200 px-3 py-2 text-xs font-semibold text-ink-600 hover:bg-ink-50">
            <Download size={13} /> CSV
          </button>}
        </div>

        {view === 'map' ? (
          <div className="card p-4">
            <MapView layers={layers} onFeatureClick={handleFeatureClick} height="600px" />
          </div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-ink-100 bg-ink-50 text-[10.5px] uppercase tracking-wide text-ink-400">
                <tr>
                  <th className="px-4 py-3 font-semibold">Parcel ID</th>
                  <th className="px-4 py-3 font-semibold">Owner</th>
                  <th className="px-4 py-3 font-semibold">Area (m²)</th>
                  <th className="px-4 py-3 font-semibold">Land Use</th>
                  <th className="px-4 py-3 font-semibold">Buildings</th>
                  <th className="px-4 py-3 font-semibold">Sources</th>
                  <th className="px-4 py-3 font-semibold">Confidence</th>
                  <th className="px-4 py-3 font-semibold">Validation</th>
                  <th className="px-4 py-3 font-semibold">Conflicts</th>
                </tr>
              </thead>
              <tbody>
                {(parcels || []).map((p) => (
                  <tr key={p.id} onClick={() => setSelected(p)} className="cursor-pointer border-b border-ink-50 hover:bg-ink-50/50">
                    <td className="px-4 py-3 font-mono font-bold text-ink-800">{p.parcel_id}</td>
                    <td className="px-4 py-3 text-ink-600">{p.owner_name}</td>
                    <td className="px-4 py-3 text-ink-600">{p.area?.toFixed(1) ?? '—'}</td>
                    <td className="px-4 py-3 text-ink-600">{p.land_use}</td>
                    <td className="px-4 py-3 text-ink-600">{p.building_count}</td>
                    <td className="px-4 py-3 text-ink-600">{p.source_count}</td>
                    <td className="px-4 py-3"><ConfidenceBadge value={p.confidence_score} showLabel={false} /></td>
                    <td className="px-4 py-3"><StatusBadge status={p.validation_status} /></td>
                    <td className="px-4 py-3"><StatusBadge status={p.conflict_status} /></td>
                  </tr>
                ))}
                {!loading && (!parcels || parcels.length === 0) && (
                  <tr><td colSpan={9} className="px-4 py-10 text-center text-ink-400">
                    No unified records yet. Run the harmonization pipeline first.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && <ParcelDetailPanel parcel={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function ParcelDetailPanel({ parcel, onClose }: { parcel: UnifiedParcel; onClose: () => void }) {
  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-ink-100 bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-ink-100 px-5 py-4">
        <div>
          <div className="text-[10.5px] font-semibold uppercase tracking-wide text-ink-400">Parcel</div>
          <div className="text-lg font-extrabold text-ink-900">{parcel.parcel_id}</div>
        </div>
        <button onClick={onClose} className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-50"><X size={16} /></button>
      </div>

      <div className="space-y-5 p-5">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Survey Number" value={parcel.survey_number || '—'} />
          <Field label="Owner" value={parcel.owner_name || '—'} />
          <Field label="Area" value={parcel.area ? `${parcel.area.toFixed(1)} m²` : '—'} />
          <Field label="Land Use" value={parcel.land_use || '—'} />
          <Field label="Buildings" value={String(parcel.building_count)} />
          <Field label="Utilities" value={String(parcel.utility_count)} />
          <Field label="GNSS Verified" value={parcel.gnss_verified ? 'YES' : 'NO'} />
          <Field label="Ground Truth" value={parcel.ground_truth_verified ? 'YES' : 'NO'} />
          <Field label="Source Count" value={String(parcel.source_count)} />
          <Field label="Validation" value={parcel.validation_status} />
        </div>

        <div>
          <div className="mb-2 text-xs font-bold text-ink-700">Confidence Breakdown</div>
          <div className="flex items-center gap-2">
            <ConfidenceBadge value={parcel.confidence_score} />
            <span className="text-[10.5px] text-ink-400">Overall</span>
          </div>
          <div className="mt-3 space-y-2">
            {[
              ['Spatial', parcel.spatial_confidence],
              ['Attribute', parcel.attribute_confidence],
              ['Geometry', parcel.geometry_confidence],
              ['Source Agreement', parcel.source_agreement],
            ].map(([label, val]) => (
              <div key={label as string}>
                <div className="mb-1 flex justify-between text-[10.5px] text-ink-500">
                  <span>{label}</span><span>{(val as number).toFixed(0)}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
                  <div className="h-full rounded-full bg-brand-500" style={{ width: `${val}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-bold text-ink-700">Conflicts</span>
            <StatusBadge status={parcel.conflict_status} />
          </div>
        </div>

        <div>
          <div className="mb-2 text-xs font-bold text-ink-700">Data Lineage</div>
          <div className="space-y-2">
            {Object.entries(parcel.lineage || {}).map(([sourceType, info]) => (
              <div key={sourceType} className="rounded-lg border border-ink-100 bg-ink-50 px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold capitalize text-ink-800">{sourceType.replace(/_/g, ' ')}</span>
                  <span className="badge bg-white text-ink-500 ring-1 ring-inset ring-ink-200">{info.confidence.toFixed(0)}%</span>
                </div>
                <div className="mt-1 text-[10.5px] text-ink-400">{info.dataset_name}</div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {info.contributed_fields.slice(0, 6).map((f) => (
                    <span key={f} className="rounded bg-white px-1.5 py-0.5 font-mono text-[9.5px] text-ink-400">{f}</span>
                  ))}
                </div>
              </div>
            ))}
            {Object.keys(parcel.lineage || {}).length === 0 && (
              <div className="text-[10.5px] text-ink-400">No lineage data recorded</div>
            )}
          </div>
        </div>

        <div className="text-[10.5px] text-ink-400">
          Last updated {new Date(parcel.last_updated).toLocaleString()}
        </div>
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">{label}</div>
      <div className="mt-0.5 text-xs font-semibold text-ink-800">{value}</div>
    </div>
  )
}
