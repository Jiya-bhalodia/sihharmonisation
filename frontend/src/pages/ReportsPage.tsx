import { Download } from 'lucide-react'
import { useState } from 'react'
import Topbar from '../components/Topbar'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function ReportsPage({ userRole, freeDemoMode = false }: { userRole?: string; freeDemoMode?: boolean }) {
  const { data: stats } = useApi(() => api.getStatistics())
  const { data: quality } = useApi(() => api.getDataQuality())
  const { data: conflicts } = useApi(() => api.getConflicts())
  const { data: changes } = useApi(() => api.getChanges())
  const [changeExportError, setChangeExportError] = useState('')

  const reports = [
    {
      title: 'Harmonization Report',
      description: 'Overall pipeline outcomes: datasets processed, features matched, confidence distribution.',
      data: stats,
      filename: 'bhumix_harmonization_report.json',
    },
    {
      title: 'Data Quality Report',
      description: 'Per-dataset quality scores, geometry validity, and CRS status.',
      data: quality,
      filename: 'bhumix_data_quality_report.json',
    },
    {
      title: 'Conflict Report',
      description: 'All detected spatial and attribute conflicts with severity and resolution status.',
      data: conflicts,
      filename: 'bhumix_conflict_report.json',
    },
    {
      title: 'Change Detection Report',
      description: freeDemoMode ? 'Snapshot and raster change detection are disabled in the hosted evaluation profile; no vector before/after report is claimed.' : 'New, removed, and modified features detected across harmonization runs.',
      data: changes,
      filename: 'bhumix_change_report.json',
    },
  ]

  const exportReport = async (report: typeof reports[number]) => {
    if (report.title === 'Change Detection Report') setChangeExportError('')
    try {
      const data = report.data ?? (report.title === 'Change Detection Report' ? await api.getChanges() : null)
      if (data !== null) downloadJson(report.filename, data)
    } catch (error) {
      if (report.title === 'Change Detection Report') {
        setChangeExportError(error instanceof Error ? error.message : 'Could not load the change detection report.')
      }
    }
  }

  return (
    <div>
      <Topbar title="Reports" subtitle="Review harmonization, quality, conflict, and change-detection results" />

      <div className="space-y-6 p-8">
        {stats && (
          <div className="card grid grid-cols-2 gap-4 p-5 md:grid-cols-4">
            <div><div className="text-[10.5px] text-ink-400">Total Records</div><div className="text-xl font-extrabold text-ink-900">{stats.total_parcels}</div></div>
            <div><div className="text-[10.5px] text-ink-400">Matched</div><div className="text-xl font-extrabold text-ink-900">{stats.matched_features}</div></div>
            <div><div className="text-[10.5px] text-ink-400">Conflicts</div><div className="text-xl font-extrabold text-ink-900">{stats.total_conflicts}</div></div>
            <div><div className="text-[10.5px] text-ink-400">Avg. Confidence</div><div className="text-xl font-extrabold text-ink-900">{stats.average_confidence}%</div></div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {reports.map((r) => (
            <div key={r.title} className="card flex flex-col justify-between p-5">
              <div>
                <h3 className="text-sm font-bold text-ink-800">{r.title}</h3>
                <p className="mt-1.5 text-xs text-ink-400">{r.description}</p>
              </div>
              {userRole !== 'evaluator' && <div className="mt-4 flex gap-2">
                <button
                  onClick={() => { void exportReport(r) }}
                  disabled={!r.data && r.title !== 'Change Detection Report'}
                  className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-brand-700 disabled:opacity-50"
                >
                  <Download size={13} /> Export JSON
                </button>
              </div>}
              {r.title === 'Change Detection Report' && changeExportError && <p role="alert" className="mt-3 text-xs text-red-700">Could not export report: {changeExportError}</p>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
