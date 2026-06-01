"""Backtest regression guard (BUILD_BRIEF §11/§12).

One eval test: on a fixed seed/sample the MdAPE stays in the honest band and coverage stays high.
Runs the real leave-one-out pipeline on the bundled parquet (no LLM, no network).
"""

from __future__ import annotations

from app import config
from app.eval.backtest import run_backtest


def test_backtest_mdape_and_coverage_regression():
    report = run_backtest(n=60, seed=config.SEED)
    assert report.n_valued >= 50  # nearly every sampled subject is valued
    assert report.coverage_min1 >= 0.9  # comps found for almost everyone
    assert report.mdape < 0.16  # honest 8–15% band, with headroom over the ~10.9% baseline
