import type { Valuation } from '../api'
import { ModeBadge } from './Badges'

type Props = { valuation: Valuation; loading?: boolean }

export default function RationalePanel({ valuation, loading = false }: Props) {
  const paragraphs = valuation.rationale.split(/\n{2,}/).filter((p) => p.trim().length > 0)

  return (
    <section className="rounded-md border border-neutral-200 bg-white">
      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-2.5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">Rationale</h3>
        {/* While the analysis is still generating, the mode is not yet settled; hold the badge. */}
        {!loading && <ModeBadge mode={valuation.mode} />}
      </div>
      <div className="space-y-2 px-4 py-3 text-sm leading-relaxed text-neutral-700">
        {loading ? (
          <div className="flex items-center gap-2 text-neutral-400">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-neutral-300 border-t-accent" />
            <span>Generating analysis...</span>
          </div>
        ) : paragraphs.length > 0 ? (
          paragraphs.map((p, i) => <p key={i}>{p}</p>)
        ) : (
          <p className="text-neutral-400">No rationale provided.</p>
        )}
      </div>
      <p className="border-t border-neutral-100 px-4 py-2.5 text-[11px] leading-relaxed text-neutral-400">
        Figures are computed by the deterministic engine and are the source of truth. This narrative
        is explanatory commentary, never the source of a displayed number.
      </p>
    </section>
  )
}
