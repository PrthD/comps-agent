"""$/sqft outlier flagging — Sam's #1 ask (BUILD_BRIEF §6/§11)."""

from __future__ import annotations

from app.core.outliers import flag_outliers
from app.schemas import ScoredComp


def _scored(make_comp, ppsf: float) -> ScoredComp:
    price = int(ppsf * 2000)
    comp = make_comp(price_per_sqft=float(ppsf), sale_price=price)
    return ScoredComp(comp=comp, similarity=0.5, subscores={}, adjustments={}, adjusted_price=price)


def test_obvious_outlier_is_flagged_with_reason(make_comp):
    scored = [_scored(make_comp, v) for v in (240, 250, 245, 255, 248, 800)]
    flag_outliers(scored)
    outlier = next(sc for sc in scored if sc.comp.price_per_sqft == 800)
    assert outlier.flagged is True
    assert outlier.flag_reason and "median" in outlier.flag_reason
    assert all(not sc.flagged for sc in scored if sc.comp.price_per_sqft < 300)


def test_uniform_ppsf_flags_nothing(make_comp):
    scored = [_scored(make_comp, 250.0) for _ in range(6)]
    flag_outliers(scored)
    assert all(not sc.flagged for sc in scored)


def test_too_few_comps_flags_nothing(make_comp):
    scored = [_scored(make_comp, v) for v in (250, 900)]  # below MIN_COMPS_FOR_BAND
    flag_outliers(scored)
    assert all(not sc.flagged for sc in scored)
