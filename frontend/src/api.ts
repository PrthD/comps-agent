// Typed client for the FastAPI backend. These interfaces mirror the pydantic schemas (schemas.py);
// every numeric field is produced by the deterministic core, the UI only displays them.

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

export type PropertyType = string
export type Confidence = 'High' | 'Medium' | 'Low'
export type Mode = 'agent' | 'deterministic'
export type CompStatus = 'included' | 'outlier' | 'low_similarity' | 'large_adjustment'

/** Subject mirrors schemas.Subject: value-critical fields are nullable on the wire (null = "not
 *  provided"); the backend completeness gate rejects a subject still missing any of them. */
export interface Subject {
  property_type: PropertyType
  beds: number | null
  baths: number | null
  sqft_living: number | null
  sqft_lot: number | null
  year_built: number | null
  condition: number | null
  grade: number | null
  lat: number | null
  lng: number | null
  as_of_date: string // ISO date (YYYY-MM-DD)
  field_confidence?: Record<string, number> | null
  needs_review?: string[] | null
}

export interface Comp {
  property_type: PropertyType
  beds: number
  baths: number
  sqft_living: number
  sqft_lot: number | null
  year_built: number | null
  condition: number | null
  grade: number | null
  lat: number
  lng: number
  sale_price: number
  sale_date: string
  price_per_sqft: number
  distance_km: number
}

export interface ScoredComp {
  comp: Comp
  similarity: number
  subscores: Record<string, number>
  adjustments: Record<string, number>
  adjusted_price: number
  flagged: boolean
  flag_reason: string | null
  status: CompStatus
}

export interface Valuation {
  conservative_value: number
  point_estimate: number
  range_low: number
  range_high: number
  confidence: Confidence
  confidence_factors: Record<string, number>
  comps: ScoredComp[]
  rationale: string
  mode: Mode
  elapsed_ms: number
}

/** The async second phase: the prose rationale + how it was produced (mirrors schemas.Rationale). */
export interface Rationale {
  rationale: string
  mode: Mode
}

export interface Sample {
  id: string
  label: string
  description: string
  subject: Subject
}

export interface HealthStatus {
  status: string
  model_available: boolean
  comps_loaded: number
}

/** The distinct 422 the completeness gate returns (NOT a generic error). */
export interface IncompleteSubject {
  error: 'incomplete_subject'
  missing_fields: string[]
  message: string
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
    if (typeof body?.message === 'string') return body.message
    return JSON.stringify(body)
  } catch {
    return res.statusText || `HTTP ${res.status}`
  }
}

export async function getHealth(signal?: AbortSignal): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/api/health`, { signal })
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  return res.json()
}

export async function getSamples(): Promise<Sample[]> {
  const res = await fetch(`${API_BASE}/api/samples`)
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  return res.json()
}

/** POST /api/extract, multipart file OR text. Extraction only; never auto-values. */
export async function extractSubject(input: { file?: File; text?: string }): Promise<Subject> {
  const form = new FormData()
  if (input.file) form.append('file', input.file)
  else if (input.text) form.append('text', input.text)
  const res = await fetch(`${API_BASE}/api/extract`, { method: 'POST', body: form })
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  return res.json()
}

export type ValueResult =
  | { ok: true; valuation: Valuation }
  | { ok: false; incomplete: IncompleteSubject }

/** POST /api/value, 200 Valuation, or the gate's 422 incomplete_subject (returned, not thrown). */
export async function valueSubject(subject: Subject): Promise<ValueResult> {
  const res = await fetch(`${API_BASE}/api/value`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subject),
  })
  if (res.status === 422) {
    const body = await res.json()
    if (body?.error === 'incomplete_subject') {
      return { ok: false, incomplete: body as IncompleteSubject }
    }
    throw new ApiError(typeof body?.detail === 'string' ? body.detail : 'Invalid subject', 422)
  }
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  return { ok: true, valuation: await res.json() }
}

/** POST /api/rationale, the slow LLM prose for an already-valued subject (progressive render). */
export async function fetchRationale(subject: Subject): Promise<Rationale> {
  const res = await fetch(`${API_BASE}/api/rationale`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subject),
  })
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status)
  return res.json()
}

export { API_BASE }
