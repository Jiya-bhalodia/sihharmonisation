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
    res = await fetch(`${API_BASE_URL}${path}`, {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
    })
  } catch {
    throw new ApiError('Cannot reach the API. Start the backend on port 8000, then restart the frontend.', 0)
  }
  if (!res.ok) {
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
  getPilotReadiness: () => request<PilotReadiness>('/pilot/readiness'),

  exportGeojsonUrl: () => `${API_BASE_URL}/export/geojson`,
  exportCsvUrl: () => `${API_BASE_URL}/export/csv`,
}

export { ApiError }
