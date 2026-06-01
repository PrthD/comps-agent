"""Central configuration for the comps valuation agent (BUILD_BRIEF §9).

Every tunable number the deterministic core relies on — scoring weights, retrieval radii and
time windows, the outlier band, confidence thresholds, the conservative-margin coefficients —
lives here, never hardcoded inside logic. Defaults follow §6 and will be validated/tuned against
the P2 backtest. Secrets and deployment-specific values come from the environment via a local
``.env`` (see ``.env.example``); nothing secret is ever committed.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------------------
# Paths & determinism (absolute + CWD-independent; single source of truth for the parquet)
# --------------------------------------------------------------------------------------
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent  # .../backend
DATA_PATH: Path = BACKEND_DIR / "data" / "kc_sales.parquet"  # bundled, read-only at runtime
SEED: int = 42  # seed everything; the deterministic core is pure and reproducible

# --------------------------------------------------------------------------------------
# Environment / secrets (never commit real values; see .env.example)
# --------------------------------------------------------------------------------------
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or None
MODEL_AVAILABLE: bool = bool(GEMINI_API_KEY)  # drives agent vs. deterministic fallback

ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]

# Gemini model IDs (env-overridable so P3 can move to Gemini 3 Flash without code changes).
GEMINI_REASONING_MODEL: str = os.getenv("GEMINI_REASONING_MODEL", "gemini-2.5-flash")
GEMINI_EXTRACTION_MODEL: str = os.getenv("GEMINI_EXTRACTION_MODEL", "gemini-2.5-flash-lite")

# --------------------------------------------------------------------------------------
# Scoring weights (§6) — weighted sum of normalized 0–1 subscores. Must sum to 1.0.
# --------------------------------------------------------------------------------------
SCORING_WEIGHTS: dict[str, float] = {
    "distance": 0.30,
    "living_area": 0.20,
    "recency": 0.15,
    "grade_condition": 0.15,
    "age": 0.10,
    "bed_bath": 0.10,
}
assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-9, "SCORING_WEIGHTS must sum to 1.0"

# --------------------------------------------------------------------------------------
# Retrieval (§6) — widen progressively until enough candidates; target 10–20.
# Each tier is (radius_km, time_window_days).
# --------------------------------------------------------------------------------------
RETRIEVAL_TIERS: list[tuple[float, int]] = [(2.0, 180), (5.0, 365), (10.0, 540)]
TARGET_COMPS_MIN: int = 10
TARGET_COMPS_MAX: int = 20

# --------------------------------------------------------------------------------------
# Outlier flagging (§6) — Sam's #1 ask. Robust $/sqft band on the candidate set.
# --------------------------------------------------------------------------------------
OUTLIER_METHOD: str = "mad"  # "mad" (median ± k·MAD) or "iqr" (Q1−m·IQR / Q3+m·IQR)
OUTLIER_K_MAD: float = 3.0
OUTLIER_IQR_MULT: float = 1.5

# --------------------------------------------------------------------------------------
# Hedonic adjustment + time index (§6)
# --------------------------------------------------------------------------------------
HEDONIC_FEATURES: list[str] = ["sqft_living", "beds", "baths", "grade", "age"]
HEDONIC_USE_ZIP: bool = True  # add zip dummies to the log(price) regression
TIME_INDEX_FREQ: str = "M"  # monthly $/sqft index for the time adjustment

# --------------------------------------------------------------------------------------
# Conservative anchor (§6) — headline = min(point · (1 − margin), P25).
# margin scales with dispersion, mean distance, and staleness, then is capped.
# --------------------------------------------------------------------------------------
CONSERVATIVE_BASE_MARGIN: float = 0.02
CONSERVATIVE_DISPERSION_COEF: float = 0.50  # × coefficient-of-variation of adjusted prices
CONSERVATIVE_DISTANCE_COEF: float = 0.01  # × mean comp distance (km)
CONSERVATIVE_STALENESS_COEF: float = 0.02  # × mean comp age (years before as_of_date)
CONSERVATIVE_MARGIN_CAP: float = 0.15  # never discount the point estimate by more than 15%

# --------------------------------------------------------------------------------------
# Confidence thresholds (§6) — High if every High bound is met; else Medium if every Medium
# bound is met; else Low. ``dispersion`` = coefficient of variation of adjusted prices.
# --------------------------------------------------------------------------------------
CONFIDENCE_THRESHOLDS: dict[str, dict[str, float]] = {
    "High": {
        "min_comps": 8,
        "max_mean_distance_km": 3.0,
        "max_dispersion": 0.12,
        "max_median_age_days": 180,
    },
    "Medium": {
        "min_comps": 5,
        "max_mean_distance_km": 6.0,
        "max_dispersion": 0.20,
        "max_median_age_days": 365,
    },
}
