import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Valuation } from '../../api'
import RationalePanel from '../RationalePanel'

const valuation = (over: Partial<Valuation> = {}): Valuation => ({
  conservative_value: 500000,
  point_estimate: 550000,
  range_low: 520000,
  range_high: 580000,
  confidence: 'Medium',
  confidence_factors: {},
  comps: [],
  rationale: 'The conservative value is defensible against the nearby comps.',
  mode: 'agent',
  elapsed_ms: 120,
  ...over,
})

describe('RationalePanel — progressive render', () => {
  it('shows a loading state while reasoning, then drops in the prose', () => {
    // Phase 1: value is on screen, rationale still generating (no prose yet).
    const { rerender } = render(<RationalePanel valuation={valuation({ rationale: '' })} loading />)
    expect(screen.getByText(/Generating analysis/i)).toBeInTheDocument()

    // Phase 2: the prose arrives and the loading state is gone.
    rerender(<RationalePanel valuation={valuation()} loading={false} />)
    expect(screen.queryByText(/Generating analysis/i)).not.toBeInTheDocument()
    expect(screen.getByText(/defensible against the nearby comps/)).toBeInTheDocument()
  })
})
