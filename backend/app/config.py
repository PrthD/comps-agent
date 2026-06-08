"""Central configuration for the comps valuation agent (BUILD_BRIEF §9).

Every tunable number the deterministic core relies on — scoring weights, retrieval radii and
time windows, the outlier band, confidence thresholds, the conservative-margin coefficients —
lives here, never hardcoded inside logic. Defaults follow §6 and will be validated/tuned against
the P2 backtest. Secrets and deployment-specific values come from the environment via a local
``.env`` (see ``.env.example``); nothing secret is ever committed.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------------------
# Data window — the bundled King County store spans 2014-05..2015-05. Any path that builds
# a Subject without an explicit as-of date (the extraction path) must default INSIDE this
# window, or the recency tiers match nothing and every valuation comes back empty. The
# frontend form uses the same 2015-05-01 default; all input paths share this one value.
# --------------------------------------------------------------------------------------
DEFAULT_AS_OF_DATE: date = date(2015, 5, 1)
# Inclusive bounds of the dataset window. An as-of date outside this range can find no comps; the
# empty-result rationale uses it to say "outside the dataset window" vs "none near this location".
DATA_WINDOW_START: date = date(2014, 5, 1)
DATA_WINDOW_END: date = date(2015, 5, 31)

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
# Canonical dict keys — single source of truth so config and code can never drift.
# SUBSCORE_* keys double as SCORING_WEIGHTS keys AND ScoredComp.subscores keys; CF_* keys name
# the metrics in Valuation.confidence_factors; CT_* keys key CONFIDENCE_THRESHOLDS. Code imports
# these constants instead of re-typing the metric-name strings.
# --------------------------------------------------------------------------------------
SUBSCORE_DISTANCE = "distance"
SUBSCORE_LIVING_AREA = "living_area"
SUBSCORE_RECENCY = "recency"
SUBSCORE_GRADE_CONDITION = "grade_condition"
SUBSCORE_AGE = "age"
SUBSCORE_BED_BATH = "bed_bath"

CF_COMP_COUNT = "comp_count"
CF_MEAN_DISTANCE_KM = "mean_distance_km"
CF_DISPERSION = "dispersion"
CF_MEDIAN_AGE_DAYS = "median_age_days"
CF_MEAN_ADJUSTMENT = "mean_adjustment"  # mean |adjusted - sale| / sale over INCLUDED comps

CT_MIN_COMPS = "min_comps"
CT_MAX_MEAN_DISTANCE_KM = "max_mean_distance_km"
CT_MAX_DISPERSION = "max_dispersion"
CT_MAX_MEDIAN_AGE_DAYS = "max_median_age_days"
CT_MAX_MEAN_ADJUSTMENT = "max_mean_adjustment"

# Internal unit convention: recency/age are handled in DAYS throughout the core; only the
# conservative staleness term converts DAYS → YEARS (at that edge) using DAYS_PER_YEAR.
DAYS_PER_YEAR: float = 365.25

# --------------------------------------------------------------------------------------
# Scoring weights (§6) — weighted sum of normalized 0–1 subscores. Must sum to 1.0.
# --------------------------------------------------------------------------------------
SCORING_WEIGHTS: dict[str, float] = {
    SUBSCORE_DISTANCE: 0.30,
    SUBSCORE_LIVING_AREA: 0.20,
    SUBSCORE_RECENCY: 0.15,
    SUBSCORE_GRADE_CONDITION: 0.15,
    SUBSCORE_AGE: 0.10,
    SUBSCORE_BED_BATH: 0.10,
}
assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-9, "SCORING_WEIGHTS must sum to 1.0"

# --------------------------------------------------------------------------------------
# Retrieval (§6) — widen progressively until enough candidates; target 10–20.
# Each tier is (radius_km, time_window_days).
# --------------------------------------------------------------------------------------
RETRIEVAL_TIERS: list[tuple[float, int]] = [(2.0, 180), (5.0, 365), (10.0, 540)]
TARGET_COMPS_MIN: int = 10
TARGET_COMPS_MAX: int = 20

# Subscore normalization scales — each subscore decays to 0 at its scale. Distance/recency
# reuse the widest retrieval tier so a candidate at the search boundary contributes ~0.
SUBSCORE_SCALES: dict[str, float] = {
    "distance_km": RETRIEVAL_TIERS[-1][0],  # widest radius (km)
    "recency_days": float(RETRIEVAL_TIERS[-1][1]),  # widest time window (days)
    "living_area_frac": 0.50,  # |Δsqft| / subject_sqft at which area similarity hits 0
    "grade": 4.0,  # KC grade points
    "condition": 4.0,  # condition 1–5 → max spread 4
    "age_years": 30.0,  # |Δyear_built| in years
    "beds": 2.0,
    "baths": 2.0,
}

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
# Log-transform these features → elasticities (scale-free), so raw size scales don't swamp the
# small-integer features (grade/beds). log(price) ~ log(sqft_living) gives a $/sqft elasticity.
HEDONIC_LOG_FEATURES: list[str] = ["sqft_living"]
HEDONIC_USE_ZIP: bool = True  # add zip dummies to the log(price) regression
# Expected economic sign of each feature's effect on price. Adjustment coefficients are clamped to
# this half-line so we never apply a backwards adjustment (e.g. paying MORE for FEWER beds); a
# wrong-signed coefficient is clamped to 0 (no adjustment) and surfaced — never applied silently.
HEDONIC_EXPECTED_SIGN: dict[str, int] = {
    "sqft_living": 1,
    "beds": 1,
    "baths": 1,
    "grade": 1,
    "age": -1,  # older → not more valuable, all else equal
}
HEDONIC_CLAMP_SIGNS: bool = True
# Sanity band for the model's implied marginal $/sqft, asserted before trusting the backtest.
HEDONIC_IMPLIED_PPSF_RANGE: tuple[float, float] = (150.0, 400.0)
TIME_INDEX_FREQ: str = "M"  # monthly $/sqft index for the time adjustment

# --------------------------------------------------------------------------------------
# Conservative anchor (§6) — headline = min(point · (1 − margin), P25).
# margin scales with dispersion, mean distance, and staleness, then is capped.
# --------------------------------------------------------------------------------------
CONSERVATIVE_BASE_MARGIN: float = 0.02
CONSERVATIVE_DISPERSION_COEF: float = 0.50  # × coefficient-of-variation of adjusted prices
CONSERVATIVE_DISTANCE_COEF: float = 0.01  # × mean comp distance (km)
CONSERVATIVE_STALENESS_COEF: float = 0.02  # × mean comp age in YEARS (days / DAYS_PER_YEAR at edge)
# × mean adjustment fraction over the included comps: a set stretched to fit (large average
# hedonic adjustment) is less trustworthy, so the defensible value drops further below the point.
CONSERVATIVE_ADJUSTMENT_COEF: float = 0.50
CONSERVATIVE_MARGIN_CAP: float = 0.25  # never discount the point estimate by more than 25%

# --------------------------------------------------------------------------------------
# Comp-quality gate (P5 review) — exclude indefensible comps from the estimate. Excluded comps
# stay visible in the table with a status, but never drive the point/range/conservative figures.
# --------------------------------------------------------------------------------------
MAX_ADJUSTMENT_FRACTION: float = 0.30  # exclude if |adjusted - sale| / sale exceeds this
MIN_SIMILARITY_FOR_ESTIMATE: float = 0.45  # exclude comps scoring below this similarity
MIN_COMPS_FOR_ESTIMATE: int = 3  # fewer included than this → "insufficient comparable sales"

# --------------------------------------------------------------------------------------
# Confidence thresholds (§6) — High if every High bound is met; else Medium if every Medium
# bound is met; else Low. ``dispersion`` = coefficient of variation of adjusted prices.
# --------------------------------------------------------------------------------------
CONFIDENCE_THRESHOLDS: dict[str, dict[str, float]] = {
    "High": {
        CT_MIN_COMPS: 8,
        CT_MAX_MEAN_DISTANCE_KM: 3.0,
        CT_MAX_DISPERSION: 0.12,
        CT_MAX_MEDIAN_AGE_DAYS: 180,
        CT_MAX_MEAN_ADJUSTMENT: 0.10,  # a heavily-adjusted comp set cannot be High confidence
    },
    "Medium": {
        CT_MIN_COMPS: 5,
        CT_MAX_MEAN_DISTANCE_KM: 6.0,
        CT_MAX_DISPERSION: 0.20,
        CT_MAX_MEDIAN_AGE_DAYS: 365,
        CT_MAX_MEAN_ADJUSTMENT: 0.18,  # above this the set is stretched to fit → Low
    },
}
