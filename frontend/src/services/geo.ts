/**
 * Helpers for turning UnifiedParcel / raw dataset rows into GeoJSON
 * Feature arrays consumable by MapView, and for building consistent
 * MapLayerConfig objects across pages.
 */
import type { Feature } from 'geojson'
import type { UnifiedParcel } from '../types'
import type { MapLayerConfig } from '../components/MapView'

export function parcelsToFeatures(parcels: UnifiedParcel[]): Feature[] {
  return parcels
    .filter((p) => p.geometry_geojson)
    .map((p) => {
      let geometry
      try {
        geometry = JSON.parse(p.geometry_geojson!)
      } catch {
        return null
      }
      return {
        type: 'Feature' as const,
        geometry,
        properties: {
          id: p.id,
          parcel_id: p.parcel_id,
          owner_name: p.owner_name,
          area: p.area ? `${p.area.toFixed(1)} m²` : 'N/A',
          land_use: p.land_use,
          confidence: `${p.confidence_score.toFixed(0)}%`,
          validation_status: p.validation_status,
          conflict_status: p.conflict_status,
        },
      }
    })
    .filter(Boolean) as Feature[]
}

export const SOURCE_TYPE_COLORS: Record<string, string> = {
  cadastral: '#146144',
  revenue: '#2c9a70',
  municipal: '#2563eb',
  gnss: '#d97706',
  ground_truth: '#7c3aed',
  utility: '#dc2626',
  drone: '#0891b2',
  unified: '#0a3324',
}

export const SOURCE_TYPE_LABELS: Record<string, string> = {
  cadastral: 'Cadastral Parcels',
  revenue: 'Revenue Records',
  municipal: 'Municipal Buildings',
  gnss: 'GNSS Survey Points',
  ground_truth: 'Ground Truth Points',
  utility: 'Utility Lines',
  drone: 'Drone-Derived Buildings',
  unified: 'Unified Land Record',
}

export function buildLayerConfig(id: string, sourceType: string, data: Feature[] | null, visible = true): MapLayerConfig {
  const geomType = data?.[0]?.geometry?.type
  const type: 'polygon' | 'point' | 'line' =
    geomType === 'Point' ? 'point' : geomType === 'LineString' || geomType === 'MultiLineString' ? 'line' : 'polygon'
  return {
    id,
    label: SOURCE_TYPE_LABELS[sourceType] || sourceType,
    color: SOURCE_TYPE_COLORS[sourceType] || '#4d5a66',
    data,
    visible,
    type,
  }
}