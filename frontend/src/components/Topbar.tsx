import { MapPinned } from 'lucide-react'

interface TopbarProps {
  title: string
  subtitle?: string
}

export default function Topbar({ title, subtitle }: TopbarProps) {
  return (
    <section className="page-heading">
      <div className="page-heading-copy">
        <div className="eyebrow"><MapPinned size={13} /> BHUMI-X / OPERATIONAL WORKSPACE</div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </section>
  )
}
