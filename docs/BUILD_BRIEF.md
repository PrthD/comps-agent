# KV Capital AI Engineer Hackathon — Build Brief

A spec for implementation in Claude Code. Not the code itself — the contracts, decisions, and
sequence Claude Code should build against.

---

## 0. Context & what wins

**Challenge:** given a subject residential property, build an AI agent that retrieves and ranks
comparable recent sales, produces a _conservative, defensible_ valuation, and explains its reasoning.

**Customer reality (from the Sam call — these are hard requirements, not flavor):**

- Underwriters rely on **10–20 plausible comps** per deal. Trust = similarity in location, size, age, recency.
- They need a **conservative, defensible value** they can justify with solid comps — **not a single point estimate.**
- Intake is **messy: building plans and documents**, not clean structured data. They extract details by hand.
- The #1 thing they want auto-flagged: **a comp significantly outside the typical price-per-sqft range.**
- **Speed is the bigger pain** than auditability (but the output must still be defensible).

**Judged on (Notion rubric):** Domain Understanding · Judgment (focused beats general) · Agent quality
(reliability, latency, experience) · Code (clarity, structure, tests where they earn their keep) · Pragmatism (what you cut).

**Positioning:** an explainable comps agent that mirrors the appraiser's sales-comparison workflow, built
for a _lender_ who needs a defensible, conservative, auditable number — what black-box AVMs (Zestimate, etc.)
don't give. We are NOT trying to beat Zillow on accuracy; we're automating the slow manual comp pull with
reasoning an underwriter can stand behind.

---

## 1. Locked decisions

| Decision            | Choice                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Deploy topology     | **Split**: React → Vercel, FastAPI → Render (Docker)                                                                  |
| Persistence         | **Stateless** — no DB; comps bundled read-only in the image                                                           |
| Document intake     | **Full**: PDF/image upload + paste text + structured form                                                             |
| Dataset             | King County (Kaggle `harlfoxem`), CC0, ~21,613 real sales, real lat/long + dates                                      |
| LLM                 | Gemini free tier — **Flash** (2.5 Flash / Gemini 3 Flash) for agent reasoning; **Flash-Lite** for document extraction |
| Map                 | Leaflet + OpenStreetMap (free, no key)                                                                                |
| LLM calls/valuation | **≤2** (extraction + reasoning) + 1 bounded re-query max — keeps latency low and stays inside free RPM                |
| Fallback            | Deterministic mode runs the full valuation with **no API key** / when rate-limited                                    |

**Non-goals for v1 (cut deliberately — document in README under "what's next"):** commercial borrowers,
multi-market, chat interface, saved history/persistence, full architectural-drawing parsing, a custom ML AVM.

---

## 2. Architecture

```
Subject (PDF / image / pasted text / form)
        │
        ▼
[Agent orchestrator — Gemini]      ← judgment, adaptation, explanation (NEVER does arithmetic)
        │  calls tools / reads results
        ▼
[Deterministic core] ───────────── all computation, pure, tested, reproducible
   ├─ extract_subject   (Gemini Flash-Lite, multimodal → structured Subject + per-field confidence)
   ├─ search_comps      (filters + haversine → 10–20 candidates)
   ├─ score_comps       (weighted similarity → ranked)
   ├─ flag_outliers     ($/sqft robust band → exclude/flag with reason)   ← Sam's #1 ask
   └─ estimate_value    (hedonic adjustment grid + time adj → point, range, conservative anchor, confidence)
        │
        ▼
[Comps store] — King County, 21.6k rows, in-memory (DuckDB/SQLite from bundled parquet)
        │
        ▼
Output: conservative value · range · confidence · comp table · flags · plain-English rationale · timing
```

**Trust boundary (the thesis, state it loudly in the README):** the LLM normalizes messy input, judges which
comps to trust, decides whether confidence is warranted, can request _one_ widen if comps are thin, and writes
the rationale. Every number it reports came from a deterministic tool. This is what makes it testable and
auditable, and it directly answers the JD's "know when to trust and when to challenge AI."

**Why ≤2 LLM calls, not a multi-step ReAct loop:** Sam said speed is the pain; free-tier RPM is 10–30. The
deterministic core handles retrieval/scoring/adjustment/flagging without round-tripping the model. Choosing the
leaner design IS the judgment being tested — say so in the README rather than apologizing for it.

---

## 3. Repo structure (monorepo)

