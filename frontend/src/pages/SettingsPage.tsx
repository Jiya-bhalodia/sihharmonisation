import { FormEvent, useEffect, useState } from 'react'
import Topbar from '../components/Topbar'
import { api } from '../services/api'
import type { ApprovalRequest } from '../services/api'

type Account = { id: string; email: string; full_name: string; role: string; is_active: boolean; created_at: string }
type AuditEntry = { id: string; actor_email: string; action: string; resource_type: string; resource_id: string | null; created_at: string }
const accountRoles = ['survey_officer', 'revenue_officer', 'municipal_officer', 'reviewer', 'evaluator', 'administrator']

export default function SettingsPage() {
  const [targetCrs, setTargetCrs] = useState('EPSG:4326')
  const [matchDistance, setMatchDistance] = useState(75)
  const [weights, setWeights] = useState({ proximity: 35, overlap: 30, area: 15, attribute: 20 })
  const [currentRole, setCurrentRole] = useState<string | null>(null)
  const [freeDemoMode, setFreeDemoMode] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [auditRows, setAuditRows] = useState<AuditEntry[]>([])
  const [accountError, setAccountError] = useState('')
  const [accountNotice, setAccountNotice] = useState('')
  const [accountBusy, setAccountBusy] = useState(false)
  const [newAccount, setNewAccount] = useState({ email: '', full_name: '', role: 'survey_officer', password: '' })
  const [approvalRequests, setApprovalRequests] = useState<ApprovalRequest[]>([])
  const [newApproval, setNewApproval] = useState({ email: '', full_name: '', requested_role: 'survey_officer' })
  const [approvalError, setApprovalError] = useState('')
  const [approvalBusy, setApprovalBusy] = useState(false)

  const totalWeight = weights.proximity + weights.overlap + weights.area + weights.attribute

  const refreshAccounts = async () => setAccounts(await api.getUsers())
  const refreshApprovalRequests = async () => setApprovalRequests(await api.getApprovalRequests())
  useEffect(() => {
    Promise.all([api.me(), api.health()]).then(async ([session, health]) => {
      setCurrentRole(session.role || null)
      setFreeDemoMode(Boolean(health.free_demo_mode))
      if (session.role === 'administrator') await refreshAccounts()
      if (session.role === 'administrator' || (health.free_demo_mode && session.role === 'evaluator')) await refreshApprovalRequests()
    }).catch(() => setCurrentRole(null))
  }, [])

  const submitApprovalRequest = async (event: FormEvent) => {
    event.preventDefault()
    setApprovalBusy(true)
    setApprovalError('')
    try {
      await api.createApprovalRequest(newApproval)
      setNewApproval({ email: '', full_name: '', requested_role: 'survey_officer' })
      await refreshApprovalRequests()
    } catch (reason) { setApprovalError(reason instanceof Error ? reason.message : 'Could not submit the request') }
    finally { setApprovalBusy(false) }
  }

  const decideApproval = async (item: ApprovalRequest, status: 'approved' | 'rejected') => {
    setApprovalBusy(true)
    setApprovalError('')
    try { await api.decideApprovalRequest(item.id, status); await refreshApprovalRequests() }
    catch (reason) { setApprovalError(reason instanceof Error ? reason.message : 'Could not record the decision') }
    finally { setApprovalBusy(false) }
  }

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
      <Topbar title="Settings" subtitle="Review coordinate and matching preferences for this workspace" />

      <div className="max-w-2xl space-y-6 p-8">
        <div className="card p-5">
          <h3 className="mb-1 text-sm font-bold text-ink-800">CRS Normalization</h3>
          <p className="mb-3 text-xs text-ink-400">Coordinate reference system used when standardizing spatial layers for comparison.</p>
          <select value={targetCrs} onChange={(e) => setTargetCrs(e.target.value)}
            className="w-full rounded-lg border border-ink-200 px-3 py-2 text-xs outline-none">
            <option value="EPSG:4326">EPSG:4326 (WGS 84 — Geographic)</option>
            <option value="EPSG:32643">EPSG:32643 (UTM Zone 43N)</option>
            <option value="EPSG:32644">EPSG:32644 (UTM Zone 44N)</option>
          </select>
        </div>

        <div className="card p-5">
          <h3 className="mb-1 text-sm font-bold text-ink-800">Spatial Matching</h3>
          <p className="mb-3 text-xs text-ink-400">Distance threshold used to identify candidate features for spatial comparison.</p>
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
          Adjust the coordinate and matching values above to review a workspace configuration.
        </div>

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
        {(currentRole === 'administrator' || (freeDemoMode && currentRole === 'evaluator')) && <section className="card p-5" aria-labelledby="approval-title">
          <div className="mb-4"><h3 id="approval-title" className="text-sm font-bold text-ink-800">Access Approval Requests</h3>
            <p className="mt-1 text-xs text-ink-400">Review staff access requests and record an approval decision.</p></div>
          <form onSubmit={submitApprovalRequest} className="mb-5 grid gap-3 rounded-lg bg-ink-50 p-4 md:grid-cols-3">
            <label className="text-xs font-semibold text-ink-600">Full name<input required maxLength={160} value={newApproval.full_name} onChange={(e) => setNewApproval({ ...newApproval, full_name: e.target.value })} className="mt-1 block w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-normal" /></label>
            <label className="text-xs font-semibold text-ink-600">Email<input required type="email" value={newApproval.email} onChange={(e) => setNewApproval({ ...newApproval, email: e.target.value })} className="mt-1 block w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-normal" /></label>
            <label className="text-xs font-semibold text-ink-600">Requested role<select value={newApproval.requested_role} onChange={(e) => setNewApproval({ ...newApproval, requested_role: e.target.value })} className="mt-1 block w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-normal">{accountRoles.filter((role) => role !== 'administrator').map((role) => <option key={role} value={role}>{role.replace(/_/g, ' ')}</option>)}</select></label>
            <button disabled={approvalBusy} className="rounded-lg bg-brand-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50 md:col-span-3">{approvalBusy ? 'Submitting…' : 'Submit access request'}</button>
          </form>
          {freeDemoMode && <p className="mb-3 text-xs text-ink-400">Hosted demo decisions are saved as review records; they do not create separate login credentials.</p>}
          {approvalError && <p role="alert" className="mb-3 text-xs text-red-700">{approvalError}</p>}
          <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-xs">
            <thead className="border-b border-ink-100 text-[10px] uppercase tracking-wide text-ink-400"><tr><th className="py-2">Request</th><th>Requested role</th><th>Status</th><th className="text-right">Decision</th></tr></thead>
            <tbody>{approvalRequests.map((item) => <tr key={item.id} className="border-b border-ink-50"><td className="py-3"><strong className="block text-ink-700">{item.full_name}</strong><span className="text-ink-400">{item.email}</span></td><td className="text-ink-500">{item.requested_role.replace(/_/g, ' ')}</td><td className="capitalize text-ink-600">{item.status}</td><td className="text-right">{item.status === 'pending' ? <span className="inline-flex gap-2"><button disabled={approvalBusy} onClick={() => void decideApproval(item, 'approved')} className="rounded border border-brand-200 px-2 py-1 font-semibold text-brand-700 disabled:opacity-50">Approve</button><button disabled={approvalBusy} onClick={() => void decideApproval(item, 'rejected')} className="rounded border border-red-200 px-2 py-1 font-semibold text-red-700 disabled:opacity-50">Reject</button></span> : item.decided_at ? <span className="text-ink-400">{new Date(item.decided_at).toLocaleDateString()}</span> : '—'}</td></tr>)}
              {approvalRequests.length === 0 && <tr><td colSpan={4} className="py-8 text-center text-ink-400">No access requests have been submitted.</td></tr>}</tbody>
          </table></div>
        </section>}
      </div>
    </div>
  )
}
