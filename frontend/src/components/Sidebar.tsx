import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Database, Layers, GitMerge, ShieldAlert,
  CheckSquare, History, FileStack, FileBarChart, Server, Settings, Landmark,
  ClipboardCheck,
} from 'lucide-react'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/data-sources', label: 'Data Sources', icon: Database },
  { to: '/pilot-readiness', label: 'Pilot Readiness', icon: ClipboardCheck },
  { to: '/harmonization', label: 'Harmonization', icon: GitMerge },
  { to: '/spatial-matching', label: 'Spatial Matching', icon: Layers },
  { to: '/conflicts', label: 'Conflict Resolution', icon: ShieldAlert },
  { to: '/topology', label: 'Topology Validation', icon: CheckSquare },
  { to: '/changes', label: 'Change Detection', icon: History },
  { to: '/records', label: 'Unified Land Records', icon: FileStack },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
  { to: '/system', label: 'API / System Status', icon: Server },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 z-30 flex h-full w-64 flex-col border-r border-brand-900/40 bg-brand-950 text-white shadow-2xl">
      <div className="flex items-center gap-2.5 border-b border-white/10 px-5 py-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-400 text-brand-950 shadow-lg shadow-brand-400/20">
          <Landmark size={18} />
        </div>
        <div>
          <div className="text-[15px] font-extrabold leading-none tracking-tight text-white">BHUMI-X</div>
          <div className="mt-1 text-[10px] font-medium uppercase tracking-[0.16em] text-brand-200">Land Intelligence System</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                    isActive
                      ? 'bg-white/14 text-white shadow-sm ring-1 ring-inset ring-white/10'
                      : 'text-brand-100/75 hover:bg-white/8 hover:text-white'
                  }`
                }
              >
                <item.icon size={16} strokeWidth={2} />
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-white/10 px-4 py-4">
        <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-3">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-100">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-300 shadow-[0_0_10px_#5fbd94]" />
            SYSTEM ONLINE
          </div>
          <div className="mt-1 text-[10.5px] leading-relaxed text-brand-100/60">Ingest · harmonize · verify<br />Every output retains lineage.</div>
        </div>
      </div>
    </aside>
  )
}