```
kv-comps-agent/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 # FastAPI app, routes, CORS
│  │  ├─ schemas.py              # pydantic models (§5)
│  │  ├─ config.py               # weights, radii, thresholds, model IDs (§9)
│  │  ├─ core/
│  │  │  ├─ data.py              # load bundled comps into in-memory store
│  │  │  ├─ retrieve.py          # search_comps + haversine
│  │  │  ├─ score.py             # weighted similarity
│  │  │  ├─ outliers.py          # $/sqft robust band
│  │  │  ├─ hedonic.py           # regression coeffs (fit once at boot)
│  │  │  └─ estimate.py          # adjustment grid, range, conservative anchor, confidence
│  │  ├─ agent/
│  │  │  ├─ extract.py           # Gemini Flash-Lite multimodal → Subject
│  │  │  ├─ reason.py            # Gemini Flash → judgment + rationale
│  │  │  └─ orchestrator.py      # bounded loop, fallback to deterministic mode
│  │  └─ eval/
│  │     └─ backtest.py          # leave-one-out, metrics, report
│  ├─ data/kc_sales.parquet      # bundled dataset (CC0)
│  ├─ tests/                     # pytest (§7)
│  ├─ scripts/prepare_data.py    # download + clean → parquet
│  ├─ Dockerfile
│  ├─ pyproject.toml             # uv-managed
│  └─ .env.example               # GEMINI_API_KEY, ALLOWED_ORIGINS
├─ frontend/                     # Vite + React + TS + Tailwind + react-leaflet
│  └─ ...                        # (§8)
├─ README.md                     # submission README (§10)
└─ docs/                         # architecture.mmd, eval_report.md, sample traces
```

---

## 4. Data

- Source: King County house sales, Kaggle `harlfoxem/housesalesprediction`, **CC0 public domain** (no license
  entanglement — matters given the IP terms). ~21,613 sales, May 2014–May 2015.
- Columns used: `date, price, bedrooms, bathrooms, sqft_living, sqft_lot, floors, condition, grade, yr_built,
zipcode, lat, long`.
- `prepare_data.py`: download → drop dupes/nulls → derive `price_per_sqft`, parse `date` → write parquet.
- Bundle the parquet in the image. Load read-only into DuckDB (or pandas) at startup; 21k rows is trivial.
- **Frame honestly in README:** King County is a stand-in for MLS sold-comp structure; pipeline is
  geography-agnostic; KV would swap in Alberta MLS / assessment / Teranet data.
- Add ~5 **synthetic adversarial subjects** (acreage, no-comps new build, $/sqft outlier neighbor) purely for
  edge-case demos. Don't synthesize the whole dataset — real geo/dates buy credibility and a real backtest.
- **Leakage rule (critical, repeat in README):** when valuing any subject, only use comps sold _strictly
  before_ its as-of date, and never the subject itself.

---

## 5. Data contracts (pydantic v2)

```
Subject:
  property_type: str            # detached/townhouse/condo (map from grade/floors if needed)
  beds: float
  baths: float
  sqft_living: int
  sqft_lot: int | None
  year_built: int | None
  condition: int | None         # 1–5
  grade: int | None             # KC grade
  lat: float; lng: float        # or geocode from address (stretch); KC is coordinate-native
  as_of_date: date              # default = today; for backtest = the held-out sale date
  # extraction metadata:
  field_confidence: dict[str,float] | None
  needs_review: list[str] | None

Comp(Subject-ish):              # a real sale row
  sale_price: int; sale_date: date; price_per_sqft: float; distance_km: float

ScoredComp:
  comp: Comp
  similarity: float             # 0–1
  subscores: dict[str,float]    # distance, recency, area, bed_bath, age, grade
  adjustments: dict[str,float]  # line-item $ deltas applied
  adjusted_price: int
  flagged: bool; flag_reason: str | None

Valuation:
  conservative_value: int       # the lender-facing figure (headline)
  point_estimate: int
  range_low: int; range_high: int
  confidence: Literal["High","Medium","Low"]
  confidence_factors: dict[str,float]
  comps: list[ScoredComp]       # 10–20, flagged ones included & marked
  rationale: str                # plain-English, from the LLM
  mode: Literal["agent","deterministic"]
  elapsed_ms: int
```

---

## 6. Deterministic core — the math (all in `config.py`, tunable)

**Retrieval (`search_comps`):**

- Hard filters: compatible property type; `sale_date < subject.as_of_date`; within radius; within time window.
- Start radius 2 km, time 180 d. If `< 10` candidates, widen to (5 km, 365 d), then (10 km, 540 d). Target **10–20**.
- Distance via haversine on lat/long.

**Scoring (`score_comps`) — weighted sum of normalized 0–1 subscores (Sam: location, size, age, recency dominate):**

```
distance        0.30
living_area     0.20
recency         0.15
grade/condition 0.15
age (yr_built)  0.10
bed/bath        0.10
```

Rank; keep the strongest 10–20.

**Outlier flag (`flag_outliers`) — FIRST-CLASS, Sam's explicit ask:**

