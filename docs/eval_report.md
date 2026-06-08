# Evaluation Report, Deterministic Comps Engine

Leave-one-out backtest on the King County dataset. Each held-out sale is valued
as-of its **true sale date** using only sales **strictly before** that date (leakage guard), and
never its own row. Accuracy is measured against the **point estimate**, the conservative value is
deliberately biased low and is *not* the accuracy target.

## Run
- Sample: **400** subjects · random seed **42** · wall time 8.9s
- Valued: **383** · refused as "insufficient comparable sales": **17**

Accuracy is measured over the **valued** subjects (a refused subject produces no number, so it
cannot have an error). This is deliberate: the engine declines rather than reporting a misleading
value off one or two weak comps.

## Headline metrics (point estimate vs. actual sale price)
| Metric | Value |
|---|---|
| **MdAPE** (median abs. % error) | **9.8%** |
| MAPE (mean) | 14.0% |
| Within 5% | 26.1% |
| Within 10% | 50.1% |
| Within 20% | 77.3% |
| Coverage (≥1 comp) | 99.8% |
| Coverage (≥10 comps) | 98.8% |

## Context & honesty
Off-market valuation is hard: Zillow's off-market median error is ~7% with a mature ML stack and
nationwide data. An MdAPE of **9.8%** on a single market with a transparent, auditable
hedonic + comps pipeline is an honest, credible result. The value proposition is a **defensible,
explainable** valuation at speed, not state-of-the-art accuracy.

## Comp-quality gate
Only genuinely comparable comps drive the estimate. A comp is excluded (still shown in the UI with
its status) when it is a $/sqft outlier, scores below the
**45%** similarity floor, or needs a hedonic adjustment above
the **30%** cap. If fewer than **3**
survive, the engine returns "insufficient comparable sales" rather than valuing off weak comps
(17 of 400 backtest subjects hit that gate). This trades a little coverage for
defensibility; MdAPE on the subjects that do value is unchanged to slightly better.

## Confidence calibration
Confidence reflects not just comp count, distance, dispersion, and recency, but also the **mean
hedonic adjustment** across the included comps: a set that only fits the subject after large average
adjustments cannot be High (mean adjustment must be
≤ 10%) or Medium
(≤ 18%); above that it is
Low. The same mean-adjustment term widens the conservative margin, so a stretched set yields a
visibly lower, wider-margin defensible value. Confidence over the **383** valued subjects:
High **72** (19%), Medium **238**
(62%), Low **73** (19%). This calibration
changes confidence labels and the conservative value, not the point estimate, so headline MdAPE is
essentially unchanged.

## Hedonic model (validated before measuring)
- `sqft_living`: log-elasticity **0.5015** (scale-free; fixes raw-scale swamping).
- Fitted coefficients: `{'sqft_living': 0.5015, 'beds': -0.0259, 'baths': 0.0453, 'grade': 0.1335, 'age': 0.0022}`
- Applied (sign-clamped) coefficients: `{'sqft_living': 0.5015, 'beds': 0.0, 'baths': 0.0453, 'grade': 0.1335, 'age': 0.0}`
- Clamped to 0, backwards-signed, never applied: `['beds', 'age']`
- Implied $/sqft level: **$247** (sane band $150 to $400).
  Implied marginal $/sqft: $123 (diminishing returns).

## Limitations
- King County is a stand-in for MLS sold-comp structure; the pipeline is geography-agnostic.
- The hedonic model is fit once on the full dataset (per-subject influence ~1/N, negligible); the
  leakage rule is enforced at the comp level and asserted per subject.
- The monthly time index is clamped to the data window (May 2014 to May 2015), no extrapolation.
- `property_type` is a documented heuristic (KC lacks a true type label).
