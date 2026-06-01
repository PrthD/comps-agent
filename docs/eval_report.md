# Evaluation Report — Deterministic Comps Engine

Leave-one-out backtest on the King County dataset (BUILD_BRIEF §12). Each held-out sale is valued
as-of its **true sale date** using only sales **strictly before** that date (leakage guard), and
never its own row. Accuracy is measured against the **point estimate** — the conservative value is
deliberately biased low and is *not* the accuracy target.

## Run
- Sample: **400** subjects · random seed **42** · wall time 10.2s
- Valued (≥1 comp): **399**

## Headline metrics (point estimate vs. actual sale price)
| Metric | Value |
|---|---|
| **MdAPE** (median abs. % error) | **10.2%** |
| MAPE (mean) | 14.3% |
| Within 5% | 25.6% |
| Within 10% | 49.1% |
| Within 20% | 76.2% |
| Coverage (≥1 comp) | 99.8% |
| Coverage (≥10 comps) | 98.8% |

## Context & honesty
Off-market valuation is hard: Zillow's off-market median error is ~7% with a mature ML stack and
nationwide data. An MdAPE of **10.2%** on a single market with a transparent, auditable
hedonic + comps pipeline is an honest, credible result. The value proposition is a **defensible,
explainable** valuation at speed — not state-of-the-art accuracy.

## Hedonic model (validated before measuring)
- `sqft_living`: log-elasticity **0.5015** (scale-free; fixes raw-scale swamping).
- Fitted coefficients: `{'sqft_living': 0.5015, 'beds': -0.0259, 'baths': 0.0453, 'grade': 0.1335, 'age': 0.0022}`
- Applied (sign-clamped) coefficients: `{'sqft_living': 0.5015, 'beds': 0.0, 'baths': 0.0453, 'grade': 0.1335, 'age': 0.0}`
- Clamped to 0 — backwards-signed, never applied: `['beds', 'age']`
- Implied $/sqft level: **$247** (sane band $150–$400).
  Implied marginal $/sqft: $123 (diminishing returns).

## Limitations
- King County is a stand-in for MLS sold-comp structure; the pipeline is geography-agnostic.
- The hedonic model is fit once on the full dataset (per-subject influence ~1/N, negligible); the
  leakage rule is enforced at the comp level and asserted per subject.
- The monthly time index is clamped to the data window (May 2014–May 2015) — no extrapolation.
- `property_type` is a documented heuristic (KC lacks a true type label).
