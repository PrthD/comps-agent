import { useEffect, useState } from 'react'

import { getSamples, type Sample } from '../api'

export default function SampleMenu({ onPick }: { onPick: (sample: Sample) => void }) {
  const [samples, setSamples] = useState<Sample[]>([])

  useEffect(() => {
    getSamples()
      .then(setSamples)
      .catch(() => setSamples([]))
  }, [])

  if (samples.length === 0) return null

  return (
    <div className="border-b border-neutral-200 bg-neutral-50 px-4 py-3">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">
        Load a sample
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {samples.map((sample) => (
          <button
            key={sample.id}
            onClick={() => onPick(sample)}
            className="rounded border border-neutral-200 bg-white p-2.5 text-left transition hover:border-neutral-400"
          >
            <div className="text-xs font-semibold text-neutral-900">{sample.label}</div>
            <div className="mt-0.5 text-[11px] leading-snug text-neutral-500">
              {sample.description}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
