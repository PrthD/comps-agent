import { describe, expect, it } from 'vitest'

import type { Subject } from '../../api'
import { formatFactor, formatPercent, subjectSummary } from '../format'

describe('formatPercent, half-up, matches the backend rationale rounding', () => {
  it('rounds half up at exact ties so the stat row can never disagree with the prose', () => {
    // x.5 percentages that are EXACTLY representable as doubles (the only place rounding modes can
    // diverge). Half-up gives 13/38/63; Python banker's round would give 12/38/62, so the backend
    // formats with floor(x+0.5) too. These must agree or the prose could say "12%" vs stat "13%".
    expect(formatPercent(0.125)).toBe('13%') // 12.5 -> 13
    expect(formatPercent(0.375)).toBe('38%') // 37.5 -> 38
    expect(formatPercent(0.625)).toBe('63%') // 62.5 -> 63
    // Ordinary (non-tie) values:
    expect(formatPercent(0.1822)).toBe('18%')
    expect(formatPercent(0.0601753)).toBe('6%')
  })

  it('drives the dispersion and mean_adjustment stat-row cells', () => {
    expect(formatFactor('dispersion', 0.125)).toBe('13%')
    expect(formatFactor('mean_adjustment', 0.125)).toBe('13%')
  })
})

describe('subjectSummary, tight descriptor, nulls omitted', () => {
  const base: Subject = {
    property_type: 'detached',
    beds: 3,
    baths: 2,
    sqft_living: 1800,
    sqft_lot: 4000,
    year_built: 1960,
    condition: 3,
    grade: 7,
    lat: 47.6,
    lng: -122.3,
    as_of_date: '2015-05-01',
    field_confidence: null,
    needs_review: null,
  }

  it('renders all present fields', () => {
    expect(subjectSummary(base)).toBe(
      'Detached · 3 bd / 2 ba · 1,800 sqft · built 1960 · grade 7 · condition 3',
    )
  })

  it('omits null fields', () => {
    expect(subjectSummary({ ...base, year_built: null, grade: null, condition: null })).toBe(
      'Detached · 3 bd / 2 ba · 1,800 sqft',
    )
  })
})
