"""Estimate invariants and confidence behavior (BUILD_BRIEF §6/§11)."""

from __future__ import annotations

from app import config
from app.agent.orchestrator import value_deterministic
from app.core.estimate import compute_confidence

_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def test_pipeline_invariants(make_subject, synthetic_store, hedonic_model):
    val = value_deterministic(make_subject(), synthetic_store, hedonic_model)
    assert val.comps, "expected comps to be found in the synthetic store"
    usable = [sc for sc in val.comps if not sc.flagged]
    adjusted = [sc.adjusted_price for sc in usable]
    assert min(adjusted) <= val.point_estimate <= max(adjusted)  # estimate ∈ [min, max]
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
    }


def test_higher_dispersion_lowers_confidence():
    tight = {
        config.CF_COMP_COUNT: 12.0,
        config.CF_MEAN_DISTANCE_KM: 1.0,
        config.CF_DISPERSION: 0.05,
        config.CF_MEDIAN_AGE_DAYS: 60.0,
    }
    wide = {**tight, config.CF_DISPERSION: 0.40}
    assert _ORDER[compute_confidence(tight)] > _ORDER[compute_confidence(wide)]


def test_empty_scored_returns_low_confidence_zeroed(make_subject, hedonic_model):
    from app.core.estimate import estimate_value

    val = estimate_value(make_subject(), [], hedonic_model)
    assert val.confidence == "Low"
    assert val.point_estimate == 0 and val.comps == []
