import { useState, useRef } from 'react'
import { Upload, FileJson, FileSpreadsheet, FileArchive, Trash2, CheckCircle2, AlertTriangle } from 'lucide-react'
import Topbar from '../components/Topbar'
import StatusBadge from '../components/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'

const SOURCE_TYPES = [
  { value: 'cadastral', label: 'Cadastral (Survey Department)' },
  { value: 'revenue', label: 'Revenue Records (Revenue Department)' },
  { value: 'municipal', label: 'Municipal Buildings (Municipal Corporation)' },
  { value: 'gnss', label: 'GNSS/CORS Points (Survey Department)' },
  { value: 'ground_truth', label: 'Ground Truth (Field Team)' },
  { value: 'utility', label: 'Utility Network (Utility Department)' },
  { value: 'drone', label: 'Drone-Derived Imagery/Buildings' },
  { value: 'orthoimagery', label: 'Orthorectified Imagery (ORI)' },
  { value: 'dsm', label: 'DSM / Surface Model' },
  { value: 'dtm', label: 'DTM / Terrain Model' },
]

const DEPARTMENTS = [
  'Revenue Department', 'Municipal Corporation', 'Survey Department',
  'Utility Department', 'Ground Truthing Team',
]

function fileIcon(name: string) {
  if (name.endsWith('.zip')) return FileArchive
  if (name.endsWith('.csv')) return FileSpreadsheet
  return FileJson
}

export default function DataSourcesPage() {
  const { data: datasets, loading, refetch } = useApi(() => api.getDatasets())
  const [showUpload, setShowUpload] = useState(false)
  const [form, setForm] = useState({ name: '', department: DEPARTMENTS[0], source_type: 'cadastral', lat_field: 'latitude', lon_field: 'longitude' })
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('name', form.name || file.name)
      fd.append('department', form.department)
      fd.append('source_type', form.source_type)
      fd.append('lat_field', form.lat_field)
      fd.append('lon_field', form.lon_field)
      await api.uploadDataset(fd)
      setShowUpload(false)
      setFile(null)
      setForm({ ...form, name: '' })
      refetch()
    } catch (e: any) {
      setUploadError(e.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Remove this dataset? This cannot be undone.')) return
    await api.deleteDataset(id)
    refetch()
  }

  return (
    <div>
      <Topbar title="Data Sources" subtitle="Ingest multi-source geospatial data from participating departments" />

      <div className="space-y-6 p-8">
        <div className="card border-brand-100 bg-brand-50/40 px-5 py-4">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-brand-600" />
            <p className="text-xs text-brand-800">
              All datasets in this demo are <strong>clearly marked SYNTHETIC DEMO DATA</strong>, generated to
              exhibit realistic real-world inconsistencies (schema mismatches, coordinate drift, duplicate IDs,
              invalid geometry) so the harmonization pipeline has something meaningful to solve.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="text-sm text-ink-500">{datasets?.length ?? 0} datasets connected</div>
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-2 rounded-lg bg-brand-700 px-4 py-2 text-xs font-bold text-white hover:bg-brand-800"
          >
            <Upload size={14} /> Upload Dataset
          </button>
        </div>

        <div className="card overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-ink-100 bg-ink-50 text-[10.5px] uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-4 py-3 font-semibold">Dataset</th>
                <th className="px-4 py-3 font-semibold">Department</th>
                <th className="px-4 py-3 font-semibold">Type</th>
                <th className="px-4 py-3 font-semibold">Geometry</th>
                <th className="px-4 py-3 font-semibold">CRS</th>
                <th className="px-4 py-3 font-semibold">Features</th>
                <th className="px-4 py-3 font-semibold">Quality</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold"></th>
              </tr>
            </thead>
            <tbody>
              {(datasets || []).map((d) => (
                <tr key={d.id} className="border-b border-ink-50 hover:bg-ink-50/50">
                  <td className="px-4 py-3 font-semibold text-ink-800">{d.name}</td>
                  <td className="px-4 py-3 text-ink-500">{d.department}</td>
                  <td className="px-4 py-3 text-ink-500">{d.source_type}</td>
                  <td className="px-4 py-3 text-ink-500">{d.geometry_type}</td>
                  <td className="px-4 py-3 font-mono text-[10.5px] text-ink-500">{d.crs}</td>
                  <td className="px-4 py-3 text-ink-700">{d.feature_count}</td>
                  <td className="px-4 py-3">
                    <span className={`badge ${d.quality_score >= 80 ? 'bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200' : 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200'}`}>
                      {d.quality_score.toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={d.status} /></td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => handleDelete(d.id)} className="rounded p-1.5 text-ink-300 hover:bg-red-50 hover:text-red-600">
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && (!datasets || datasets.length === 0) && (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-ink-400">
                  No datasets uploaded yet. Click "Upload Dataset" or run <code className="rounded bg-ink-100 px-1.5 py-0.5">python run_seed.py</code> in the backend.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-panel">
              <h3 className="text-base font-bold text-ink-900">Upload & process data</h3>
            <p className="mb-4 text-xs text-ink-400">GeoJSON, CSV, Shapefile ZIP, KML/KMZ, GeoTIFF/COG and text-based PDF land records are analysed on upload.</p>

            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-ink-500">Dataset Name</label>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Cadastral Parcels - Ward 07"
                  className="w-full rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none focus:border-brand-400" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-ink-500">Department</label>
                <select value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}
                  className="w-full rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none focus:border-brand-400">
                  {DEPARTMENTS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-ink-500">Source Type</label>
                <select value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}
                  className="w-full rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none focus:border-brand-400">
                  {SOURCE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>

              {form.source_type === 'gnss' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-ink-500">Latitude Field</label>
                    <input value={form.lat_field} onChange={(e) => setForm({ ...form, lat_field: e.target.value })}
                      className="w-full rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none focus:border-brand-400" />
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] font-semibold text-ink-500">Longitude Field</label>
                    <input value={form.lon_field} onChange={(e) => setForm({ ...form, lon_field: e.target.value })}
                      className="w-full rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none focus:border-brand-400" />
                  </div>
                </div>
              )}

              <div
                onClick={() => fileInputRef.current?.click()}
                className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-ink-200 px-4 py-6 text-center hover:border-brand-300"
              >
                {file ? (
                  <div className="flex items-center gap-2 text-xs font-semibold text-brand-700">
                    <CheckCircle2 size={16} /> {file.name}
                  </div>
                ) : (
                  <>
                    <Upload size={20} className="mb-1.5 text-ink-300" />
                    <div className="text-xs font-semibold text-ink-500">Click to select a file</div>
                    <div className="mt-0.5 text-[10.5px] text-ink-400">.geojson, .csv, .zip, .kml, .kmz, .tif, .tiff, .pdf</div>
                  </>
                )}
                <input ref={fileInputRef} type="file" accept=".geojson,.json,.csv,.zip,.kml,.kmz,.tif,.tiff,.pdf" className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </div>

              {uploadError && <p className="text-xs font-medium text-red-600">{uploadError}</p>}
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setShowUpload(false)} className="rounded-lg border border-ink-200 px-4 py-2 text-xs font-semibold text-ink-500 hover:bg-ink-50">
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="rounded-lg bg-brand-700 px-4 py-2 text-xs font-bold text-white hover:bg-brand-800 disabled:opacity-50"
              >
                {uploading ? 'Uploading…' : 'Upload & Ingest'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