- Compute robust band on candidate-set `$/sqft`: median ± 3·MAD (or IQR fences Q1−1.5·IQR / Q3+1.5·IQR).
- Comps outside the band → `flagged=True`, excluded from the estimate, with `flag_reason`
  (e.g. "$/sqft of $612 is 2.8× the neighborhood median of $218 — likely a teardown/lot sale").
- Surface flags in the UI and the rationale. This is the hero demo moment.

**Adjustment + estimate (`hedonic.py` + `estimate.py`):**

- Fit a global hedonic regression once at boot: `log(price) ~ sqft_living + beds + baths + grade + age (+ zip)`
  → interpretable marginal $/feature. (sklearn LinearRegression; not a black box.)
- Per-comp adjustment grid: adjust each comp's `sale_price` for differences vs subject using those marginals.
- Time adjustment: fit a simple monthly `$/sqft` index; bring each comp to the subject's `as_of_date`.
- `point_estimate` = similarity-weighted average of non-flagged adjusted prices.
- `range` = [P25, P75] of adjusted prices (or ± dispersion).
- `conservative_value` (headline) = the defensible floor a lender should size against, e.g.
  `min(point_estimate − margin, P25)`, where `margin` scales with dispersion + distance + staleness. Tunable.
- `confidence` from: comp count, mean distance, recency, dispersion → High/Medium/Low, with the factors exposed.

