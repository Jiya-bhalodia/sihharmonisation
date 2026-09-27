import { FormEvent, useEffect, useState } from 'react'
import Topbar from '../components/Topbar'
import { api } from '../services/api'

type Account = { id: string; email: string; full_name: string; role: string; is_active: boolean; created_at: string }
type AuditEntry = { id: string; actor_email: string; action: string; resource_type: string; resource_id: string | null; created_at: string }
const accountRoles = ['survey_officer', 'revenue_officer', 'municipal_officer', 'reviewer', 'evaluator', 'administrator']

export default function SettingsPage() {
  const [targetCrs, setTargetCrs] = useState('EPSG:4326')
  const [matchDistance, setMatchDistance] = useState(75)
  const [weights, setWeights] = useState({ proximity: 35, overlap: 30, area: 15, attribute: 20 })
  const [saved, setSaved] = useState(false)
  const [currentRole, setCurrentRole] = useState<string | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [auditRows, setAuditRows] = useState<AuditEntry[]>([])
  const [accountError, setAccountError] = useState('')
  const [accountNotice, setAccountNotice] = useState('')
  const [accountBusy, setAccountBusy] = useState(false)
  const [newAccount, setNewAccount] = useState({ email: '', full_name: '', role: 'survey_officer', password: '' })

  const totalWeight = weights.proximity + weights.overlap + weights.area + weights.attribute

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const refreshAccounts = async () => setAccounts(await api.getUsers())
  useEffect(() => {
    api.me().then(async (session) => {
      setCurrentRole(session.role || null)
      if (session.role === 'administrator') await refreshAccounts()
    }).catch(() => setCurrentRole(null))
  }, [])

  const addAccount = async (event: FormEvent) => {
    event.preventDefault()
    setAccountBusy(true)
    setAccountError('')
    setAccountNotice('')
    try {
      await api.createUser(newAccount)
      setNewAccount({ email: '', full_name: '', role: 'survey_officer', password: '' })
      await refreshAccounts()
      setAccountNotice('Account created. Share the temporary password securely with the staff member.')
    } catch (reason) { setAccountError(reason instanceof Error ? reason.message : 'Could not create account') }
    finally { setAccountBusy(false) }
  }

  const toggleAccount = async (account: Account) => {
    setAccountError('')
    try { await api.setUserActive(account.id, !account.is_active); await refreshAccounts() }
    catch (reason) { setAccountError(reason instanceof Error ? reason.message : 'Could not update account') }
  }

  const loadAudit = async () => {
    setAccountError('')
    try { setAuditRows(await api.getAuditLog()) }
    catch (reason) { setAccountError(reason instanceof Error ? reason.message : 'Could not load audit trail') }
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

        <button onClick={handleSave} className="rounded-lg bg-brand-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-700">
          {saved ? 'Saved (reference only)' : 'Save Preferences'}
        </button>

        {currentRole === 'administrator' && <section className="card mt-8 p-5" aria-labelledby="accounts-title">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div><h3 id="accounts-title" className="text-sm font-bold text-ink-800">User accounts & roles</h3>
              <p className="mt-1 text-xs text-ink-400">Create departmental accounts and suspend access. Public sign-up is disabled.</p></div>
            <button type="button" onClick={loadAudit} className="rounded-lg border border-ink-200 px-3 py-2 text-xs font-semibold text-ink-600 hover:bg-ink-50">View audit trail</button>
          </div>

          <form onSubmit={addAccount} className="grid gap-3 rounded-lg bg-ink-50 p-4 md:grid-cols-2">
            <label className="text-xs font-semibold text-ink-600">Full name
              <input required maxLength={160} value={newAccount.full_name} onChange={(e) => setNewAccount({ ...newAccount, full_name: e.target.value })} className="mt-1 block w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-normal" />
            </label>
            <label className="text-xs font-semibold text-ink-600">Email
              <input required type="email" value={newAccount.email} onChange={(e) => setNewAccount({ ...newAccount, email: e.target.value })} className="mt-1 block w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-normal" />
            </label>
            <label className="text-xs font-semibold text-ink-600">Role
              <select value={newAccount.role} onChange={(e) => setNewAccount({ ...newAccount, role: e.target.value })} className="mt-1 block w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-normal">
                {accountRoles.map((role) => <option key={role} value={role}>{role.replace(/_/g, ' ')}</option>)}
              </select>
            </label>
            <label className="text-xs font-semibold text-ink-600">Temporary password
              <input required type="password" minLength={12} maxLength={256} autoComplete="new-password" value={newAccount.password} onChange={(e) => setNewAccount({ ...newAccount, password: e.target.value })} className="mt-1 block w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-normal" />
            </label>
            <button disabled={accountBusy} className="rounded-lg bg-brand-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50 md:col-span-2">{accountBusy ? 'Creating…' : 'Create staff account'}</button>
          </form>
          {accountError && <p role="alert" className="mt-3 text-xs text-red-700">{accountError}</p>}
          {accountNotice && <p role="status" className="mt-3 text-xs text-brand-700">{accountNotice}</p>}

          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-xs">
              <thead className="border-b border-ink-100 text-[10px] uppercase tracking-wide text-ink-400"><tr><th className="py-2">Staff member</th><th>Role</th><th>Status</th><th className="text-right">Access</th></tr></thead>
              <tbody>{accounts.map((account) => <tr key={account.id} className="border-b border-ink-50">
                <td className="py-3"><strong className="block text-ink-700">{account.full_name}</strong><span className="text-ink-400">{account.email}</span></td>
                <td className="text-ink-500">{account.role.replace(/_/g, ' ')}</td>
                <td><span className={account.is_active ? 'text-brand-700' : 'text-red-700'}>{account.is_active ? 'Active' : 'Suspended'}</span></td>
                <td className="text-right"><button type="button" onClick={() => toggleAccount(account)} className="rounded border border-ink-200 px-2.5 py-1.5 font-semibold text-ink-600 hover:bg-ink-50">{account.is_active ? 'Suspend' : 'Restore'}</button></td>
              </tr>)}</tbody>
            </table>
          </div>

          {auditRows.length > 0 && <div className="mt-6"><h4 className="mb-2 text-xs font-bold text-ink-700">Recent audit events</h4><div className="max-h-64 space-y-2 overflow-auto">
            {auditRows.map((row) => <div key={row.id} className="flex flex-wrap justify-between gap-x-4 gap-y-1 border-b border-ink-50 py-2 text-[11px]">
              <span className="font-semibold text-ink-700">{row.action}<span className="ml-2 font-normal text-ink-400">{row.resource_type}{row.resource_id ? ` · ${row.resource_id}` : ''}</span></span>
              <span className="text-ink-400">{row.actor_email} · {new Date(row.created_at).toLocaleString()}</span>
            </div>)}
          </div></div>}
        </section>}
        {currentRole !== null && currentRole !== 'administrator' && <div className="mt-8 rounded-lg bg-ink-50 p-4 text-xs text-ink-500">User administration is available to administrators only.</div>}
      </div>
    </div>
  )
}
