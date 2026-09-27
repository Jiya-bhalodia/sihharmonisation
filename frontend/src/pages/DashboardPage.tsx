import { useMemo } from 'react'
import {
  MapPin, Building2, Database, GitMerge, ShieldAlert, Gauge, CheckSquare, History, ArrowRight,
  Layers, Sparkles, FileCheck2,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import Topbar from '../components/Topbar'
import StatCard from '../components/StatCard'
import MapView from '../components/MapView'
import { LoadingState } from '../components/LoadingState'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { buildLayerConfig, parcelsToFeatures } from '../services/geo'

const PIE_COLORS = ['#146144', '#d97706', '#dc2626']

export default function DashboardPage() {
  const { data: stats, loading: statsLoading } = useApi(() => api.getStatistics())
  const { data: parcels } = useApi(() => api.getParcels({ limit: 300 }))
  const { data: datasets } = useApi(() => api.getDatasets())

  const parcelFeatures = useMemo(() => (parcels ? parcelsToFeatures(parcels) : []), [parcels])
  const layers = useMemo(() => [buildLayerConfig('unified-preview', 'unified', parcelFeatures)], [parcelFeatures])

  const confidenceData = stats
    ? [
        { name: 'High (90-100%)', value: stats.confidence_distribution.High },
        { name: 'Medium (70-89%)', value: stats.confidence_distribution.Medium },
        { name: 'Low (0-69%)', value: stats.confidence_distribution.Low },
      ]
    : []

  const conflictCategoryData = stats
    ? Object.entries(stats.conflict_categories).map(([name, value]) => ({
        name: name.replace(/_/g, ' '),
        value,
      }))
    : []

  const qualityData = stats?.data_quality_scores.map((d) => ({
    name: d.name.length > 18 ? d.name.slice(0, 16) + '…' : d.name,
    score: d.quality_score,
  })) || []

  const distributionData = stats?.dataset_feature_distribution.map((d) => ({
    name: d.name.length > 16 ? d.name.slice(0, 14) + '…' : d.name,
    count: d.count,
  })) || []

  return (
    <div>
      <Topbar
        title="BHUMI-X"
        subtitle="AI-Powered Urban Land Record Harmonization Platform · Ministry of Rural Development"
      />

      <div className="space-y-6 p-8">
        <section className="relative overflow-hidden rounded-3xl bg-brand-950 px-7 py-7 text-white shadow-2xl shadow-brand-950/20">
          <div className="absolute -right-16 -top-24 h-72 w-72 rounded-full bg-brand-400/20 blur-3xl" />
          <div className="absolute bottom-0 left-1/3 h-px w-2/3 bg-gradient-to-r from-transparent via-brand-300/50 to-transparent" />
          <div className="relative grid gap-6 lg:grid-cols-[1.35fr,1fr] lg:items-end">
            <div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-brand-300/25 bg-brand-400/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-brand-200">
                <span className="h-1.5 w-1.5 rounded-full bg-brand-300" /> Live harmonization workspace
              </div>
              <h2 className="max-w-xl text-2xl font-extrabold tracking-tight md:text-3xl">From fragmented maps to a trusted land record.</h2>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-brand-100/70">Upload departmental files, inspect their real spatial footprint, and produce only traceable records—every match is explainable and every conflict stays reviewable.</p>
              <div className="mt-5 flex flex-wrap gap-2">
                <Link to="/data-sources" className="rounded-xl bg-brand-600 px-3.5 py-2 text-xs font-bold text-white transition hover:bg-brand-700">Add data source</Link>
                <Link to="/harmonization" className="rounded-xl border border-white/20 px-3.5 py-2 text-xs font-bold text-white transition hover:bg-white/10">Run pipeline</Link>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2.5">
              {[
                [Layers, 'Sources', `${stats?.total_datasets ?? 0}`],
                [Sparkles, 'Matched', `${stats?.matched_features ?? 0}`],
                [FileCheck2, 'Unified', `${stats?.total_parcels ?? 0}`],
              ].map(([Icon, label, value]) => {
                const MetricIcon = Icon as typeof Layers
                return <div key={label as string} className="glass-card p-3"><MetricIcon size={16} className="text-brand-200" /><div className="mt-5 text-xl font-extrabold">{value as string}</div><div className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider text-brand-100/60">{label as string}</div></div>
              })}
            </div>
          </div>
        </section>

        {!statsLoading && stats && stats.total_datasets === 0 && (
          <div className="card flex items-center justify-between border-amber-200 bg-amber-50 px-5 py-4">
            <div>
              <div className="text-sm font-bold text-amber-800">No datasets loaded yet</div>
              <div className="text-xs text-amber-700">
                Add a source file in Data Sources, then run harmonization to generate records.
              </div>
            </div>
            <Link to="/data-sources" className="flex items-center gap-1.5 rounded-lg bg-amber-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-amber-700">
              Go to Data Sources <ArrowRight size={14} />
            </Link>
          </div>
        )}

        {statsLoading && !stats ? (
          <div className="card"><LoadingState label="Loading statistics…" /></div>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Total Parcels" value={stats?.total_parcels ?? '—'} icon={MapPin} accent="brand" />
            <StatCard label="Buildings" value={stats?.total_buildings ?? '—'} icon={Building2} accent="brand" />
            <StatCard label="Data Sources" value={stats?.total_datasets ?? '—'} icon={Database} accent="ink" />
            <StatCard label="Matched Features" value={stats?.matched_features ?? '—'} icon={GitMerge} accent="brand" />
            <StatCard label="Conflicts" value={stats?.total_conflicts ?? '—'} icon={ShieldAlert} accent="red"
              trend={stats ? `${stats.open_conflicts} open` : undefined} />
            <StatCard label="Avg. Confidence" value={stats?.average_confidence ?? '—'} suffix="%" icon={Gauge} accent="brand" />
            <StatCard label="Topology Errors" value={stats?.topology_errors ?? '—'} icon={CheckSquare} accent="amber" />
            <StatCard label="Changes Detected" value={stats?.changes_detected ?? '—'} icon={History} accent="ink" />
          </div>
        )}

        {/* Map + Distribution */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="card p-4 lg:col-span-2">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold text-ink-800">Unified Cadastral Map Preview</h3>
              <Link to="/records" className="flex items-center gap-1 text-xs font-semibold text-brand-600 hover:underline">
                Open full map <ArrowRight size={12} />
              </Link>
            </div>
            <MapView layers={layers} height="380px" showLayerControl={false} />
          </div>

          <div className="card p-4">
            <h3 className="mb-3 text-sm font-bold text-ink-800">Connected Data Sources</h3>
            <div className="space-y-2.5">
              {(datasets || []).slice(0, 6).map((d) => (
                <div key={d.id} className="flex items-center justify-between border-b border-ink-50 pb-2 last:border-0">
                  <div>
                    <div className="text-xs font-semibold text-ink-800">{d.department}</div>
                    <div className="text-[10.5px] text-ink-400">{d.feature_count} features · {d.crs}</div>
                  </div>
                  <span className="badge bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200">{d.quality_score.toFixed(0)}%</span>
                </div>
              ))}
              {(!datasets || datasets.length === 0) && (
                <div className="py-4 text-center text-xs text-ink-400">No data sources connected yet</div>
              )}
            </div>
          </div>
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="card p-4">
            <h3 className="mb-4 text-sm font-bold text-ink-800">Dataset Feature Distribution</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={distributionData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef1f0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#71808c' }} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 10, fill: '#71808c' }} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="count" fill="#146144" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card p-4">
            <h3 className="mb-4 text-sm font-bold text-ink-800">Matching Confidence Distribution</h3>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={confidenceData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={85} label>
                  {confidenceData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="card p-4">
            <h3 className="mb-4 text-sm font-bold text-ink-800">Conflict Categories</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={conflictCategoryData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#eef1f0" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10, fill: '#71808c' }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: '#71808c' }} width={130} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="value" fill="#dc2626" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card p-4">
            <h3 className="mb-4 text-sm font-bold text-ink-800">Data Quality Scores by Source</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={qualityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef1f0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#71808c' }} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 10, fill: '#71808c' }} domain={[0, 100]} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="score" fill="#2c9a70" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}
