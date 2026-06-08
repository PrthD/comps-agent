"""$/sqft robust-band outlier flagging, Sam's #1 ask.

Flags candidates whose price-per-sqft falls outside a robust band on the candidate set (median ±
k·MAD by default, or IQR fences), marks them with a human-readable reason, and leaves them in the
list so the UI can show them, but ``estimate.py`` excludes flagged comps from the number.
"""

from __future__ import annotations

import numpy as np

from app import config
from app.schemas import ScoredComp

# Below this many candidates a robust band is meaningless, so we flag nothing.
MIN_COMPS_FOR_BAND = 4


def _band(values: np.ndarray) -> tuple[float, float, float]:
    """Return (median, low, high) for the configured robust method."""
    median = float(np.median(values))
    if config.OUTLIER_METHOD == "iqr":
        q1, q3 = (float(x) for x in np.percentile(values, [25, 75]))
        iqr = q3 - q1
        return median, q1 - config.OUTLIER_IQR_MULT * iqr, q3 + config.OUTLIER_IQR_MULT * iqr
    mad = float(np.median(np.abs(values - median)))  # median absolute deviation
    spread = config.OUTLIER_K_MAD * mad
    return median, median - spread, median + spread


def flag_outliers(scored: list[ScoredComp]) -> list[ScoredComp]:
    """Mark comps outside the robust $/sqft band with a reason; order is unchanged."""
    if len(scored) < MIN_COMPS_FOR_BAND:
        return scored
    values = np.array([sc.comp.price_per_sqft for sc in scored], dtype=float)
    median, low, high = _band(values)
    if not np.isfinite([low, high]).all() or high <= low:
        return scored  # degenerate band (e.g. MAD == 0): flag nothing
    for sc in scored:
        pps = sc.comp.price_per_sqft
        if pps < low or pps > high:
            ratio = pps / median if median else float("nan")
            sc.flagged = True
            sc.flag_reason = (
                f"$/sqft of ${pps:,.0f} is {ratio:.1f}x the neighborhood median of "
                f"${median:,.0f}, outside the robust band [${low:,.0f}, ${high:,.0f}]"
            )
    return scored
