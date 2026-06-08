import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Comp, ScoredComp, Subject, Valuation } from '../../api'
import ResultsView from '../ResultsView'

// The Leaflet map can't render in jsdom; stub it (the table + headline are the point here).
vi.mock('../CompMap', () => ({ default: () => <div data-testid="comp-map" /> }))

const comp = (over: Partial<Comp> = {}): Comp => ({
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
  sale_price: 650000,
  sale_date: '2015-01-01',
  price_per_sqft: 361,
  distance_km: 1.2,
  ...over,
})

const scored = (over: Partial<ScoredComp> = {}): ScoredComp => ({
  comp: comp(),
  similarity: 0.9,
  subscores: {},
  adjustments: {},
  adjusted_price: 655000,
  flagged: false,
  flag_reason: null,
  status: 'included',
  ...over,
})

const subject: Subject = { ...comp(), as_of_date: '2015-05-01' } as unknown as Subject

const valuation: Valuation = {
  conservative_value: 591104,
  point_estimate: 654849,
  range_low: 612000,
  range_high: 701000,
  confidence: 'Medium',
  confidence_factors: {
    comp_count: 20,
    mean_distance_km: 1.2,
    dispersion: 0.1,
    median_age_days: 90,
  },
  comps: [
    scored(),
    scored({
      comp: comp({ sale_price: 900000 }),
      similarity: 0.5,
      adjusted_price: 905000,
      flagged: true,
      flag_reason: '$/sqft of $500 is 2.1x the neighborhood median',
      status: 'outlier',
    }),
  ],
  rationale: 'Conservative value supported by nearby comps.\n\nOne comp flagged as an outlier.',
  mode: 'agent',
  elapsed_ms: 142,
}

describe('ResultsView, headline', () => {
  it('shows the conservative value as the labeled headline, with confidence and timing', () => {
    render(<ResultsView valuation={valuation} subject={subject} onBack={() => {}} />)

    expect(screen.getByText('Defensible value')).toBeInTheDocument()
    expect(screen.getByText('$591,104')).toBeInTheDocument() // the conservative headline
    expect(screen.getByText('Medium')).toBeInTheDocument() // confidence badge
    expect(screen.getByText(/142 ms/)).toBeInTheDocument()
    expect(screen.getByTestId('comp-map')).toBeInTheDocument()
    // the flagged comp's $/sqft reason is surfaced
    expect(screen.getByText(/2\.1x the neighborhood median/)).toBeInTheDocument()
  })
})
