# Sample trace: Wallingford bungalow

A real run of the deterministic engine on the "Wallingford bungalow" demo subject, as-of
2015-05-01 (inside the King County data window). Every figure below comes from the core; the
rationale is the deterministic template (no API key needed). The numbers reproduce exactly because
the pipeline is pure and seeded.

## Subject

| Field         | Value             |
| ------------- | ----------------- |
| Property type | detached          |
| Beds          | 3                 |
| Baths         | 2                 |
| Living area   | 1,800 sqft        |
| Lot           | 4,000 sqft        |
| Year built    | 1960              |
| Grade         | 7                 |
| Condition     | 3                 |
| Location      | 47.6795, -122.346 |
| As-of date    | 2015-05-01        |

## Deterministic output

| Field                             | Value                |
| --------------------------------- | -------------------- |
| **Conservative value (headline)** | **$563,019**         |
| Point estimate                    | $654,849             |
| Range (P25 to P75)                | $633,214 to $715,664 |
| Confidence                        | Medium               |
| Comps retrieved                   | 20                   |
| Comps included                    | 17                   |
| Comps excluded                    | 3 ($/sqft outliers)  |
| Mean comp distance                | 1.2 km               |
| Median sale age                   | 59 days              |
| Price dispersion                  | 12%                  |
| Mean hedonic adjustment           | 9%                   |
| Compute time                      | ~30 ms               |

## Rationale

> Conservative value $563,019 is positioned below the point estimate of $654,849 based on 17
> comparable sales within 1.2 km, with a median sale age of 59 days. The margin reflects 12% price
> dispersion among the included comparables and a 9% mean hedonic adjustment, indicating manageable
> market variability. Excluded 3 of 20 comparables: 3 $/sqft outlier.

With a `GEMINI_API_KEY` set, the same numbers are sent to Gemini Flash, which replaces this template
with an interpretive lender rationale. The figures never change; only the prose does.

## What this shows

- The headline is the **conservative value** ($563,019), below the point estimate. A lender sizes
  against this, not the point.
- 3 of 20 retrieved comps were flagged as $/sqft outliers and excluded from the math, but stay
  visible in the table with their reason.
- Confidence is Medium: 17 comps clears the count and distance bars, but the price dispersion
  (0.1235) edges just past the High cap of 0.12, so it lands in the Medium band rather than High.
  It displays as 12% rounded, which is why the rounded figure alone does not tell the whole story.
- The conservative margin reflects dispersion, distance, staleness, and the mean adjustment, capped
  at 25%.
