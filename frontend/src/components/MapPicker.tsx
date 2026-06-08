import { useEffect } from 'react'
import { CircleMarker, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import { PIN } from '../lib/format'

const KC_CENTER: [number, number] = [47.61, -122.33] // Seattle, center of the King County data region
const KC_ZOOM = 11 // tight enough to land in the data region, not the Sound / Olympics by default

function ClickCapture({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

// MapContainer.center is initial-only; recenter when the pin moves (e.g. after loading a sample).
function Recenter({ lat, lng }: { lat: number | null; lng: number | null }) {
  const map = useMap()
  useEffect(() => {
    if (lat !== null && lng !== null) map.setView([lat, lng], 13)
  }, [lat, lng, map])
  return null
}

type Props = {
  lat: number | null
  lng: number | null
  onPick: (lat: number, lng: number) => void
  highlight?: boolean
}

export default function MapPicker({ lat, lng, onPick, highlight }: Props) {
  const hasPin = lat !== null && lng !== null
  return (
    <div
      className={`overflow-hidden rounded border ${
        highlight ? 'border-red-400' : 'border-neutral-200'
      }`}
    >
      <div className="h-56 w-full">
        <MapContainer
          center={hasPin ? [lat, lng] : KC_CENTER}
          zoom={hasPin ? 13 : KC_ZOOM}
          className="h-full w-full"
          scrollWheelZoom
        >
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ClickCapture onPick={onPick} />
          <Recenter lat={lat} lng={lng} />
          {hasPin && (
            <CircleMarker
              center={[lat, lng]}
              radius={8}
              pathOptions={{ color: '#ffffff', weight: 2, fillColor: PIN.subject, fillOpacity: 1 }}
            />
          )}
        </MapContainer>
      </div>
      <div className="flex items-center justify-between border-t border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-500">
        <span>Click the map to set the subject location.</span>
        <span className="font-mono text-neutral-600">
          {hasPin ? `${lat.toFixed(4)}, ${lng.toFixed(4)}` : 'no location set'}
        </span>
      </div>
    </div>
  )
}