**Honest accuracy expectation (put in README, don't overclaim):** this is essentially off-market prediction;
Zillow's off-market median error is ~7% with a mature ML stack. A backtest MdAPE in ~8–15% on King County is a
credible, honest result. The value prop is a defensible, auditable workflow at speed — not SOTA accuracy.

---

## 7. Agent layer (Gemini)

- **`extract.py`** (document/text input only): Gemini **Flash-Lite**, multimodal, `responseSchema = Subject`.
  Returns fields + per-field confidence + `needs_review` for low-confidence/missing. Frontend lets the user
  review/edit before valuing. Building plans: extract what's reliably there; flag the rest — do not hallucinate.
- **`reason.py`**: Gemini **Flash**, given subject + scored candidates + computed estimate/flags. Produces:
  a sanity check on the deterministic flags (agree/override with reason), the **defensible plain-English
  rationale**, and a confidence call. May request **one** widen if it judges comps insufficient.
- **`orchestrator.py`**: bounded loop (hard cap 1 re-query). If `GEMINI_API_KEY` absent or a `429`/error →
  **deterministic mode**: skip extraction (require form/structured), generate the rationale from a template.
  The app never just breaks. Cache identical requests.
- **Privacy note for README:** Gemini free tier may train on inputs/outputs — fine for public+synthetic data;
  KV's real data would need the paid (no-training) tier. Noting this = production maturity points.

---

## 8. API (FastAPI)

```
POST /api/extract   multipart file (pdf/image) OR {text}  → Subject + field_confidence + needs_review
POST /api/value     Subject (structured)                  → Valuation
GET  /api/health    → {status, model_available, comps_loaded}   # keep-warm + frontend readiness
GET  /api/samples   → preloaded demo subjects incl. edge cases
```

CORS: allow the Vercel origin via `ALLOWED_ORIGINS` env. Return `elapsed_ms` so the UI can show speed.

---

## 9. Frontend (Vite + React + TS + Tailwind + react-leaflet)

**Flow:** input (3 tabs: Upload doc / Paste text / Fill form) → if doc/text, call `/extract`, show **editable
extracted fields with confidence chips + review flags** → user confirms → call `/value` → results.

**Results view (the hero):**

- Big **conservative defensible value** + range + confidence badge. Point estimate secondary.
- "**Valued in X.Xs**" (Sam: speed is the pain — make it visible).
- **Map**: subject pin + comp pins (color by similarity; flagged comps marked distinctly).
- **Comp table** (10–20, sortable): similarity, $/sqft, adjustments, outlier flag + reason.
- **Rationale** (LLM prose) + expandable **agent trace** (tool calls) for transparency.
- One-click **demo subjects** (incl. sparse-comps + outlier cases) so the demo is frictionless.

**Cold-start UX:** on load, ping `/api/health`; if backend is waking, show a friendly "warming up the valuation
engine (~30s)" state with retry — never a raw spinner or a failed fetch.

Env: `VITE_API_BASE_URL` → Render backend URL.

---

## 10. Deployment

**Vercel (frontend):** static build; set `VITE_API_BASE_URL`. Always-on, no sleep, CDN.

**Render (backend, Docker):**

- Env: `GEMINI_API_KEY`, `ALLOWED_ORIGINS` (Vercel domain).
- Free web service sleeps after 15 min (30–60s cold start) on an ephemeral filesystem — irrelevant since the
  comps store is read-only and rebuilt from the bundled parquet at boot.
- **Keep-warm:** free uptime pinger (cron-job.org / UptimeRobot) hitting `/api/health` every ~10–14 min. One
  always-on free service fits inside the 750 instance-hours/month budget.

**Docker (backend):** python-slim, `uv` install, copy app + `data/kc_sales.parquet`, run `uvicorn`. Keep lean.

---

## 11. Testing (lean, on the core — "tests where they earn their keep")

Target ~20–30 focused tests, not 100 shallow ones. State this philosophy in the README.

- Scoring monotonicity: closer / more recent / more similar comp scores higher.
- Haversine correctness; adjustment-grid math; time-adjustment direction.
- **Leakage guard:** assert no comp dated ≥ subject as_of_date is ever returned.
- Outlier detection: known outlier gets flagged + excluded.
- Invariants: estimate ∈ [min, max] of adjusted non-flagged comps; higher dispersion → lower confidence;
  conservative_value ≤ point_estimate.
- One **eval regression test:** backtest MdAPE on a fixed seed/sample stays below a threshold.
- Tool tests call tools directly (no LLM). One mocked-LLM test: agent respects the re-query cap and tool order.
- CI: GitHub Actions running ruff + pytest (core tests run without an API key).

---

## 12. Eval harness (the differentiator)

- Leave-one-out backtest over a random holdout (~300–500 subjects): hide price, predict from prior comps,
  compare to actual sale price.
- Metrics: **MdAPE**, % within 5/10/20%, coverage (how often ≥10 comps found). Report vs the ~7% Zillow
  off-market context, honestly.
- Output `docs/eval_report.md` (+ JSON), committed. Lock a baseline number EARLY — it anchors the whole eval
  narrative and the demo.

---

## 13. README (submission — heavily weighted; answer their explicit asks in order)

1. One-line summary + 20-sec "what it does".
2. **Problem understanding** — lender framing, comps, why it's slow, what Sam said.
3. **Approach & key decisions** — hybrid trust boundary, comps-not-black-box, ≤2 LLM calls (with the speed
   rationale), dataset choice, the cuts you made.
4. **Architecture diagram** (Mermaid — renders on GitHub) + agent sequence (Mermaid).
5. Scoring & valuation methodology (features, weights, adjustment, conservative anchor, confidence).
6. Agent design + a pasted sample trace.
7. **Evaluation** — backtest method incl. leakage guard, metrics in Zillow context, honest limitations.
8. Edge cases handled (sparse comps, stale market, $/sqft outliers, unusual subject, missing fields).
9. **How to run** — deterministic mode (no key) + full agent mode; example I/O; live URL.
10. Tradeoffs & **what I cut** (Pragmatism — scored).
11. **What I'd build next** (commercial, Alberta data, persistence, plan parsing, paid no-train tier).
12. Tech stack.
    Include a UI screenshot/GIF. Link the demo video. Note the phone number used to call Sam.

---

## 14. Demo video (≤3 min — the Notion brief says 3, not the Luma 10)

- 0:00–0:25 — problem + lender framing (defensible comps, fast).
- 0:25–1:45 — live: upload a doc → review extracted fields → value it → show conservative value + range +
  confidence + map + comp table + rationale. Then trigger the **$/sqft outlier flag** and a **sparse-comps**
  case (agent widens, drops confidence). This is the rubric, demonstrated.
- 1:45–2:25 — architecture + trust boundary + backtest results, honest about limits.
- 2:25–2:55 — what's next + sign off.
  Record after the build is stable. Rehearse. Clear audio, no dead air.

---

## 15. Build sequence (for Claude Code)

- **P0** — scaffold, `prepare_data.py`, schemas, config.
- **P1** — deterministic core (retrieve → score → outliers → hedonic → estimate/conservative/confidence) + unit tests.
- **P2** — eval harness; lock baseline MdAPE.
- **P3** — Gemini layer (extract + reason + orchestrator + deterministic fallback).
- **P4** — FastAPI (`/extract`, `/value`, `/health`, `/samples`) + CORS.
- **P5** — frontend (input → review → results, map, cold-start UX, demo subjects).
- **P6** — Dockerfile + deploy (Render + Vercel) + keep-warm pinger.
- **P7** — README + Mermaid diagrams + test/eval polish + record demo.

Cut order if ever needed: map → frontend (fall back to CLI+API) → hedonic adjustment (fall back to
similarity-weighted $/sqft). Protect: eval harness, README clarity, the $/sqft flag, the conservative-value framing.

---

## 16. Submission checklist

- [ ] Public GitHub repo at submission time
- [ ] README: problem / approach / how-to-run / what's-next
- [ ] Demo video ≤3 min, linked in README
- [ ] Phone number used to call Sam, noted in README
- [ ] Live URL (Vercel frontend → Render backend), with cold-start handled
- [ ] Runs in deterministic mode with no API key
- [ ] Submit at https://kv-ai-engineer-hiring.vercel.app/submit by **Fri Jun 12, 2026, 11:59 PM MST**
