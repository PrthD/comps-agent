"""Adjustment grid → point estimate, range, conservative anchor, confidence (BUILD_BRIEF §6).

Applies the hedonic + time adjustment to every comp, then estimates from the comps that are actually
comparable. A comp is excluded (but still shown) when it is a $/sqft outlier, scores below the
similarity floor, or needs a hedonic adjustment larger than the cap. If fewer than
``MIN_COMPS_FOR_ESTIMATE`` survive, we return an explicit "insufficient comparable sales" result
rather than valuing off one or two weak comps. All confidence/threshold keys come from ``config``
constants so the metric names can never drift; ages are handled in DAYS, converted to YEARS only at
the conservative-staleness edge via ``config.DAYS_PER_YEAR``.
"""

from __future__ import annotations

import numpy as np

from app import config
from app.core.hedonic import HedonicModel, adjust_comp
from app.schemas import ScoredComp, Subject, Valuation


def compute_confidence(factors: dict[str, float]) -> str:
    """High/Medium/Low by reading the exact bound keys from ``config.CONFIDENCE_THRESHOLDS``."""
    for level in ("High", "Medium"):
        bounds = config.CONFIDENCE_THRESHOLDS[level]
        if (
            factors[config.CF_COMP_COUNT] >= bounds[config.CT_MIN_COMPS]
            and factors[config.CF_MEAN_DISTANCE_KM] <= bounds[config.CT_MAX_MEAN_DISTANCE_KM]
            and factors[config.CF_DISPERSION] <= bounds[config.CT_MAX_DISPERSION]
            and factors[config.CF_MEDIAN_AGE_DAYS] <= bounds[config.CT_MAX_MEDIAN_AGE_DAYS]
            and factors[config.CF_MEAN_ADJUSTMENT] <= bounds[config.CT_MAX_MEAN_ADJUSTMENT]
        ):
            return level
    return "Low"


def _empty_factors(comp_count: float = 0.0) -> dict[str, float]:
    return {
        config.CF_COMP_COUNT: comp_count,
        config.CF_MEAN_DISTANCE_KM: 0.0,
        config.CF_DISPERSION: 0.0,
        config.CF_MEDIAN_AGE_DAYS: 0.0,
        config.CF_MEAN_ADJUSTMENT: 0.0,
    }


def _empty_valuation() -> Valuation:
    return Valuation(
        conservative_value=0,
        point_estimate=0,
        range_low=0,
        range_high=0,
        confidence="Low",
        confidence_factors=_empty_factors(),
        comps=[],
        rationale="No comparable sales found before the as-of date within the widest search tier.",
        mode="deterministic",
        elapsed_ms=0,
    )


def _adjustment_fraction(scored: ScoredComp) -> float:
    """Absolute hedonic adjustment as a fraction of the comp's actual sale price."""
    base = scored.comp.sale_price
    return abs(scored.adjusted_price - base) / base if base else 0.0


def _classify(scored: list[ScoredComp]) -> None:
    """Assign each comp a status (and an exclusion reason). Mutates in place.

    Precedence: a $/sqft outlier (already flagged by ``flag_outliers``) stays an outlier; otherwise
    a comp below the similarity floor is "low_similarity"; otherwise one needing too large an
    adjustment is "large_adjustment"; otherwise "included".
    """
    min_sim = config.MIN_SIMILARITY_FOR_ESTIMATE
    max_adj = config.MAX_ADJUSTMENT_FRACTION
    for sc in scored:
        if sc.flagged:  # $/sqft outlier flagged upstream by flag_outliers
            sc.status = "outlier"
            continue
        if sc.similarity < min_sim:
            sc.status = "low_similarity"
            sc.flagged = True
            sc.flag_reason = (
                f"Similarity {sc.similarity:.0%} is below the {min_sim:.0%} floor; "
                "not comparable enough to value against."
            )
            continue
        frac = _adjustment_fraction(sc)
        if frac > max_adj:
            sc.status = "large_adjustment"
            sc.flagged = True
            sc.flag_reason = (
                f"Hedonic adjustment of {frac:.0%} exceeds the {max_adj:.0%} cap; "
                "not comparable enough to value against."
            )
            continue
        sc.status = "included"


def _exclusion_summary(scored: list[ScoredComp]) -> str:
    """One-line count of excluded comps by reason, for the rationale (plain punctuation)."""
    labels = {
        "outlier": "$/sqft outlier",
        "low_similarity": "low similarity",
        "large_adjustment": "over-adjusted",
    }
    counts = {key: sum(1 for sc in scored if sc.status == key) for key in labels}
    total = sum(counts.values())
    # The categorized total must equal every non-"included" comp; a new status that escapes
    # ``labels`` would undercount the rationale, so fail loudly rather than mislead the UI.
    n_excluded = sum(1 for sc in scored if sc.status != "included")
    assert total == n_excluded, f"exclusion tally mismatch: {total} categorized vs {n_excluded}"
    if not total:
        return ""
    parts = [f"{counts[key]} {labels[key]}" for key in labels if counts[key]]
    return f"Excluded {total} of {len(scored)} comps: " + ", ".join(parts) + "."


