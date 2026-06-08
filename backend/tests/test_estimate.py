"""Estimate invariants and confidence behavior (BUILD_BRIEF §6/§11)."""

from __future__ import annotations

from app import config
from app.agent.orchestrator import value_deterministic
from app.core.estimate import compute_confidence, estimate_value
from app.schemas import ScoredComp

_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def _scored(comp, similarity: float) -> ScoredComp:
    return ScoredComp(
        comp=comp,
        similarity=similarity,
        subscores={},
        adjustments={},
        adjusted_price=comp.sale_price,
    )


def test_pipeline_invariants(make_subject, synthetic_store, hedonic_model):
    val = value_deterministic(make_subject(), synthetic_store, hedonic_model)
    assert val.comps, "expected comps to be found in the synthetic store"
    usable = [sc for sc in val.comps if sc.status == "included"]
    assert len(usable) >= config.MIN_COMPS_FOR_ESTIMATE  # a valuable case
    adjusted = [sc.adjusted_price for sc in usable]
    assert min(adjusted) <= val.point_estimate <= max(adjusted)  # estimate ∈ [min, max] of used
    assert val.conservative_value <= val.point_estimate  # conservative ≤ point
    assert val.range_low <= val.range_high  # range ordering
    assert val.mode == "deterministic"
    assert val.elapsed_ms >= 0


def test_confidence_factor_keys_are_canonical(make_subject, synthetic_store, hedonic_model):
    val = value_deterministic(make_subject(), synthetic_store, hedonic_model)
    assert set(val.confidence_factors) == {
        config.CF_COMP_COUNT,
        config.CF_MEAN_DISTANCE_KM,
        config.CF_DISPERSION,
        config.CF_MEDIAN_AGE_DAYS,
        config.CF_MEAN_ADJUSTMENT,
    }


def test_higher_dispersion_lowers_confidence():
    tight = {
        config.CF_COMP_COUNT: 12.0,
        config.CF_MEAN_DISTANCE_KM: 1.0,
        config.CF_DISPERSION: 0.05,
        config.CF_MEDIAN_AGE_DAYS: 60.0,
        config.CF_MEAN_ADJUSTMENT: 0.05,
    }
    wide = {**tight, config.CF_DISPERSION: 0.40}
    assert _ORDER[compute_confidence(tight)] > _ORDER[compute_confidence(wide)]


def test_large_mean_adjustment_caps_confidence():
    """A set fitted only by large average adjustments cannot be High, even if all else is tight."""
    tight = {
        config.CF_COMP_COUNT: 12.0,
        config.CF_MEAN_DISTANCE_KM: 1.0,
        config.CF_DISPERSION: 0.05,
        config.CF_MEDIAN_AGE_DAYS: 60.0,
        config.CF_MEAN_ADJUSTMENT: 0.05,
    }
    stretched = {**tight, config.CF_MEAN_ADJUSTMENT: 0.25}
    assert _ORDER[compute_confidence(tight)] > _ORDER[compute_confidence(stretched)]


def test_empty_scored_returns_low_confidence_zeroed(make_subject, hedonic_model):
    val = estimate_value(make_subject(), [], hedonic_model)
    assert val.confidence == "Low"
    assert val.point_estimate == 0 and val.comps == []


def test_below_similarity_floor_excluded(make_subject, make_comp, hedonic_model):
    """Comps under the similarity floor are excluded; too few left → insufficient (no value)."""
    subject = make_subject()
    comps = [_scored(make_comp(), 0.30) for _ in range(5)]  # all below the 0.45 floor
    val = estimate_value(subject, comps, hedonic_model)
    assert all(sc.status == "low_similarity" for sc in val.comps)
    assert val.point_estimate == 0 and val.confidence == "Low"  # insufficient comparable sales


def test_large_adjustment_excluded(make_subject, make_comp, hedonic_model):
    """A comp needing a >30% hedonic adjustment is excluded as not comparable enough."""
    subject = make_subject(sqft_living=2000)
    huge = make_comp(sqft_living=6000, sale_price=1_500_000, price_per_sqft=250.0)
    comps = [_scored(huge, 0.80) for _ in range(4)]  # high similarity, but far too large
    val = estimate_value(subject, comps, hedonic_model)
    assert all(sc.status == "large_adjustment" for sc in val.comps)


def test_percent_formatting_is_half_up_and_consistent():
    """Prose percentages round half-up (floor(x+0.5)), matching the frontend stat row exactly.

    The frontend formats the SAME source float with Math.round (also floor(x+0.5)), so a quoted
    percentage in the rationale can never disagree with the stat row, even at an exact x.5 tie
    where Python's banker's round would differ (e.g. 12.5 -> "13%", not "12%").
    """
    from app.agent.reason import _pct as reason_pct
    from app.core.estimate import _pct as estimate_pct

    for value, expected in [(0.125, "13%"), (0.375, "38%"), (0.625, "63%"), (0.1822, "18%")]:
        assert reason_pct(value) == expected
        assert estimate_pct(value) == expected


def test_exclusion_counts_tie_out(make_subject, make_comp, hedonic_model):
    """Excluded total in the rationale equals outliers + low_similarity + large_adjustment."""
    subject = make_subject(sqft_living=2000)
    good = [_scored(make_comp(sale_price=500_000), 0.85) for _ in range(3)]
    weak = [_scored(make_comp(), 0.30) for _ in range(2)]  # below the similarity floor
    huge = [_scored(make_comp(sqft_living=6000, sale_price=1_500_000, price_per_sqft=250.0), 0.80)]
    val = estimate_value(subject, good + weak + huge, hedonic_model)  # asserts internally too
    by = {"outlier": 0, "low_similarity": 0, "large_adjustment": 0, "included": 0}
    for sc in val.comps:
        by[sc.status] += 1
    excluded = sum(1 for sc in val.comps if sc.status != "included")
    assert excluded == by["outlier"] + by["low_similarity"] + by["large_adjustment"]
    assert by["low_similarity"] >= 2 and by["large_adjustment"] >= 1  # both reasons exercised


def test_excluded_comps_do_not_drive_estimate(make_subject, make_comp, hedonic_model):
    """With enough included comps, the estimate uses only them; weak comps stay visible."""
    subject = make_subject(sqft_living=2000)
    good = [_scored(make_comp(sale_price=500_000), 0.85) for _ in range(3)]
    weak = [_scored(make_comp(), 0.30)]  # low similarity → excluded but shown
    val = estimate_value(subject, good + weak, hedonic_model)
    included = [sc for sc in val.comps if sc.status == "included"]
    assert len(included) == 3
    assert any(sc.status == "low_similarity" for sc in val.comps)
    assert val.point_estimate > 0 and val.conservative_value <= val.point_estimate
