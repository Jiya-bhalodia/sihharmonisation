import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import {
  ArrowUpRight, CheckSquare, ClipboardCheck, Database, LogOut,
  FileBarChart, FileStack, GitMerge, History, Layers,
  Menu, ShieldAlert, X,
} from 'lucide-react'

const TOOL_LINKS = [
  { to: '/data-sources', label: 'Data Sources', icon: Database },
  { to: '/pilot-readiness', label: 'Pilot Readiness', icon: ClipboardCheck },
  { to: '/harmonization', label: 'Harmonization', icon: GitMerge },
  { to: '/spatial-matching', label: 'Spatial Matching', icon: Layers },
  { to: '/conflicts', label: 'Conflict Resolution', icon: ShieldAlert },
  { to: '/topology', label: 'Topology Validation', icon: CheckSquare },
  { to: '/changes', label: 'Change Detection', icon: History },
  { to: '/records', label: 'Unified Land Records', icon: FileStack },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
]

const HOME_LINKS = [
  ['Platform', '#capabilities', '/'],
  ['Data Sources', '#ecosystem', '/data-sources'],
  ['Workflow', '#workflow', '/harmonization'],
  ['Reports', '', '/reports'],
  ['Settings', '', '/settings'],
]

interface SidebarProps {
  user?: { full_name?: string; email?: string; role?: string } | null
  onSignOut?: () => void
}

export default function Sidebar({ user, onSignOut }: SidebarProps) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const onHome = location.pathname === '/'
  const [scrolled, setScrolled] = useState(!onHome)

  useEffect(() => {
    if (!onHome) { setScrolled(true); return }
    const update = () => setScrolled(window.scrollY > 28)
    window.addEventListener('scroll', update, { passive: true })
    update()
    return () => window.removeEventListener('scroll', update)
  }, [onHome])

  const closeMenus = () => setMobileOpen(false)

  return (
    <>
      <header className={`site-nav ${scrolled ? 'is-scrolled' : ''} app-nav ${onHome ? 'app-nav-home' : ''}`}>
        <Link to="/" className="brand" onClick={closeMenus} aria-label="BHUMI-X home">
          <span className="brand-mark"><span /><span /><span /></span><span>BHUMI-X</span>
        </Link>
        <nav className="nav-links app-nav-links" aria-label="Main navigation">
          {HOME_LINKS.map(([label, anchor, route]) => onHome && anchor
            ? <a key={label} href={anchor}>{label}</a>
            : <Link key={label} to={route}>{label}</Link>)}
        </nav>
        {user && <button type="button" className="app-auth-action" onClick={onSignOut} aria-label={`Sign out ${user.full_name || user.email}`} title={`${user.email} · ${user.role}`}>
          <LogOut size={15} aria-hidden="true" /><span>Sign out</span>
        </button>}
        <Link to="/data-sources" className="nav-cta" onClick={closeMenus}>Open tools <ArrowUpRight size={13} /></Link>
        <button className="menu-button app-menu-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation menu"><Menu size={21} /></button>
      </header>
      {mobileOpen && <div className="mobile-menu app-mobile-menu" role="dialog" aria-modal="true" aria-label="Navigation menu">
        <div className="mobile-menu-head">
          <Link to="/" className="brand" onClick={closeMenus}><span className="brand-mark"><span /><span /><span /></span><span>BHUMI-X</span></Link>
          <button className="menu-button" onClick={closeMenus} aria-label="Close navigation menu"><X size={23} /></button>
        </div>
        <div className="mobile-menu-links">
          {HOME_LINKS.map(([label, anchor, route], index) => <Link key={label} to={onHome && anchor ? `/${anchor}` : route} onClick={closeMenus}><small>0{index + 1}</small>{label}<ArrowUpRight size={18} /></Link>)}
          <span className="mobile-tools-label">Platform tools</span>
          {TOOL_LINKS.map(({ to, label }, index) => <Link key={to} to={to} onClick={closeMenus}><small>{String(index + 6).padStart(2, '0')}</small>{label}<ArrowUpRight size={18} /></Link>)}
          {user && <button type="button" className="mobile-auth-action" onClick={() => { closeMenus(); onSignOut?.() }}>
            <LogOut size={17} aria-hidden="true" /><span>Sign out</span><small>{user.full_name || user.email}</small>
          </button>}
        </div>
        <div className="mobile-menu-foot">Intelligent spatial harmonization<br />for urban land records.</div>
      </div>}
      {!onHome && <nav className="tool-rail" aria-label="Operational tools">
        <div className="tool-rail-inner">
          <span className="tool-rail-label">Tools</span>
          {TOOL_LINKS.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'tool-rail-link active' : 'tool-rail-link'}>
            <Icon size={15} aria-hidden="true" /><span>{label}</span>
          </NavLink>)}
        </div>
      </nav>}
    </>
  )
}
