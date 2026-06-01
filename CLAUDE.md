# CLAUDE.md

Comps valuation agent for the KV Capital AI Engineer hackathon.
**Full spec: `docs/BUILD_BRIEF.md` — that file is the source of truth. This is the short version.**

## Non-negotiables (never violate)

- **Trust boundary.** The LLM normalizes input, judges which comps to trust, decides whether
  confidence is warranted, and writes the rationale. It NEVER computes a number. All arithmetic
  (distance, scoring, adjustments, estimate, range, confidence) lives in pure, tested functions
  under `backend/app/core/`.
- **≤2 LLM calls per valuation** (extraction + reasoning) plus at most 1 bounded re-query. Speed is
  the customer's #1 pain; the deterministic core does retrieval/scoring/adjustment without round-trips.
- **Leakage rule.** When valuing a subject, only use comps sold *strictly before* its as-of date, and
  never the subject itself. Enforced in retrieval and asserted in tests.
- **Headline output is the conservative defensible value** + range + confidence — not the point
  estimate. This is a lender, not a brokerage.
- **$/sqft outlier flagging is a first-class feature** (the customer explicitly asked for it): flag and
  exclude comps outside a robust $/sqft band, with a stated reason, surfaced in the UI.
- **Never overclaim accuracy.** Off-market AVMs sit ~7% median error; an 8–15% backtest MdAPE is honest
  and acceptable. Always report limitations.
- **Never commit secrets.** `GEMINI_API_KEY` via env only.

## Architecture (one breath)

Subject (PDF / image / pasted text / form) → Gemini agent (judgment + prose) → deterministic core
(retrieve → score → flag outliers → hedonic adjust → estimate / conservative / confidence) over an
in-memory King County comps store → conservative value + range + confidence + comp table + flags +
rationale. Stateless. React on Vercel + FastAPI (Docker) on Render.

## Conventions

- Python: `uv` for deps, `ruff` for lint + format, pydantic v2 at every boundary, full type hints.
  Core functions are pure and deterministic (seed everything).
- Config-driven: weights, radii, time windows, thresholds, and model IDs live in
  `backend/app/config.py` — never hardcode them inside logic.
- Tests are lean and on the core: scoring monotonicity, haversine, leakage guard, outlier detection,
  estimate invariants (estimate ∈ [min,max]; conservative ≤ point; more dispersion → lower confidence),
  and one backtest regression test. Do not test LLM prose.
- Frontend: Vite + React + TS + Tailwind + react-leaflet. Map = Leaflet / OpenStreetMap (no key).

## Workflow

- Build phase by phase, P0 → P7 per `docs/BUILD_BRIEF.md` §15. Commit at the end of each phase.
- Build **P1 (deterministic core) and P2 (backtest) before the Gemini layer (P3)** — no agent work
  until the core has a locked accuracy number.
- After the P0 scaffold, stop and ask for review before continuing.

## Out of scope for v1 (do NOT build — these are "what's next")

Commercial borrowers · multi-market · chat UI · persistence / saved history ·
architectural-drawing parsing · any custom ML AVM model.
