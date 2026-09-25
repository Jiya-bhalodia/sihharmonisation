import { useEffect, useState } from 'react'
import { Bell, RefreshCcw, MapPinned } from 'lucide-react'
import { api } from '../services/api'
import type { SystemHealth } from '../types'

interface TopbarProps {
  title: string
  subtitle?: string
}

export default function Topbar({ title, subtitle }: TopbarProps) {
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [lastSync, setLastSync] = useState<Date>(new Date())

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  const refresh = () => {
    api.health().then(setHealth).catch(() => setHealth(null))
    setLastSync(new Date())
  }

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-white/60 bg-white/80 px-8 py-4 backdrop-blur-xl">
      <div>
        <h1 className="text-lg font-bold text-ink-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-xs text-ink-400">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-4">
        <div className="hidden items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-[11px] font-semibold text-brand-700 xl:flex">
          <MapPinned size={13} /> Pilot workspace
        </div>
        <div className="hidden items-center gap-2 rounded-full border border-ink-100 bg-ink-50 px-3 py-1.5 text-xs text-ink-500 md:flex">
          <span className={`h-1.5 w-1.5 rounded-full ${health ? 'bg-brand-500' : 'bg-red-400'}`} />
          {health ? `System Online · ${health.database}` : 'Connecting...'}
        </div>
        <div className="hidden text-xs text-ink-400 lg:block">
          Last sync {lastSync.toLocaleTimeString()}
        </div>
        <button onClick={refresh} className="rounded-lg border border-ink-100 p-2 text-ink-400 hover:bg-ink-50 hover:text-ink-700">
          <RefreshCcw size={15} />
        </button>
        <button className="rounded-lg border border-ink-100 p-2 text-ink-400 hover:bg-ink-50 hover:text-ink-700">
          <Bell size={15} />
        </button>
        <div className="h-8 w-8 rounded-full bg-brand-700 text-center text-xs font-bold leading-8 text-white">
          MR
        </div>
      </div>
    </header>
  )
}
