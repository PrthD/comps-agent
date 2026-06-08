// Static product identity only. Cold-start status lives in WarmingScreen (shown until the backend
// is live, then gone); per-result provenance lives in the Agent/Template mode badge. No global
// "Ready" / "LLM on" / comps-count indicators here, those are dev-facing.
export default function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-neutral-200 bg-white">
      <div className="mx-auto flex h-12 max-w-6xl items-center gap-2.5 px-4">
        <div className="flex h-6 w-6 items-center justify-center rounded bg-accent text-[11px] font-semibold text-white">
          KV
        </div>
        <span className="text-sm font-semibold text-neutral-900">Comps Valuation</span>
        <span className="hidden text-xs text-neutral-500 sm:inline">Lender underwriting tool</span>
      </div>
    </header>
  )
}
