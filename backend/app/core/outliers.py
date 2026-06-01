"""$/sqft robust-band outlier flagging — Sam's #1 ask (BUILD_BRIEF §6, P1)."""

from __future__ import annotations

from app.schemas import ScoredComp


def flag_outliers(scored: list[ScoredComp]) -> list[ScoredComp]:
    """Flag comps outside the robust $/sqft band (and exclude them), with a reason. (P1)"""
    raise NotImplementedError("P1: flag_outliers")
