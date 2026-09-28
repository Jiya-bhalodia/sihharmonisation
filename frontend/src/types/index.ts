export interface Dataset {
  id: string
  name: string
  department: string
  source_type: string
  provenance: string
  geometry_type: string | null
  crs: string | null
  feature_count: number
  quality_score: number
  status: string
  uploaded_at: string
}

export interface UnifiedParcel {
  id: string
  parcel_id: string
  survey_number: string | null
  owner_name: string | null
  area: number | null
  land_use: string | null
  geometry_geojson: string | null
  building_count: number
  utility_count: number
  gnss_verified: boolean
  ground_truth_verified: boolean
  source_count: number
  confidence_score: number
  spatial_confidence: number
  attribute_confidence: number
  geometry_confidence: number
  source_agreement: number
  validation_status: string
  conflict_status: string
  lineage: Record<string, {
    dataset_id: string
    dataset_name: string
    provenance?: string
    feature_id: string
    contributed_fields: string[]
    confidence: number
  }>
  last_updated: string
}

export interface MatchRecord {
  id: string
  matched_group_id: string
  feature_id: string
  dataset_id: string
  parcel_unified_id: string | null
  spatial_proximity: number
  geometry_overlap: number
  area_similarity: number
  attribute_similarity: number
  overall_confidence: number
}

export interface Conflict {
  id: string
  conflict_type: string
  severity: 'MINOR' | 'MODERATE' | 'MAJOR'
  feature_ref: string | null
  source_a: string | null
  source_b: string | null
  description: string | null
  confidence: number
  recommended_action: string | null
  status: 'Open' | 'Under Review' | 'Resolved' | 'Accepted' | 'Rejected'
  parcel_id: string | null
  created_at: string
}

export interface ChangeEvent {
  id: string
  feature_ref: string
  change_type: string
  before: Record<string, any> | null
  after: Record<string, any> | null
  confidence: number
  detected_at: string
}

export interface HarmonizationStage {
  name: string
  status: string
  processed: number
  warnings: number
  errors: number
  detail: string
  timestamp: string
}

export interface HarmonizationJob {
  id: string
  status: string
  stages: HarmonizationStage[]
  total_processed: number
  started_at: string
  completed_at: string | null
}

export interface AttributeMapping {
  id: string
  dataset_id: string
  source_field: string
  canonical_field: string
  confidence: number
  method: string
  manual_override: boolean
}

export interface Statistics {
  total_parcels: number
  total_buildings: number
  total_datasets: number
  matched_features: number
  total_conflicts: number
  open_conflicts: number
  average_confidence: number
  topology_errors: number
  changes_detected: number
  dataset_feature_distribution: { name: string; source_type: string; count: number }[]
  confidence_distribution: { High: number; Medium: number; Low: number }
  conflict_categories: Record<string, number>
  data_quality_scores: { name: string; quality_score: number }[]
}

export interface DataQualityRow {
  dataset_id: string
  name: string
  department: string
  source_type: string
  feature_count: number
  quality_score: number
  invalid_geometry_count: number
  crs: string | null
  status: string
}

export interface SystemHealth {
  status: string
  app_name: string
  version: string
  demo_mode: boolean
  free_demo_mode?: boolean
  disabled_features?: string[]
  free_demo_limits?: { max_upload_mb: number; max_datasets: number; max_features: number; max_geometry_complexity: number; max_processing_seconds: number } | null
  uptime_seconds: number
  database: string
  target_crs: string
}

export interface PilotReadinessCheck {
  id: string
  required: boolean
  status: 'PASS' | 'BLOCKER' | 'RECOMMENDED' | 'LIMITATION'
  title: string
  detail: string
  action: string
}

export interface PilotReadiness {
  status: 'READY_FOR_REVIEW' | 'DEMO_READY' | 'NOT_READY'
  blocker_count: number
  checks: PilotReadinessCheck[]
  disclaimer: string
  limitations?: string[]
}
