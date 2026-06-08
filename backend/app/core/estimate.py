"""Adjustment grid → point estimate, range, conservative anchor, confidence.

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


def _empty_valuation(subject: Subject) -> Valuation:
    """No comps at all. Distinguish an out-of-window as-of date (State A) from a barren location
    within the dataset window (State B), since the fix the user needs differs."""
    if subject.as_of_date < config.DATA_WINDOW_START or subject.as_of_date > config.DATA_WINDOW_END:
        rationale = (
            "No comparable sales found: the as-of date falls outside the dataset window "
            "(2014-05 to 2015-05). Change the as-of date to a date within the dataset range."
        )
    else:
        rationale = (
            "No comparable sales were found in this area within the search radius. "
            "Verify the subject location."
        )
    return Valuation(
        conservative_value=0,
        point_estimate=0,
        range_low=0,
        range_high=0,
        confidence="Low",
        confidence_factors=_empty_factors(),
        comps=[],
        rationale=rationale,
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


_EXCLUSION_LABELS = {
    "outlier": "$/sqft outlier",
    "low_similarity": "low similarity",
    "large_adjustment": "over-adjusted",
}


def _exclusion_breakdown(scored: list[ScoredComp]) -> tuple[int, int, str]:
    """Return (n_excluded, n_total, "N label, ...") for the rationale; asserts the tally ties."""
    counts = {key: sum(1 for sc in scored if sc.status == key) for key in _EXCLUSION_LABELS}
    n_excluded = sum(counts.values())
    # The categorized total must equal every non-"included" comp; a new status that escapes
    # ``_EXCLUSION_LABELS`` would undercount the rationale, so fail loudly rather than mislead.
    n_other = sum(1 for sc in scored if sc.status != "included")
    assert n_excluded == n_other, f"exclusion tally mismatch: {n_excluded} vs {n_other}"
    breakdown = ", ".join(
        f"{counts[key]} {_EXCLUSION_LABELS[key]}" for key in _EXCLUSION_LABELS if counts[key]
    )
    return n_excluded, len(scored), breakdown


def _exclusion_summary(scored: list[ScoredComp]) -> str:
    """One-line count of excluded comps by reason, for the insufficient-comps rationale."""
    n_excluded, n_total, breakdown = _exclusion_breakdown(scored)
    if not n_excluded:
        return ""
    return f"Excluded {n_excluded} of {n_total} comps: {breakdown}."


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
    factors: dict[str, float],
) -> str:
    """Templated lender rationale. No confidence label (it is on the badge), no raw margin figure.

    Percentages use ``_pct`` (half-up) so dispersion and mean adjustment match the stat row exactly.
    """
    dispersion = factors[config.CF_DISPERSION]
    s = "" if n_used == 1 else "s"
    variability = "moderate" if dispersion > 0.15 else "manageable"
    n_excluded, n_total, breakdown = _exclusion_breakdown(scored)
    exclusion_sentence = (
        f" Excluded {n_excluded} of {n_total} comparables: {breakdown}." if n_excluded else ""
    )
    return (
        f"Conservative value ${conservative:,.0f} is positioned below the point estimate of "
        f"${point:,.0f} based on {n_used} comparable sale{s} within "
        f"{factors[config.CF_MEAN_DISTANCE_KM]:.1f} km, with a median sale age of "
        f"{factors[config.CF_MEDIAN_AGE_DAYS]:.0f} days. The margin reflects {_pct(dispersion)} "
        f"price dispersion among the included comparables and a "
        f"{_pct(factors[config.CF_MEAN_ADJUSTMENT])} mean hedonic adjustment, indicating "
        f"{variability} market variability.{exclusion_sentence}"
    )


def estimate_value(
    subject: Subject,
    scored: list[ScoredComp],
    hedonic: HedonicModel,
) -> Valuation:
    """Similarity-weighted estimate, [P25, P75] range, conservative headline, and confidence."""
    if not scored:
        return _empty_valuation(subject)

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
        rationale=_rationale(scored, len(usable), point, conservative, factors),
        mode="deterministic",
        elapsed_ms=0,
    )
