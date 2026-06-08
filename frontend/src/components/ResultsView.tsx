import { useMemo, type ReactNode } from 'react'

import type { Subject, Valuation } from '../api'
import {
  factorLabel,
  formatCurrency,
  formatDuration,
  formatFactor,
  subjectSummary,
} from '../lib/format'
import { ConfidenceBadge, ModeBadge } from './Badges'
import CompMap from './CompMap'
import CompTable from './CompTable'
import RationalePanel from './RationalePanel'

function Panel({ title, meta, children }: { title: string; meta?: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-neutral-200 bg-white">
      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-2.5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">{title}</h3>
        {meta && <span className="text-[11px] text-neutral-400">{meta}</span>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

function ValueHero({ valuation }: { valuation: Valuation }) {
  return (
    <section className="rounded-md border border-neutral-200 bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 px-5 py-4">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
            Defensible value
          </div>
          <div className="mt-1 font-mono text-4xl font-semibold tracking-tight text-accent">
            {formatCurrency(valuation.conservative_value)}
          </div>
          <div className="mt-1.5 text-xs text-neutral-500">
            Lender-facing floor. Point estimate{' '}
            <span className="font-mono text-neutral-700">
              {formatCurrency(valuation.point_estimate)}
            </span>
            , range{' '}
            <span className="font-mono text-neutral-700">
              {formatCurrency(valuation.range_low)} to {formatCurrency(valuation.range_high)}
            </span>
            .
          </div>
        </div>
        <div className="text-right">
          <div className="flex items-center justify-end gap-1.5 text-xs text-neutral-500">
            Confidence <ConfidenceBadge confidence={valuation.confidence} />
          </div>
          <div className="mt-1.5 flex items-center justify-end gap-2 text-xs text-neutral-400">
            <span>
              Valued in{' '}
              <span className="font-mono text-neutral-600">
                {formatDuration(valuation.elapsed_ms)}
              </span>
            </span>
            <ModeBadge mode={valuation.mode} />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 divide-x divide-neutral-100 border-t border-neutral-200 sm:grid-cols-3 lg:grid-cols-5">
        {Object.entries(valuation.confidence_factors).map(([key, value]) => (
          <div key={key} className="px-4 py-2.5">
            <div className="text-[11px] uppercase tracking-wide text-neutral-400">
              {factorLabel(key)}
            </div>
            <div className="mt-0.5 font-mono text-sm font-medium text-neutral-900">
              {formatFactor(key, value)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function InsufficientHero({ valuation }: { valuation: Valuation }) {
  return (
    <section className="rounded-md border border-neutral-200 bg-white px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
            No defensible value
          </div>
          <div className="mt-1 text-xl font-semibold text-neutral-900">
            Insufficient comparable sales
          </div>
          <div className="mt-1 max-w-xl text-xs text-neutral-500">
            Too few comps remained comparable after exclusions. The engine declines rather than
            valuing off one or two weak comps. See the rationale and table below.
          </div>
        </div>
        <div className="text-right text-xs text-neutral-400">
          <div className="flex items-center justify-end gap-1.5 text-neutral-500">
            Confidence <ConfidenceBadge confidence={valuation.confidence} />
          </div>
          <div className="mt-1.5">
            Valued in{' '}
            <span className="font-mono text-neutral-600">{formatDuration(valuation.elapsed_ms)}</span>
          </div>
        </div>
      </div>
    </section>
  )
}

type Props = {
  valuation: Valuation
  subject: Subject
  onBack: () => void
  rationaleLoading?: boolean
}

export default function ResultsView({ valuation, subject, onBack, rationaleLoading }: Props) {
  const insufficient = valuation.point_estimate === 0
  // Stable comp numbering (similarity desc, the table's default order) shared by the table's
  // "#" column and the exclusion-reason list, so each reason maps to a visible row.
  const rows = useMemo(
    () =>
      [...valuation.comps]
        .sort((a, b) => b.similarity - a.similarity)
        .map((sc, i) => ({ sc, n: i + 1 })),
    [valuation.comps],
  )
  const included = rows.filter((r) => r.sc.status === 'included')
  const excluded = rows.filter((r) => r.sc.status !== 'included')

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
      <button
        onClick={onBack}
        className="text-xs font-medium text-neutral-500 transition hover:text-neutral-900"
      >
        ← New valuation
      </button>

      {insufficient ? <InsufficientHero valuation={valuation} /> : <ValueHero valuation={valuation} />}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-3">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Subject
            </h3>
            <p className="mt-1 text-sm text-neutral-700">{subjectSummary(subject)}</p>
          </div>
          <Panel
            title="Comparable sales"
            meta={`${valuation.comps.length} found, ${included.length} included, ${excluded.length} excluded`}
          >
            <CompMap valuation={valuation} subject={subject} />
            <div className="mt-4">
              <CompTable rows={rows} />
            </div>
            {excluded.length > 0 && (
              <ul className="mt-3 space-y-1 text-[11px] text-neutral-500">
                {excluded.map(({ sc, n }) => (
                  <li key={n}>
                    <span className="font-medium text-neutral-600">Row {n}:</span> {sc.flag_reason}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
        <div>
          <RationalePanel valuation={valuation} loading={rationaleLoading} />
        </div>
      </div>
    </div>
  )
}
