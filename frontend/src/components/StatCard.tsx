import type { LucideIcon } from 'lucide-react'

interface StatCardProps {
  label: string
  value: string | number
  icon: LucideIcon
  accent?: 'brand' | 'amber' | 'red' | 'ink'
  suffix?: string
  trend?: string
}

const ACCENTS = {
  brand: 'bg-brand-50 text-brand-600',
  amber: 'bg-amber-50 text-amber-600',
  red: 'bg-red-50 text-red-600',
  ink: 'bg-ink-50 text-ink-600',
}

export default function StatCard({ label, value, icon: Icon, accent = 'brand', suffix, trend }: StatCardProps) {
  return (
    <div className="card group p-4 transition duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lg">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">{label}</div>
          <div className="kpi-number mt-1.5 text-2xl font-extrabold text-ink-900">
            {value}
            {suffix && <span className="ml-0.5 text-sm font-semibold text-ink-400">{suffix}</span>}
          </div>
          {trend && <div className="mt-1 text-[11px] font-medium text-brand-600">{trend}</div>}
        </div>
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${ACCENTS[accent]} transition group-hover:scale-105`}>
          <Icon size={17} />
        </div>
      </div>
    </div>
  )
}
