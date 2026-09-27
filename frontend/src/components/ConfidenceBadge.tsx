interface ConfidenceBadgeProps {
  value: number
  showLabel?: boolean
}

export function confidenceBand(value: number): 'High' | 'Medium' | 'Low' {
  if (value >= 90) return 'High'
  if (value >= 70) return 'Medium'
  return 'Low'
}

const STYLES: Record<string, string> = {
  High: 'bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200',
  Medium: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
  Low: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-200',
}

export default function ConfidenceBadge({ value, showLabel = true }: ConfidenceBadgeProps) {
  const band = confidenceBand(value)
  return (
    <span className={`badge ${STYLES[band]}`}>
      {value.toFixed(0)}%{showLabel && ` ${band}`}
    </span>
  )
}
