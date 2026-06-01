"""Weighted-similarity scoring of candidate comps (BUILD_BRIEF §6).

Each subscore is normalized to 0–1 (1 = identical) using ``config.SUBSCORE_SCALES``; the similarity
is their ``config.SCORING_WEIGHTS`` weighted sum. Subscore dict keys are the SUBSCORE_* constants,
so they can never drift from the weight keys.
"""

from __future__ import annotations

from app import config
from app.schemas import Comp, ScoredComp, Subject


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _diff_score(diff: float, scale: float) -> float:
    """1 at zero difference, decaying linearly to 0 at ``scale`` (and clamped to 0–1)."""
    return _clamp01(1.0 - abs(diff) / scale)


def _opt_diff_score(a: float | None, b: float | None, scale: float) -> float:
    """Like ``_diff_score`` but neutral (0.5) when either value is missing."""
    if a is None or b is None:
        return 0.5
    return _diff_score(a - b, scale)


def _subscores(subject: Subject, comp: Comp) -> dict[str, float]:
    s = config.SUBSCORE_SCALES
    age_days = (subject.as_of_date - comp.sale_date).days
    grade = _opt_diff_score(subject.grade, comp.grade, s["grade"])
    condition = _opt_diff_score(subject.condition, comp.condition, s["condition"])
    bed = _diff_score(subject.beds - comp.beds, s["beds"])
    bath = _diff_score(subject.baths - comp.baths, s["baths"])
    return {
        config.SUBSCORE_DISTANCE: _clamp01(1.0 - comp.distance_km / s["distance_km"]),
        config.SUBSCORE_LIVING_AREA: _diff_score(
            (comp.sqft_living - subject.sqft_living) / subject.sqft_living, s["living_area_frac"]
        ),
        config.SUBSCORE_RECENCY: _clamp01(1.0 - age_days / s["recency_days"]),
        config.SUBSCORE_GRADE_CONDITION: 0.5 * grade + 0.5 * condition,
        config.SUBSCORE_AGE: _opt_diff_score(subject.year_built, comp.year_built, s["age_years"]),
        config.SUBSCORE_BED_BATH: 0.5 * bed + 0.5 * bath,
    }


def score_comps(subject: Subject, comps: list[Comp]) -> list[ScoredComp]:
    """Score and rank candidates; keep the strongest TARGET_COMPS_MAX (BUILD_BRIEF §6)."""
    scored: list[ScoredComp] = []
    for comp in comps:
        subs = _subscores(subject, comp)
        similarity = sum(config.SCORING_WEIGHTS[k] * subs[k] for k in config.SCORING_WEIGHTS)
        scored.append(
            ScoredComp(
                comp=comp,
                similarity=round(_clamp01(similarity), 4),
                subscores=subs,
                adjustments={},
                adjusted_price=comp.sale_price,  # placeholder until hedonic adjustment
            )
        )
    scored.sort(key=lambda sc: sc.similarity, reverse=True)
    return scored[: config.TARGET_COMPS_MAX]
