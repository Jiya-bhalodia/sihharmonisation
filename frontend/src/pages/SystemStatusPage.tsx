import { useEffect, useState } from 'react'
import { ExternalLink, Server, CheckCircle2 } from 'lucide-react'
import Topbar from '../components/Topbar'
import { api, API_BASE_URL } from '../services/api'
import type { SystemHealth } from '../types'

const ENDPOINTS = [
  { method: 'GET', path: '/api/health', desc: 'Liveness and demo-mode status' },
  { method: 'GET', path: '/api/datasets', desc: 'List all connected datasets' },
  { method: 'POST', path: '/api/datasets/upload', desc: 'Upload a new dataset (GeoJSON/CSV/Shapefile ZIP)' },
  { method: 'GET', path: '/api/parcels', desc: 'List unified parcels with search/filter/sort' },
  { method: 'GET', path: '/api/parcels/{id}', desc: 'Parcel detail with lineage' },
  { method: 'POST', path: '/api/harmonize', desc: 'Run the full harmonization pipeline' },
  { method: 'GET', path: '/api/harmonize/{job_id}', desc: 'Pipeline job status' },
  { method: 'GET', path: '/api/matches', desc: 'AI spatial match records with score breakdown' },
  { method: 'GET', path: '/api/mappings', desc: 'Attribute mapping table' },
  { method: 'POST', path: '/api/mappings/{id}/override', desc: 'Manually override a schema mapping' },
  { method: 'GET', path: '/api/conflicts', desc: 'List detected conflicts' },
  { method: 'POST', path: '/api/conflicts/{id}/resolve', desc: 'Update conflict resolution status' },
  { method: 'GET', path: '/api/changes', desc: 'Change detection events' },
  { method: 'GET', path: '/api/statistics', desc: 'Dashboard aggregate statistics' },
  { method: 'GET', path: '/api/data-quality', desc: 'Per-dataset quality report' },
  { method: 'GET', path: '/api/export/geojson', desc: 'Export unified records as GeoJSON' },
  { method: 'GET', path: '/api/export/csv', desc: 'Export unified records as CSV' },
]

const METHOD_COLORS: Record<string, string> = {
  GET: 'bg-blue-50 text-blue-700',
  POST: 'bg-brand-50 text-brand-700',
  DELETE: 'bg-red-50 text-red-700',
}

export default function SystemStatusPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(e.message))
  }, [])

  const apiBase = API_BASE_URL === '/api' ? window.location.origin : API_BASE_URL.replace(/\/api$/, '')

  return (
    <div>
      <Topbar title="API / System Status" subtitle="Backend health, environment, and available FastAPI endpoints" />

      <div className="space-y-6 p-8">
        <div className="card flex items-center justify-between p-5">
          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${health ? 'bg-brand-50 text-brand-600' : 'bg-red-50 text-red-600'}`}>
              <Server size={18} />
            </div>
            <div>
              <div className="text-sm font-bold text-ink-800">
                {health ? `${health.app_name} v${health.version}` : 'Backend unreachable'}
              </div>
              <div className="text-xs text-ink-400">
                {health ? `${health.database} · Target CRS ${health.target_crs}` : error || 'Ensure uvicorn is running on port 8000'}
              </div>
            </div>
          </div>
          {health && (
            <span className="badge bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200">
              <CheckCircle2 size={12} /> Online
            </span>
          )}
        </div>

        <a href={`${apiBase}/docs`} target="_blank" rel="noreferrer"
          className="card flex items-center justify-between p-5 hover:bg-ink-50/50">
          <div>
            <div className="text-sm font-bold text-ink-800">Interactive Swagger Documentation</div>
            <div className="text-xs text-ink-400">{apiBase}/docs</div>
          </div>
          <ExternalLink size={16} className="text-ink-400" />
        </a>

        <div className="card overflow-hidden">
          <div className="border-b border-ink-100 bg-ink-50 px-5 py-3 text-xs font-bold text-ink-700">
            API Endpoints ({ENDPOINTS.length})
          </div>
          <div className="divide-y divide-ink-50">
            {ENDPOINTS.map((e) => (
              <div key={e.method + e.path} className="flex items-center gap-3 px-5 py-2.5">
                <span className={`badge w-14 justify-center ${METHOD_COLORS[e.method]}`}>{e.method}</span>
                <span className="w-64 font-mono text-xs text-ink-700">{e.path}</span>
                <span className="text-xs text-ink-400">{e.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
