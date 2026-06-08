import type { Confidence, Mode } from '../api'

const CONF_STYLES: Record<Confidence, string> = {
  High: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  Medium: 'bg-amber-50 text-amber-700 ring-amber-200',
  Low: 'bg-red-50 text-red-700 ring-red-100',
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return (
    <span
      className={`inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${CONF_STYLES[confidence]}`}
    >
      {confidence}
    </span>
  )
}

export function ModeBadge({ mode }: { mode: Mode }) {
  const agent = mode === 'agent'
  return (
    <span
      title={
        agent
          ? 'Rationale written by AI over the computed figures'
          : 'Deterministic templated rationale (AI unavailable)'
      }
      className="inline-flex items-center gap-1 rounded-sm bg-neutral-100 px-1.5 py-0.5 text-[11px] font-medium text-neutral-600 ring-1 ring-inset ring-neutral-200"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${agent ? 'bg-accent' : 'bg-neutral-400'}`} />
      {agent ? 'AI analysis' : 'Template'}
    </span>
  )
}