def _insufficient_valuation(scored: list[ScoredComp], n_included: int) -> Valuation:
    """Return an explicit no-value result when too few comps are comparable enough to trust."""
    summary = _exclusion_summary(scored)
    detail = f" {summary}" if summary else ""
    return Valuation(
        conservative_value=0,
        point_estimate=0,
        range_low=0,
        range_high=0,
        confidence="Low",
        confidence_factors=_empty_factors(float(n_included)),
        comps=scored,
        rationale=(
            f"Insufficient comparable sales: only {n_included} of {len(scored)} retrieved comps "
            f"are comparable enough to value (minimum {config.MIN_COMPS_FOR_ESTIMATE})."
            f"{detail} No defensible value is produced; widen the search area or date window, or "
            "confirm the subject details."
        ),
        mode="deterministic",
        elapsed_ms=0,
    )


def _pct(value: float) -> str:
    """Half-up percent (floor(x+0.5)), matching the frontend stat row and the reason payload so a
    percentage in this templated rationale never disagrees with the displayed figure at a tie."""
    return f"{int(value * 100 + 0.5)}%"


def _rationale(
    scored: list[ScoredComp],
    n_used: int,
    point: float,
    conservative: float,
    margin: float,
    confidence: str,
    factors: dict[str, float],
) -> str:
    text = (
        f"Conservative value ${conservative:,.0f} (point estimate ${point:,.0f}) from "
        f"{n_used} comparable sale(s) within {factors[config.CF_MEAN_DISTANCE_KM]:.1f} km, "
        f"median age {factors[config.CF_MEDIAN_AGE_DAYS]:.0f} days. A {_pct(margin)} margin "
        f"reflects price dispersion ({_pct(factors[config.CF_DISPERSION])}), distance, recency, "
        f"and a {_pct(factors[config.CF_MEAN_ADJUSTMENT])} mean hedonic adjustment. "
        f"Confidence: {confidence}."
    )
    summary = _exclusion_summary(scored)
    if summary:
        text += " " + summary
    return text


def estimate_value(
    subject: Subject,
    scored: list[ScoredComp],
    hedonic: HedonicModel,
) -> Valuation:
    """Similarity-weighted estimate, [P25, P75] range, conservative headline, and confidence."""
    if not scored:
        return _empty_valuation()

    # 1. Hedonic + time adjustment for every comp (line items recorded on each ScoredComp).
    for sc in scored:
        sc.adjustments, sc.adjusted_price = adjust_comp(subject, sc.comp, hedonic)

    # 2. Classify each comp; only "included" comps drive the figures.
    _classify(scored)
    usable = [sc for sc in scored if sc.status == "included"]
    if len(usable) < config.MIN_COMPS_FOR_ESTIMATE:
        return _insufficient_valuation(scored, len(usable))

    adjusted = np.array([sc.adjusted_price for sc in usable], dtype=float)
    sims = np.array([sc.similarity for sc in usable], dtype=float)
    weights = sims if sims.sum() > 0 else np.ones_like(sims)
    point = float(np.average(adjusted, weights=weights))
    p25, p75 = (float(x) for x in np.percentile(adjusted, [25, 75]))

    # 3. Confidence factors (ages in DAYS).
    distances = np.array([sc.comp.distance_km for sc in usable], dtype=float)
    ages = np.array([(subject.as_of_date - sc.comp.sale_date).days for sc in usable], dtype=float)
    mean_adjusted = float(adjusted.mean())
    dispersion = float(adjusted.std() / mean_adjusted) if mean_adjusted else 0.0
    mean_adjustment = float(np.mean([_adjustment_fraction(sc) for sc in usable]))
    factors = {
        config.CF_COMP_COUNT: float(len(usable)),
        config.CF_MEAN_DISTANCE_KM: float(distances.mean()),
        config.CF_DISPERSION: dispersion,
        config.CF_MEDIAN_AGE_DAYS: float(np.median(ages)),
        config.CF_MEAN_ADJUSTMENT: mean_adjustment,
    }
    confidence = compute_confidence(factors)

    # 4. Conservative anchor: margin from dispersion, distance, staleness (days→years here), and
    #    how hard the comp set had to be stretched (mean adjustment fraction). A set fitted only by
    #    large average adjustments yields a visibly lower, wider-margin defensible value.
    mean_age_years = float(ages.mean()) / config.DAYS_PER_YEAR
    margin = min(
        config.CONSERVATIVE_BASE_MARGIN
        + config.CONSERVATIVE_DISPERSION_COEF * dispersion
        + config.CONSERVATIVE_DISTANCE_COEF * factors[config.CF_MEAN_DISTANCE_KM]
        + config.CONSERVATIVE_STALENESS_COEF * mean_age_years
        + config.CONSERVATIVE_ADJUSTMENT_COEF * mean_adjustment,
        config.CONSERVATIVE_MARGIN_CAP,
    )
    conservative = min(point * (1.0 - margin), p25)

    return Valuation(
        conservative_value=int(round(conservative)),
        point_estimate=int(round(point)),
        range_low=int(round(p25)),
        range_high=int(round(p75)),
        confidence=confidence,
        confidence_factors=factors,
        comps=scored,  # all comps, excluded ones included and marked with a status
        rationale=_rationale(scored, len(usable), point, conservative, margin, confidence, factors),
        mode="deterministic",
        elapsed_ms=0,
    )
