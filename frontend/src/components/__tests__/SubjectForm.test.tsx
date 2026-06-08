import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Subject } from '../../api'
import SubjectForm from '../SubjectForm'

// Leaflet needs real layout; stub the map. The stub exposes a button that fires the CURRENT onPick
// prop, so a "map click" exercises the same commit path the real MapPicker uses.
vi.mock('../MapPicker', () => ({
  default: ({ onPick }: { onPick: (lat: number, lng: number) => void }) => (
    <button data-testid="map-click" onClick={() => onPick(47.61, -122.33)}>
      map
    </button>
  ),
}))

const baseSubject: Subject = {
  property_type: 'detached',
  beds: null,
  baths: null,
  sqft_living: null,
  sqft_lot: null,
  year_built: null,
  condition: null,
  grade: null,
  lat: null,
  lng: null,
  as_of_date: '2015-05-01',
  field_confidence: null,
  needs_review: null,
}

describe('SubjectForm — completeness gate', () => {
  it('renders the gate banner and marks required fields when fields are missing', () => {
    render(
      <SubjectForm
        subject={baseSubject}
        onChange={() => {}}
        onValue={() => {}}
        valuing={false}
        missingFields={['sqft_living', 'lat', 'lng']}
        error={null}
        extracted={false}
      />,
    )

    // The gate message is intentional, not a generic error.
    expect(screen.getByText(/Required fields missing/i)).toBeInTheDocument()
    // The human labels for missing fields appear (as a field label and/or in the banner list).
    expect(screen.getAllByText(/Living area \(sqft\)/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Latitude/)).toBeInTheDocument()
    // Missing fields carry a "required" tag.
    expect(screen.getAllByText('required').length).toBeGreaterThan(0)
  })
})

describe('SubjectForm — map click on the extraction path', () => {
  // Mirror App's updateSubject: any field change clears the stale gate result.
  function Harness({ onCommit }: { onCommit: (s: Subject) => void }) {
    const [subject, setSubject] = useState<Subject>({
      ...baseSubject,
      beds: 3,
      baths: 2,
      sqft_living: 1800,
      // Extraction populated the fields but flags lat/lng for the user to set on the map.
      field_confidence: { lat: 0, lng: 0 },
      needs_review: ['lat', 'lng'],
    })
    const [missing, setMissing] = useState<string[]>(['lat', 'lng'])
    return (
      <SubjectForm
        subject={subject}
        onChange={(next) => {
          onCommit(next)
          setSubject(next)
          setMissing([]) // App clears the prior 422 result on any subject change
        }}
        onValue={() => {}}
        valuing={false}
        missingFields={missing}
        error={null}
        extracted
      />
    )
  }

  it('dropping a pin clears the gate, enables Value, and resolves lat/lng review', () => {
    let committed: Subject | null = null
    render(<Harness onCommit={(s) => (committed = s)} />)

    // Before the pin: the gate banner shows and Value is blocked.
    expect(screen.getByText(/Required fields missing/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Value property/i })).toBeDisabled()

    fireEvent.click(screen.getByTestId('map-click'))

    // The banner is gone and Value is enabled.
    expect(screen.queryByText(/Required fields missing/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Value property/i })).toBeEnabled()

    // The committed subject is what the backend gate reads: coords set AND removed from
    // needs_review (membership there is what kept the gate firing).
    expect(committed).not.toBeNull()
    expect(committed!.lat).toBeCloseTo(47.61)
    expect(committed!.lng).toBeCloseTo(-122.33)
    expect(committed!.needs_review).not.toContain('lat')
    expect(committed!.needs_review).not.toContain('lng')
  })
})
