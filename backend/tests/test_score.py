"""Scoring monotonicity and key-drift guard."""

from __future__ import annotations

from datetime import date

from app import config
from app.core.score import score_comps


def _similarity_by(comps, key, subject):
    return {key(sc.comp): sc.similarity for sc in score_comps(subject, comps)}


def test_closer_comp_scores_higher(make_subject, make_comp):
    subject = make_subject()
    near, far = make_comp(distance_km=0.2), make_comp(distance_km=8.0)
    sims = _similarity_by([near, far], lambda c: c.distance_km, subject)
    assert sims[0.2] > sims[8.0]


def test_more_recent_comp_scores_higher(make_subject, make_comp):
    subject = make_subject(as_of_date=date(2015, 6, 1))
    recent = make_comp(sale_date=date(2015, 5, 1))
    stale = make_comp(sale_date=date(2014, 6, 1))
    sims = _similarity_by([recent, stale], lambda c: c.sale_date, subject)
    assert sims[date(2015, 5, 1)] > sims[date(2014, 6, 1)]


def test_more_similar_size_scores_higher(make_subject, make_comp):
    subject = make_subject(sqft_living=2000)
    same, bigger = make_comp(sqft_living=2000), make_comp(sqft_living=3500)
    sims = _similarity_by([same, bigger], lambda c: c.sqft_living, subject)
    assert sims[2000] > sims[3500]


def test_subscore_keys_match_weight_keys(make_subject, make_comp):
    scored = score_comps(make_subject(), [make_comp()])
    assert set(scored[0].subscores) == set(config.SCORING_WEIGHTS)
