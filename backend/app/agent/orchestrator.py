"""Bounded agent loop with deterministic fallback (BUILD_BRIEF §7).

``value_deterministic`` is the pure pipeline (retrieve → score → flag → estimate) — it requires no
API key and is what the backtest and the agent's deterministic fallback both run. The Gemini-driven
``run_valuation`` (extraction + reasoning + one bounded re-query) wraps it in P3.
"""

from __future__ import annotations

import time

import pandas as pd

from app.core.estimate import estimate_value
from app.core.hedonic import HedonicModel
from app.core.outliers import flag_outliers
from app.core.retrieve import search_comps
from app.core.score import score_comps
from app.schemas import Subject, Valuation


def value_deterministic(subject: Subject, store: pd.DataFrame, hedonic: HedonicModel) -> Valuation:
    """Run the full deterministic valuation pipeline and stamp ``elapsed_ms``."""
    start = time.perf_counter()
    candidates = search_comps(subject, store)
    scored = score_comps(subject, candidates)
    scored = flag_outliers(scored)
    valuation = estimate_value(subject, scored, hedonic)
    valuation.elapsed_ms = int((time.perf_counter() - start) * 1000)
    return valuation


def run_valuation(subject: Subject) -> Valuation:
    """Orchestrate retrieve → score → flag → estimate, then (optionally) LLM reasoning. (P3)"""
    raise NotImplementedError("P3: agent orchestration (extract + reason + bounded re-query)")
