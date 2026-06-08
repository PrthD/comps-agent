import L from 'leaflet'
import { useEffect } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet'

import type { Subject, Valuation } from '../api'
import { PIN, STATUS_LABEL, formatCurrency, formatKm, includedFillOpacity } from '../lib/format'

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [28, 28], maxZoom: 14 })
    }
  }, [points, map])
  return null
}

function LegendDot({ color, dashed, label }: { color: string; dashed?: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="h-2.5 w-2.5 rounded-full"
        style={{
          backgroundColor: dashed ? 'transparent' : color,
          border: `1.5px ${dashed ? 'dashed' : 'solid'} ${color}`,
        }}
      />
      {label}
    </span>
  )
}

export default function CompMap({ valuation, subject }: { valuation: Valuation; subject: Subject }) {
  const subjectPos: [number, number] | null =
    subject.lat !== null && subject.lng !== null ? [subject.lat, subject.lng] : null
  const compPoints = valuation.comps.map((sc) => [sc.comp.lat, sc.comp.lng] as [number, number])
  const allPoints = subjectPos ? [subjectPos, ...compPoints] : compPoints
  const center = subjectPos ?? compPoints[0] ?? ([47.61, -122.33] as [number, number])

  return (
    <div className="space-y-2">
      <div className="h-72 w-full overflow-hidden rounded border border-neutral-200">
        <MapContainer center={center} zoom={12} className="h-full w-full" scrollWheelZoom>
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitBounds points={allPoints} />
          {valuation.comps.map((sc, i) => {
            const included = sc.status === 'included'
            const opts = included
              ? {
                  color: PIN.included,
                  weight: 1,
                  fillColor: PIN.included,
                  fillOpacity: includedFillOpacity(sc.similarity),
                }
              : {
                  color: PIN.excluded,
                  weight: 1.5,
                  fillColor: PIN.excluded,
                  fillOpacity: 0.12,
                  dashArray: '3',
                }
            return (
              <CircleMarker key={i} center={[sc.comp.lat, sc.comp.lng]} radius={6} pathOptions={opts}>
                <Popup>
                  <div className="text-xs">
                    <div className="font-mono font-semibold">
                      {formatCurrency(sc.comp.sale_price)} to {formatCurrency(sc.adjusted_price)}
                    </div>
                    <div>
                      {formatKm(sc.comp.distance_km)}, {sc.comp.sqft_living.toLocaleString()} sqft,
                      sim {(sc.similarity * 100).toFixed(0)}%
                    </div>
                    <div className="mt-0.5 text-neutral-500">{STATUS_LABEL[sc.status]}</div>
                    {sc.flag_reason && <div className="mt-0.5 text-red-700">{sc.flag_reason}</div>}
                  </div>
                </Popup>
              </CircleMarker>
            )
          })}
          {subjectPos && (
            <CircleMarker
              center={subjectPos}
              radius={9}
              pathOptions={{ color: '#ffffff', weight: 2, fillColor: PIN.subject, fillOpacity: 1 }}
            >
              <Popup>
                <div className="text-xs font-semibold">Subject property</div>
              </Popup>
            </CircleMarker>
          )}
        </MapContainer>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-neutral-500">
        <LegendDot color={PIN.subject} label="Subject" />
        <LegendDot color={PIN.included} label="Included (opacity = similarity)" />
        <LegendDot color={PIN.excluded} dashed label="Excluded" />
      </div>
    </div>
  )
}
