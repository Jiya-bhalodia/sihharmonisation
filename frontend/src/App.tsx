import { FormEvent, lazy, Suspense, useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import { api, getAccessToken } from './services/api'

const DataSourcesPage = lazy(() => import('./pages/DataSourcesPage'))
const HarmonizationPage = lazy(() => import('./pages/HarmonizationPage'))
const SpatialMatchingPage = lazy(() => import('./pages/SpatialMatchingPage'))
const ConflictsPage = lazy(() => import('./pages/ConflictsPage'))
const TopologyPage = lazy(() => import('./pages/TopologyPage'))
const ChangesPage = lazy(() => import('./pages/ChangesPage'))
const RecordsPage = lazy(() => import('./pages/RecordsPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const PilotReadinessPage = lazy(() => import('./pages/PilotReadinessPage'))
const LandingPage = lazy(() => import('./pages/LandingPage'))

export default function App() {
  const { pathname } = useLocation()
  const isLandingPage = pathname === '/'
  const [authState, setAuthState] = useState<'checking' | 'login' | 'ready' | 'unavailable'>('checking')
  const [user, setUser] = useState<{ full_name?: string; email?: string; role?: string } | null>(null)
  const [freeDemoMode, setFreeDemoMode] = useState(false)
  const [freeDemoLimits, setFreeDemoLimits] = useState({ maxUploadMb: 2, maxDatasets: 20, maxFeatures: 1000 })

  useEffect(() => {
    let active = true
    api.health().then(async (health) => {
      if (!active) return
      setFreeDemoMode(health.free_demo_mode === true)
      if (health.free_demo_limits) setFreeDemoLimits({
        maxUploadMb: health.free_demo_limits.max_upload_mb,
        maxDatasets: health.free_demo_limits.max_datasets,
        maxFeatures: health.free_demo_limits.max_features,
      })
      if (health.demo_mode) { setAuthState('ready'); return }
      if (!getAccessToken()) { setAuthState('login'); return }
      try {
        const session = await api.me()
        if (active) { setUser(session); setAuthState('ready') }
      } catch {
        if (active) setAuthState('login')
      }
    }).catch(() => { if (active) setAuthState('unavailable') })
    const onUnauthorized = () => { setUser(null); setAuthState('login') }
    window.addEventListener('bhumix:unauthorized', onUnauthorized)
    return () => { active = false; window.removeEventListener('bhumix:unauthorized', onUnauthorized) }
  }, [])

  if (authState === 'checking') return <div className="route-loading" role="status">Connecting to BHUMI-X…</div>
  if (authState === 'unavailable') return <div className="route-loading" role="alert">The BHUMI-X API is unavailable. Check the backend connection and reload.</div>
  if (authState === 'login') return <LoginScreen onLogin={(session) => { setUser(session); setAuthState('ready') }} />

  return (
    <div className="platform-app">
      <Sidebar user={user} onSignOut={() => { api.logout(); setUser(null); setAuthState('login') }} />
      <main className={`platform-main${isLandingPage ? ' home-main' : ''}`}>
        {freeDemoMode && <div className="demo-notice mx-3 mt-3 flex flex-wrap items-start gap-x-2 gap-y-1 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs text-brand-900 md:mx-8 md:mt-4 md:px-4 md:py-2.5" role="note">
          <strong>BHUMI-X Evaluation Demo</strong>
          <span>Some advanced processing features are disabled in this hosted evaluation environment. Only bounded CSV/GeoJSON vector workflows are enabled.</span>
        </div>}
        <Suspense fallback={<div className="route-loading" role="status" aria-live="polite">Loading page…</div>}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/workspace" element={<Navigate to="/" replace />} />
            <Route path="/data-sources" element={<DataSourcesPage userRole={user?.role} freeDemoMode={freeDemoMode} freeDemoLimits={freeDemoLimits} />} />
            <Route path="/harmonization" element={<HarmonizationPage userRole={user?.role} freeDemoMode={freeDemoMode} />} />
            <Route path="/spatial-matching" element={<SpatialMatchingPage />} />
            <Route path="/conflicts" element={<ConflictsPage userRole={user?.role} />} />
            <Route path="/topology" element={<TopologyPage />} />
            <Route path="/changes" element={<ChangesPage />} />
            <Route path="/records" element={<RecordsPage userRole={user?.role} />} />
            <Route path="/reports" element={<ReportsPage userRole={user?.role} freeDemoMode={freeDemoMode} />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/pilot-readiness" element={<PilotReadinessPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}

function LoginScreen({ onLogin }: { onLogin: (user: { full_name?: string; email?: string; role?: string }) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try { onLogin(await api.login(email, password)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Sign in failed') }
    finally { setBusy(false) }
  }
  return <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: 'linear-gradient(145deg,#f0f7f4,#e3eeeb)' }}>
    <form onSubmit={submit} style={{ width: 'min(100%,420px)', padding: 32, border: '1px solid #d6e2dd', borderRadius: 12, background: '#fff', boxShadow: '0 20px 60px rgba(23,52,71,.12)' }}>
      <p style={{ margin: '0 0 8px', color: '#43836e', fontSize: 11, fontWeight: 700, letterSpacing: '.12em' }}>BHUMI-X · SECURE WORKSPACE</p>
      <h1 style={{ margin: '0 0 8px', color: '#173447', fontFamily: 'Georgia,serif', fontSize: 34, fontWeight: 400 }}>Sign in</h1>
      <p style={{ margin: '0 0 24px', color: '#60736d', fontSize: 13 }}>Use your departmental account to access the land records workspace.</p>
      <label style={{ display: 'block', marginBottom: 14, color: '#334b45', fontSize: 12, fontWeight: 600 }}>Email
        <input required type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} style={{ display: 'block', width: '100%', marginTop: 6, padding: 11, border: '1px solid #cbd8d3', borderRadius: 6 }} />
      </label>
      <label style={{ display: 'block', marginBottom: 18, color: '#334b45', fontSize: 12, fontWeight: 600 }}>Password
        <input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} style={{ display: 'block', width: '100%', marginTop: 6, padding: 11, border: '1px solid #cbd8d3', borderRadius: 6 }} />
      </label>
      {error && <p role="alert" style={{ margin: '0 0 14px', color: '#a43f37', fontSize: 12 }}>{error}</p>}
      <button disabled={busy} type="submit" style={{ width: '100%', padding: 12, border: 0, borderRadius: 6, background: '#1d5b68', color: 'white', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>{busy ? 'Signing in…' : 'Sign in securely'}</button>
      <p style={{ margin: '16px 0 0', color: '#71817c', fontSize: 11, textAlign: 'center' }}>No public sign-up. Ask your BHUMI-X administrator to create your account.</p>
    </form>
  </main>
}
