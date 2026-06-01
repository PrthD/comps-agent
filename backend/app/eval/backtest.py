"""Leave-one-out backtest over a random holdout; lock a baseline MdAPE (BUILD_BRIEF §12, P2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BacktestReport:
    """MdAPE, % within 5/10/20%, coverage (≥10 comps found), and per-subject records. (P2)"""


def run_backtest(n: int = 400, seed: int | None = None) -> BacktestReport:
    """Hide each held-out subject's price, value it from prior comps, compare to actual. (P2)"""
    raise NotImplementedError("P2: run_backtest")
