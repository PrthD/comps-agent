"""Gemini Flash reasoning: flag sanity-check, rationale, confidence call (BUILD_BRIEF §7, P3)."""

from __future__ import annotations

from app.schemas import Subject, Valuation


def reason_over_valuation(subject: Subject, valuation: Valuation) -> Valuation:
    """Return the valuation with an LLM rationale + confidence call; may request one widen. (P3)"""
    raise NotImplementedError("P3: reason_over_valuation (Gemini Flash)")
