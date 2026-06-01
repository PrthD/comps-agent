"""Adjustment grid → point estimate, range, conservative anchor, confidence (BUILD_BRIEF §6, P1)."""

from __future__ import annotations

from app.core.hedonic import HedonicModel
from app.schemas import ScoredComp, Subject, Valuation


def estimate_value(
    subject: Subject,
    scored: list[ScoredComp],
    hedonic: HedonicModel,
) -> Valuation:
    """Similarity-weighted estimate, [P25,P75] range, conservative headline, confidence. (P1)"""
    raise NotImplementedError("P1: estimate_value")
