"""Weighted-similarity scoring of candidate comps (BUILD_BRIEF §6, P1)."""

from __future__ import annotations

from app.schemas import Comp, ScoredComp, Subject


def score_comps(subject: Subject, comps: list[Comp]) -> list[ScoredComp]:
    """Score each comp 0–1 via weighted subscores (config.SCORING_WEIGHTS); rank desc. (P1)"""
    raise NotImplementedError("P1: score_comps")
