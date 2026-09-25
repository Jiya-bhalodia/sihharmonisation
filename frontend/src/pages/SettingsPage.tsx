import { useState } from 'react'
import Topbar from '../components/Topbar'

export default function SettingsPage() {
  const [targetCrs, setTargetCrs] = useState('EPSG:4326')
  const [matchDistance, setMatchDistance] = useState(75)
  const [weights, setWeights] = useState({ proximity: 35, overlap: 30, area: 15, attribute: 20 })
  const [saved, setSaved] = useState(false)

  const totalWeight = weights.proximity + weights.overlap + weights.area + weights.attribute

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div>
      <Topbar title="Settings" subtitle="Pipeline configuration reference (backend values set via backend/.env)" />

      <div className="max-w-2xl space-y-6 p-8">
        <div className="card p-5">
          <h3 className="mb-1 text-sm font-bold text-ink-800">CRS Normalization</h3>
          <p className="mb-3 text-xs text-ink-400">Target coordinate reference system for all harmonized geometries.</p>
          <select value={targetCrs} onChange={(e) => setTargetCrs(e.target.value)}
            className="w-full rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none">
            <option value="EPSG:4326">EPSG:4326 (WGS 84 — Geographic)</option>
            <option value="EPSG:32643">EPSG:32643 (UTM Zone 43N)</option>
            <option value="EPSG:32644">EPSG:32644 (UTM Zone 44N)</option>
          </select>
        </div>

        <div className="card p-5">
          <h3 className="mb-1 text-sm font-bold text-ink-800">Spatial Matching</h3>
          <p className="mb-3 text-xs text-ink-400">Maximum distance (meters) to consider two features candidate matches.</p>
          <input type="range" min={20} max={200} value={matchDistance}
            onChange={(e) => setMatchDistance(parseInt(e.target.value))} className="w-full accent-brand-600" />
          <div className="mt-1 text-xs font-bold text-ink-700">{matchDistance} m</div>
        </div>

        <div className="card p-5">
          <h3 className="mb-1 text-sm font-bold text-ink-800">Matching Weight Model</h3>
          <p className="mb-3 text-xs text-ink-400">
            Weights must sum to 100%. Current total: <span className={totalWeight === 100 ? 'text-brand-600' : 'text-red-600'}>{totalWeight}%</span>
          </p>
          <div className="space-y-3">
            {(['proximity', 'overlap', 'area', 'attribute'] as const).map((key) => (
              <div key={key}>
                <div className="mb-1 flex justify-between text-xs text-ink-500">
                  <span className="capitalize">{key}</span><span>{weights[key]}%</span>
                </div>
                <input type="range" min={0} max={60} value={weights[key]}
                  onChange={(e) => setWeights({ ...weights, [key]: parseInt(e.target.value) })}
                  className="w-full accent-brand-600" />
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg bg-ink-50 px-4 py-3 text-xs text-ink-500">
          These controls illustrate pipeline configuration. To persist changes, edit the corresponding
          values in <code className="rounded bg-white px-1.5 py-0.5">backend/.env</code> or{' '}
          <code className="rounded bg-white px-1.5 py-0.5">backend/app/config.py</code> and restart the backend.
        </div>

        <button onClick={handleSave} className="rounded-lg bg-brand-700 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-800">
          {saved ? 'Saved (reference only)' : 'Save Preferences'}
        </button>
      </div>
    </div>
  )
}