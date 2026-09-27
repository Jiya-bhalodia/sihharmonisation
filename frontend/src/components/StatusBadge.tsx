interface StatusBadgeProps {
  status: string
}

const STYLE_MAP: Record<string, string> = {
  PASSED: 'bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200',
  FAILED: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200',
  PENDING: 'bg-ink-100 text-ink-500 ring-1 ring-inset ring-ink-200',
  NONE: 'bg-ink-100 text-ink-500 ring-1 ring-inset ring-ink-200',
  MINOR: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
  MODERATE: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
  MAJOR: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200',
  Open: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200',
  'Under Review': 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
  Resolved: 'bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200',
  Accepted: 'bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200',
  Rejected: 'bg-ink-100 text-ink-500 ring-1 ring-inset ring-ink-200',
  uploaded: 'bg-ink-100 text-ink-500 ring-1 ring-inset ring-ink-200',
  processing: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
  harmonized: 'bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200',
  error: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200',
  completed: 'bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200',
  running: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
  failed: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200',
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`badge ${STYLE_MAP[status] || 'bg-ink-100 text-ink-500'}`}>{status}</span>
}
