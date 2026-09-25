/**
 * Core interactive GIS map component built on Leaflet/react-leaflet.
 *
 * CRITICAL FIX (senior review): the point-layer renderer previously called
 * `require('leaflet')` inside a component body. `require` does not exist
 * in a Vite/ESM bundle and this would throw at runtime the moment any
 * point layer (GNSS points, ground truth points) was rendered -- i.e. it
 * would crash on the very features most central to the demo. Leaflet is
 * now imported properly at the top of the file.
 */
import { useMemo, useState } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { PathOptions } from 'leaflet'
import type { Feature, Geometry } from 'geojson'
import { Layers as LayersIcon, Minus, Plus } from 'lucide-react'

export interface MapLayerConfig {
  id: string
  label: string
  color: string
  data: Feature[] | null
  visible: boolean
  type?: 'polygon' | 'point' | 'line'
}

interface MapViewProps {
  layers: MapLayerConfig[]
  onToggleLayer?: (id: string) => void
  onFeatureClick?: (properties: Record<string, any>, layerId: string) => void
  center?: [number, number]
  zoom?: number
  height?: string
  highlightedIds?: string[]
  showLegend?: boolean
  showLayerControl?: boolean
}

function ZoomControls() {
  const map = useMap()
  return (
    <div className="absolute right-3 top-3 z-[1000] flex flex-col overflow-hidden rounded-lg border border-ink-200 bg-white shadow-panel">
      <button onClick={() => map.zoomIn()} className="border-b border-ink-100 p-2 hover:bg-ink-50">
        <Plus size={14} />
      </button>
      <button onClick={() => map.zoomOut()} className="p-2 hover:bg-ink-50">
        <Minus size={14} />
      </button>
    </div>
  )
}

export default function MapView({
  layers,
  onToggleLayer,
  onFeatureClick,
  center = [18.5204, 73.8567],
  zoom = 15,
  height = '520px',
  highlightedIds = [],
  showLegend = true,
  showLayerControl = true,
}: MapViewProps) {
  const [opacity, setOpacity] = useState(0.75)
  const [panelOpen, setPanelOpen] = useState(true)

  const styleFor = (layer: MapLayerConfig) => (feature?: Feature<Geometry, any>): PathOptions => {
    const id = feature?.properties?.id || feature?.properties?.parcel_id || feature?.properties?.property_id
    const isHighlighted = id && highlightedIds.includes(String(id))
    return {
      color: isHighlighted ? '#dc2626' : layer.color,
      weight: isHighlighted ? 3.5 : layer.type === 'line' ? 2.5 : 1.5,
      fillColor: layer.color,
      fillOpacity: layer.type === 'line' ? 0 : opacity * 0.35,
      opacity: opacity,
      dashArray: isHighlighted ? '4 3' : undefined,
    }
  }

  const pointToLayer = (layer: MapLayerConfig) => (feature: Feature<Geometry, any>, latlng: L.LatLng) => {
    const id = feature?.properties?.id
    const isHighlighted = id && highlightedIds.includes(String(id))
    return L.circleMarker(latlng, {
      radius: isHighlighted ? 8 : 5,
      color: isHighlighted ? '#dc2626' : layer.color,
      weight: 2,
      fillColor: layer.color,
      fillOpacity: opacity * 0.7,
    })
  }

  const onEachFeature = (layer: MapLayerConfig) => (feature: Feature<Geometry, any>, leafletLayer: L.Layer) => {
    const props = feature.properties || {}
    const title = props.parcel_id || props.property_id || props.point_id || props.gt_id || props.utility_id || props.id || 'Feature'
    const rows = Object.entries(props).slice(0, 8)
      .map(([k, v]) => `<div style="display:flex;justify-content:space-between;gap:12px;padding:2px 0;border-bottom:1px solid #eef1f0"><span style="color:#71808c;font-size:11px">${k}</span><span style="font-weight:600;font-size:11px">${v}</span></div>`)
      .join('')
    leafletLayer.bindPopup(
      `<div style="min-width:200px;font-family:Inter,sans-serif">
        <div style="font-weight:800;font-size:13px;margin-bottom:6px;color:#0a3324">${title}</div>
        ${rows}
      </div>`
    )
    leafletLayer.on('click', () => {
      onFeatureClick?.(props, layer.id)
    })
  }

  const visibleLayers = useMemo(() => layers.filter((l) => l.visible && l.data && l.data.length > 0), [layers])

  return (
    <div className="map-shell relative overflow-hidden rounded-2xl border border-ink-100 shadow-inner" style={{ height }}>
      <MapContainer center={center} zoom={zoom} style={{ height: '100%', width: '100%' }} zoomControl={false}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {visibleLayers.map((layer) => (
          <GeoJSON
            key={`${layer.id}-${opacity}-${highlightedIds.join(',')}`}
            data={{ type: 'FeatureCollection', features: layer.data! } as any}
            style={styleFor(layer) as any}
            pointToLayer={layer.type === 'point' ? (pointToLayer(layer) as any) : undefined}
            onEachFeature={onEachFeature(layer)}
          />
        ))}
        <ZoomControls />
      </MapContainer>

      {showLayerControl && (
        <div className="absolute left-3 top-3 z-[1000] w-56 overflow-hidden rounded-lg border border-ink-200 bg-white shadow-panel">
          <button
            onClick={() => setPanelOpen(!panelOpen)}
            className="flex w-full items-center gap-2 border-b border-ink-100 bg-ink-50 px-3 py-2 text-xs font-bold text-ink-700"
          >
            <LayersIcon size={13} /> Layers
          </button>
          {panelOpen && (
            <div className="max-h-64 overflow-y-auto p-2.5">
              {layers.map((layer) => (
                <label key={layer.id} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1.5 text-xs hover:bg-ink-50">
                  <input
                    type="checkbox"
                    checked={layer.visible}
                    onChange={() => onToggleLayer?.(layer.id)}
                    className="h-3.5 w-3.5 accent-brand-600"
                  />
                  <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: layer.color }} />
                  <span className="flex-1 text-ink-700">{layer.label}</span>
                  <span className="text-[10px] text-ink-400">{layer.data?.length ?? 0}</span>
                </label>
              ))}
              <div className="mt-2 border-t border-ink-100 pt-2">
                <div className="mb-1 flex justify-between text-[10px] text-ink-400">
                  <span>Opacity</span><span>{Math.round(opacity * 100)}%</span>
                </div>
                <input
                  type="range" min={0.2} max={1} step={0.05}
                  value={opacity}
                  onChange={(e) => setOpacity(parseFloat(e.target.value))}
                  className="w-full accent-brand-600"
                />
              </div>
            </div>
          )}
        </div>
      )}

      {showLegend && (
        <div className="absolute bottom-3 left-3 z-[1000] rounded-lg border border-ink-200 bg-white/95 px-3 py-2 shadow-panel">
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {layers.filter((l) => l.visible).map((layer) => (
              <div key={layer.id} className="flex items-center gap-1.5 text-[10px] text-ink-500">
                <span className="h-2 w-2 rounded-sm" style={{ background: layer.color }} />
                {layer.label}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
