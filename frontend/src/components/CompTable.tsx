import { useMemo, useState } from 'react'

import type { ScoredComp } from '../api'
import { STATUS_LABEL, STATUS_PILL, formatCurrency, formatKm } from '../lib/format'

type SortKey = 'sale_price' | 'adjusted_price' | 'distance_km' | 'sqft_living' | 'similarity'

// Each row carries a stable comp number (`n`) assigned by the parent, so re-sorting the table never
// breaks the link between a flagged row and its exclusion reason listed below the table.
type Row = { sc: ScoredComp; n: number }

const ACCESSOR: Record<SortKey, (sc: ScoredComp) => number> = {
  sale_price: (sc) => sc.comp.sale_price,
  adjusted_price: (sc) => sc.adjusted_price,
  distance_km: (sc) => sc.comp.distance_km,
  sqft_living: (sc) => sc.comp.sqft_living,
  similarity: (sc) => sc.similarity,
}

export default function CompTable({ rows }: { rows: Row[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('similarity')
  const [dir, setDir] = useState<'asc' | 'desc'>('desc')

  const sorted = useMemo(() => {
    const copy = [...rows]
    copy.sort(
      (a, b) => (ACCESSOR[sortKey](a.sc) - ACCESSOR[sortKey](b.sc)) * (dir === 'asc' ? 1 : -1),
    )
    return copy
  }, [rows, sortKey, dir])

  function toggle(key: SortKey) {
    if (key === sortKey) {
      setDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setDir('desc')
    }
  }

  const SortHeader = ({ col, label, title }: { col: SortKey; label: string; title?: string }) => (
    <th
      onClick={() => toggle(col)}
      title={title}
      className="cursor-pointer select-none px-3 py-1.5 text-right font-medium hover:text-neutral-900"
    >
      {label}
      <span className="text-neutral-400">{sortKey === col ? (dir === 'asc' ? ' ↑' : ' ↓') : ''}</span>
    </th>
  )

  // Weights mirror the backend SCORING_WEIGHTS; surfaced on hover so the Sim score is auditable.
  const SIM_TITLE =
    'Weighted similarity: distance 30%, living area 20%, recency 15%, ' +
    'grade/condition 15%, age 10%, bed/bath 10%'

  return (
    <div className="overflow-x-auto rounded border border-neutral-200">
      <table className="min-w-full text-xs">
        <thead className="border-b border-neutral-200 bg-neutral-50 text-[11px] uppercase tracking-wide text-neutral-500">
          <tr>
            <th className="px-3 py-1.5 text-left font-medium">#</th>
            <SortHeader col="sale_price" label="Sale" />
            <SortHeader col="adjusted_price" label="Adjusted" />
            <SortHeader col="distance_km" label="Dist" />
            <SortHeader col="sqft_living" label="Sqft" />
            <th className="px-3 py-1.5 text-right font-medium">Bd/Ba</th>
            <SortHeader col="similarity" label="Sim" title={SIM_TITLE} />
            <th className="px-3 py-1.5 text-left font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {sorted.map(({ sc, n }) => (
            <tr key={n} className="hover:bg-neutral-50">
              <td className="px-3 py-1.5 text-neutral-400">{n}</td>
              <td className="px-3 py-1.5 text-right font-mono text-neutral-600">
                {formatCurrency(sc.comp.sale_price)}
              </td>
              <td className="px-3 py-1.5 text-right font-mono font-medium text-neutral-900">
                {formatCurrency(sc.adjusted_price)}
              </td>
              <td className="px-3 py-1.5 text-right font-mono text-neutral-600">
                {formatKm(sc.comp.distance_km)}
              </td>
              <td className="px-3 py-1.5 text-right font-mono text-neutral-600">
                {sc.comp.sqft_living.toLocaleString()}
              </td>
              <td className="px-3 py-1.5 text-right font-mono text-neutral-600">
                {sc.comp.beds}/{sc.comp.baths}
              </td>
              <td className="px-3 py-1.5">
                <div className="flex items-center justify-end gap-2">
                  <span className="h-1 w-8 overflow-hidden rounded-sm bg-neutral-200">
                    <span
                      className="block h-full bg-accent"
                      style={{ width: `${Math.round(sc.similarity * 100)}%` }}
                    />
                  </span>
                  <span className="font-mono text-neutral-700">
                    {(sc.similarity * 100).toFixed(0)}%
                  </span>
                </div>
              </td>
              <td className="px-3 py-1.5">
                <span
                  title={sc.flag_reason ?? ''}
                  className={`inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset ${STATUS_PILL[sc.status]}`}
                >
                  {STATUS_LABEL[sc.status]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
