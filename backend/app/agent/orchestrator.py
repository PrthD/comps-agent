"""Bounded agent loop with deterministic fallback (BUILD_BRIEF §7, P3).

Hard cap of one re-query. If ``GEMINI_API_KEY`` is absent or the model errors / 429s, fall back
to deterministic mode (template rationale). The app never just breaks.
"""

from __future__ import annotations

from app.schemas import Subject, Valuation


def run_valuation(subject: Subject) -> Valuation:
    """Orchestrate retrieve → score → flag → estimate, then (optionally) LLM reasoning. (P3)"""
    raise NotImplementedError("P3: orchestrator")
