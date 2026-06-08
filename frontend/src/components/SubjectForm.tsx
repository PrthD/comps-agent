import type { Subject } from '../api'
import { fieldLabel } from '../lib/format'
import MapPicker from './MapPicker'

type Props = {
  subject: Subject
  onChange: (subject: Subject) => void
  onValue: () => void
  valuing: boolean
  missingFields: string[]
  error: string | null
  extracted: boolean
}

const NUMERIC_FIELDS: { key: keyof Subject; step?: string; min?: number; placeholder?: string }[] = [
  { key: 'beds', step: '1', min: 0, placeholder: '3' },
  { key: 'baths', step: '0.25', min: 0, placeholder: '2' },
  { key: 'sqft_living', step: '1', min: 1, placeholder: '1800' },
  { key: 'sqft_lot', step: '1', min: 1, placeholder: '5000' },
  { key: 'year_built', step: '1', placeholder: '1960' },
  { key: 'grade', step: '1', placeholder: '7' },
  { key: 'condition', step: '1', min: 1, placeholder: '3' },
]

const PROPERTY_TYPES = ['detached', 'townhouse', 'condo']

function ConfidenceChip({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const tone =
    value >= 0.8
      ? 'text-emerald-700'
      : value >= 0.4
        ? 'text-amber-700'
        : 'text-red-700'
  return <span className={`font-mono text-[10px] ${tone}`}>{pct}%</span>
}

export default function SubjectForm({
  subject,
  onChange,
  onValue,
  valuing,
  missingFields,
  error,
  extracted,
}: Props) {
  const missing = new Set(missingFields)
  const review = new Set(subject.needs_review ?? [])

  function stateOf(key: string): 'missing' | 'review' | 'ok' {
    if (missing.has(key)) return 'missing'
    if (review.has(key)) return 'review'
    return 'ok'
  }

  function borderFor(key: string): string {
    const s = stateOf(key)
    if (s === 'missing') return 'border-red-400 focus:border-red-500 focus:ring-red-100'
    if (s === 'review') return 'border-amber-400 focus:border-amber-500 focus:ring-amber-100'
    return 'border-neutral-300 focus:border-accent focus:ring-neutral-200'
  }

  // Commit a field change. A field the user just set or confirmed is no longer pending review, so
  // drop it from needs_review: the backend gate treats needs_review membership as "unresolved", and
  // leaving e.g. 'lat'/'lng' there after the user picks a location keeps the gate firing even though
  // the coordinate is set (the pin and the gate would otherwise be out of sync).
  function commit(patch: Partial<Subject>) {
    const touched = new Set(Object.keys(patch))
    const nr = subject.needs_review ?? null
    const needs_review = nr ? nr.filter((f) => !touched.has(f)) : nr
    onChange({ ...subject, ...patch, needs_review })
  }

  function setField<K extends keyof Subject>(key: K, value: Subject[K]) {
    commit({ [key]: value } as Partial<Subject>)
  }

  function setNumber(key: keyof Subject, raw: string) {
    setField(key, (raw === '' ? null : Number(raw)) as Subject[keyof Subject])
  }

  function FieldLabel({ field }: { field: string }) {
    const s = stateOf(field)
    const conf = subject.field_confidence?.[field]
    return (
      <span className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-neutral-500">
        {fieldLabel(field)}
        {s === 'missing' && (
          <span className="rounded-sm bg-red-50 px-1 text-[9px] font-semibold text-red-700">
            required
          </span>
        )}
        {s === 'review' && (
          <span className="rounded-sm bg-amber-50 px-1 text-[9px] font-semibold text-amber-700">
            review
          </span>
        )}
        {conf !== undefined && <ConfidenceChip value={conf} />}
      </span>
    )
  }

  const inputClass = (key: string) =>
    `w-full rounded border bg-white px-2.5 py-1.5 text-sm text-neutral-900 outline-none focus:ring-2 ${borderFor(key)}`

  return (
    <div className="space-y-4">
      {extracted && (
        <div className="rounded border border-neutral-300 bg-neutral-50 px-3 py-2 text-xs text-neutral-700">
          Extracted from the document. Review highlighted fields, set the location, then value.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1">
          <FieldLabel field="property_type" />
          <select
            value={subject.property_type}
            onChange={(e) => setField('property_type', e.target.value)}
            className={inputClass('property_type')}
          >
            {PROPERTY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <label className="block space-y-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
            As-of date
          </span>
          <input
            type="date"
            value={subject.as_of_date}
            onChange={(e) => setField('as_of_date', e.target.value)}
            className={inputClass('as_of_date')}
          />
        </label>

        {NUMERIC_FIELDS.map(({ key, step, min, placeholder }) => (
          <label key={key} className="block space-y-1">
            <FieldLabel field={key} />
            <input
              type="number"
              inputMode="decimal"
              step={step}
              min={min}
              placeholder={placeholder}
              value={subject[key] === null || subject[key] === undefined ? '' : String(subject[key])}
              onChange={(e) => setNumber(key, e.target.value)}
              className={inputClass(key)}
            />
          </label>
        ))}
      </div>

      <p className="text-[11px] text-neutral-400">
        Dataset covers 2014-05 to 2015-05. As-of date defaults to 2015-05-01 (a current date returns
        no comps).
      </p>

      <div className="space-y-1">
        <span className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
          Location {(missing.has('lat') || missing.has('lng')) && (
            <span className="rounded-sm bg-red-50 px-1 text-[9px] font-semibold text-red-700">
              required
            </span>
          )}
        </span>
        <MapPicker
          lat={subject.lat}
          lng={subject.lng}
          onPick={(lat, lng) => commit({ lat, lng })}
          highlight={missing.has('lat') || missing.has('lng')}
        />
      </div>

      {missingFields.length > 0 && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <span className="font-semibold">Required fields missing:</span>{' '}
          {missingFields.map(fieldLabel).join(', ')}.
        </div>
      )}

      {error && (
        <div className="rounded border border-neutral-300 bg-neutral-50 px-3 py-2 text-xs text-neutral-700">
          {error}
        </div>
      )}

      <button
        onClick={onValue}
        disabled={valuing || missingFields.length > 0}
        className="w-full rounded bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
      >
        {valuing ? 'Valuing' : 'Value property'}
      </button>
    </div>
  )
}
