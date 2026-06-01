"""Adjustment grid → point estimate, range, conservative anchor, confidence (BUILD_BRIEF §6).

Applies the hedonic + time adjustment to every comp, then computes the lender-facing figures from
the NON-FLAGGED comps only. All confidence/threshold keys come from ``config`` constants so the
metric names can never drift from ``CONFIDENCE_THRESHOLDS``. Ages are handled in DAYS internally;
the staleness term converts to YEARS at the edge via ``config.DAYS_PER_YEAR``.
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
        ):
            return level
    return "Low"


def _empty_valuation() -> Valuation:
    factors = {
        config.CF_COMP_COUNT: 0.0,
        config.CF_MEAN_DISTANCE_KM: 0.0,
        config.CF_DISPERSION: 0.0,
        config.CF_MEDIAN_AGE_DAYS: 0.0,
    }
    return Valuation(
        conservative_value=0,
        point_estimate=0,
        range_low=0,
        range_high=0,
        confidence="Low",
        confidence_factors=factors,
        comps=[],
        rationale="No comparable sales found before the as-of date within the widest search tier.",
        mode="deterministic",
        elapsed_ms=0,
    )


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
        f"median age {factors[config.CF_MEDIAN_AGE_DAYS]:.0f} days. A {margin:.0%} margin "
        f"reflects price dispersion ({factors[config.CF_DISPERSION]:.0%}), distance, and "
        f"recency. Confidence: {confidence}."
    )
    flagged = sum(1 for sc in scored if sc.flagged)
    if flagged:
        text += f" {flagged} comp(s) flagged as $/sqft outliers and excluded from the estimate."
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

    # 2. Estimate from non-flagged comps; degrade to all comps only if every one was flagged.
    usable = [sc for sc in scored if not sc.flagged] or scored
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
    factors = {
        config.CF_COMP_COUNT: float(len(usable)),
        config.CF_MEAN_DISTANCE_KM: float(distances.mean()),
        config.CF_DISPERSION: dispersion,
        config.CF_MEDIAN_AGE_DAYS: float(np.median(ages)),
    }
    confidence = compute_confidence(factors)

    # 4. Conservative anchor: margin from dispersion, distance, staleness (days→years here).
    mean_age_years = float(ages.mean()) / config.DAYS_PER_YEAR
    margin = min(
        config.CONSERVATIVE_BASE_MARGIN
        + config.CONSERVATIVE_DISPERSION_COEF * dispersion
        + config.CONSERVATIVE_DISTANCE_COEF * factors[config.CF_MEAN_DISTANCE_KM]
        + config.CONSERVATIVE_STALENESS_COEF * mean_age_years,
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
        comps=scored,  # all comps, flagged ones included and marked
        rationale=_rationale(scored, len(usable), point, conservative, margin, confidence, factors),
        mode="deterministic",
        elapsed_ms=0,
    )
