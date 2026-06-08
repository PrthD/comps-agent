// Pure display helpers. No business logic; every number shown comes from the API as-is.

import type { CompStatus, Subject } from '../api'

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatKm(value: number): string {
  return `${value.toFixed(1)} km`
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

const FIELD_LABELS: Record<string, string> = {
  property_type: 'Property type',
  beds: 'Bedrooms',
  baths: 'Bathrooms',
  sqft_living: 'Living area (sqft)',
  sqft_lot: 'Lot size (sqft)',
  year_built: 'Year built',
  condition: 'Condition (1 to 5)',
  grade: 'Grade',
  lat: 'Latitude',
  lng: 'Longitude',
}

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key
}

// One tight descriptor line for the subject property (nulls omitted). Display-only, "·" separated.
export function subjectSummary(s: Subject): string {
  const parts: string[] = []
  if (s.property_type) parts.push(s.property_type.charAt(0).toUpperCase() + s.property_type.slice(1))
  if (s.beds != null && s.baths != null) parts.push(`${s.beds} bd / ${s.baths} ba`)
  else if (s.beds != null) parts.push(`${s.beds} bd`)
  else if (s.baths != null) parts.push(`${s.baths} ba`)
  if (s.sqft_living != null) parts.push(`${s.sqft_living.toLocaleString()} sqft`)
  if (s.year_built != null) parts.push(`built ${s.year_built}`)
  if (s.grade != null) parts.push(`grade ${s.grade}`)
  if (s.condition != null) parts.push(`condition ${s.condition}`)
  return parts.join(' · ')
}

const FACTOR_LABELS: Record<string, string> = {
  comp_count: 'Comps used',
  mean_distance_km: 'Mean distance',
  dispersion: 'Price dispersion',
  median_age_days: 'Median sale age',
  mean_adjustment: 'Mean adjustment',
}

export function factorLabel(key: string): string {
  return FACTOR_LABELS[key] ?? key
}

// Percentages round half-up (Math.round == floor(x+0.5)). The backend rationale formats the SAME
// source float the same way (int(x*100 + 0.5)), so the prose can never disagree with this stat row.
export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function formatFactor(key: string, value: number): string {
  if (key === 'mean_distance_km') return `${value.toFixed(1)} km`
  if (key === 'dispersion') return formatPercent(value)
  if (key === 'mean_adjustment') return formatPercent(value)
  if (key === 'median_age_days') return `${Math.round(value)} days`
  return `${Math.round(value)}`
}

// Comp status: included is neutral; every exclusion reason reads as a muted, desaturated red.
export const STATUS_LABEL: Record<CompStatus, string> = {
  included: 'Included',
  outlier: '$/sqft outlier',
  low_similarity: 'Low similarity',
  large_adjustment: 'Large adjustment',
}

export const STATUS_PILL: Record<CompStatus, string> = {
  included: 'bg-neutral-100 text-neutral-600 ring-neutral-200',
  outlier: 'bg-red-50 text-red-700 ring-red-100',
  low_similarity: 'bg-red-50 text-red-700 ring-red-100',
  large_adjustment: 'bg-red-50 text-red-700 ring-red-100',
}

// Muted pin colors for the map (single ink hue for comps, opacity encodes similarity).
export const PIN = {
  subject: '#111827',
  included: '#1b3a5b',
  excluded: '#b45454',
}

export function includedFillOpacity(similarity: number): number {
  return 0.2 + 0.6 * Math.max(0, Math.min(1, similarity))
}
