/**
 * Centralized API client for the BHUMI-X backend.
 * All requests go through this module so the base URL and error
 * handling are consistent across the app.
 */
import type {
  Dataset, UnifiedParcel, MatchRecord, Conflict, ChangeEvent,
  HarmonizationJob, AttributeMapping, Statistics, DataQualityRow, SystemHealth, PilotReadiness,
} from '../types'

// In development this is proxied by Vite to 127.0.0.1:8000. For a deployed
// frontend, set VITE_API_URL to the public API URL at build time.
export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'
const TOKEN_KEY = 'bhumix_access_token'

export const getAccessToken = () => localStorage.getItem(TOKEN_KEY)
export const setAccessToken = (token: string | null) => {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    const headers = new Headers(options.headers)
    if (!(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    })
  } catch {
    throw new ApiError('Cannot reach the API. Start the backend on port 8000, then restart the frontend.', 0)
  }
  if (!res.ok) {
    if (res.status === 401 && getAccessToken()) {
      setAccessToken(null)
      window.dispatchEvent(new Event('bhumix:unauthorized'))
    }
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      // ignore parse failure
    }
    throw new ApiError(detail, res.status)
  }
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return res.json()
  }
  return res.text() as unknown as T
}

export const api = {
  health: () => request<SystemHealth>('/health'),
  me: () => request<{ authenticated: boolean; id?: string; email?: string; full_name?: string; role?: string; mode?: string }>('/auth/me'),
  login: async (email: string, password: string) => {
    const result = await request<{ access_token: string; user: { id: string; email: string; full_name: string; role: string } }>('/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password }),
    })
    setAccessToken(result.access_token)
    return result.user
  },
  logout: () => setAccessToken(null),
  getUsers: () => request<Array<{ id: string; email: string; full_name: string; role: string; is_active: boolean; created_at: string }>>('/auth/users'),
  createUser: (user: { email: string; full_name: string; role: string; password: string }) =>
    request<{ id: string; email: string; full_name: string; role: string }>('/auth/users', {
      method: 'POST', body: JSON.stringify(user),
    }),
  setUserActive: (id: string, is_active: boolean) =>
    request<{ id: string; email: string; is_active: boolean }>(`/auth/users/${id}/status`, {
      method: 'PATCH', body: JSON.stringify({ is_active }),
    }),
  getAuditLog: () => request<Array<{ id: string; actor_email: string; action: string; resource_type: string; resource_id: string | null; created_at: string }>>('/auth/audit?limit=50'),
  getApprovalRequests: () => request<Array<ApprovalRequest>>('/auth/approval-requests'),
  createApprovalRequest: (data: { email: string; full_name: string; requested_role: string }) =>
    request<ApprovalRequest>('/auth/approval-requests', { method: 'POST', body: JSON.stringify(data) }),
  decideApprovalRequest: (id: string, status: 'approved' | 'rejected') =>
    request<ApprovalRequest>(`/auth/approval-requests/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),

  getDatasets: () => request<Dataset[]>('/datasets'),
  uploadDataset: (formData: FormData) =>
    request<Dataset>('/datasets/upload', { method: 'POST', body: formData }),
  deleteDataset: (id: string) => request(`/datasets/${id}`, { method: 'DELETE' }),

  getParcels: (params: Record<string, string | number | undefined> = {}) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') query.set(k, String(v)) })
    const qs = query.toString()
    return request<UnifiedParcel[]>(`/parcels${qs ? `?${qs}` : ''}`)
  },
  getParcel: (id: string) => request<UnifiedParcel>(`/parcels/${id}`),

  runHarmonization: () => request<HarmonizationJob>('/harmonize', { method: 'POST' }),
  getJob: (jobId: string) => request<HarmonizationJob>(`/harmonize/${jobId}`),
  listJobs: () => request<HarmonizationJob[]>('/harmonize'),

  getMatches: (params: Record<string, string | number | undefined> = {}) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') query.set(k, String(v)) })
    const qs = query.toString()
    return request<MatchRecord[]>(`/matches${qs ? `?${qs}` : ''}`)
  },

  getMappings: (datasetId?: string) =>
    request<AttributeMapping[]>(`/mappings${datasetId ? `?dataset_id=${datasetId}` : ''}`),
  overrideMapping: (id: string, canonicalField: string) =>
    request<AttributeMapping>(`/mappings/${id}/override`, {
      method: 'POST',
      body: JSON.stringify({ canonical_field: canonicalField }),
    }),

  getConflicts: (params: Record<string, string | undefined> = {}) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v) query.set(k, v) })
    const qs = query.toString()
    return request<Conflict[]>(`/conflicts${qs ? `?${qs}` : ''}`)
  },
  resolveConflict: (id: string, status: string, note?: string) =>
    request<Conflict>(`/conflicts/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ status, note }),
    }),

  getChanges: (changeType?: string) =>
    request<ChangeEvent[]>(`/changes${changeType ? `?change_type=${changeType}` : ''}`),

  getStatistics: () => request<Statistics>('/statistics'),
  getDataQuality: () => request<DataQualityRow[]>('/data-quality'),
  getTopologyResults: () => request<Array<{ id: string; dataset_id: string; feature_id: string; issue_type: string | null; is_valid: boolean; corrected: boolean; original_geometry: string | null; corrected_geometry: string | null }>>('/data-quality/topology'),
  getPilotReadiness: () => request<PilotReadiness>('/pilot/readiness'),

  exportFile: async (type: 'geojson' | 'csv') => {
    const headers = new Headers()
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(`${API_BASE_URL}/export/${type}`, { headers })
    if (!response.ok) {
      if (response.status === 401 && token) {
        setAccessToken(null)
        window.dispatchEvent(new Event('bhumix:unauthorized'))
      }
      throw new ApiError(response.statusText || 'Export failed', response.status)
    }
    return response.blob()
  },
}

export { ApiError }

export interface ApprovalRequest {
  id: string
  email: string
  full_name: string
  requested_role: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  decided_at: string | null
  decided_by: string | null
}
