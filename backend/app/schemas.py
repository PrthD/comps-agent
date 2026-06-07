"""Pydantic v2 data contracts for the comps valuation agent (BUILD_BRIEF §5).

These models are the trust boundary's type system: the LLM fills a ``Subject`` (with per-field
confidence), while every numeric field on ``ScoredComp``/``Valuation`` is produced by the
deterministic core. ``PropertyFeatures`` holds the structural attributes shared by a subject
property and a comparable sale, so a ``Comp`` never carries subject-only metadata such as
``as_of_date`` or extraction confidence.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class PropertyFeatures(BaseModel):
    """Structural attributes shared by a subject property and a comparable sale."""

    property_type: str  # detached / townhouse / condo (mapped from grade/floors if needed)
    beds: float
    baths: float
    sqft_living: int = Field(gt=0)
    sqft_lot: int | None = Field(default=None, gt=0)
    year_built: int | None = None
    condition: int | None = Field(default=None, ge=1, le=5)  # KC condition, 1–5
    grade: int | None = None  # KC construction grade
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Subject(PropertyFeatures):
    """The property being valued, from a document/form (via the LLM) or entered directly."""

    as_of_date: date = Field(default_factory=date.today)  # backtest = the held-out sale date
    # Extraction metadata — set by the agent's extract step; None for hand-entered subjects:
    field_confidence: dict[str, float] | None = None
    needs_review: list[str] | None = None


# Fields the deterministic math actually needs to value a subject. year_built/grade/condition are
# intentionally absent — the core treats them as nullable (neutral subscores, no adjustment).
REQUIRED_FIELDS: tuple[str, ...] = ("sqft_living", "beds", "baths", "lat", "lng")


def required_fields_missing(subject: Subject) -> list[str]:
    """Single source of truth for the gate: which required fields are absent or sentinel.

    Detects the placeholders the extract path emits when it cannot read a field (it never fabricates
    a value — it flags one): ``sqft_living == 1``, ``lat == lng == 0.0`` (the coordinate
    placeholder), and ``beds``/``baths == 0.0``. Anything still in ``subject.needs_review`` that the
    math needs also counts. Returned sorted + de-duplicated; empty list means "ready to value".
    """
    missing: set[str] = set()
    if subject.sqft_living <= 1:  # 1 is the extractor's placeholder; no real home is ≤1 sqft
        missing.add("sqft_living")
    if not subject.beds:  # 0.0 placeholder (or genuinely 0 → still not valuable for the math)
        missing.add("beds")
    if not subject.baths:
        missing.add("baths")
    if subject.lat == 0.0 and subject.lng == 0.0:  # the coordinate placeholder (never invented)
        missing.add("lat")
        missing.add("lng")
    for field in subject.needs_review or []:
        if field in REQUIRED_FIELDS:
            missing.add(field)
    return sorted(missing)


class Comp(PropertyFeatures):
    """A real comparable sale row retrieved from the comps store."""

    sale_price: int = Field(gt=0)
    sale_date: date
    price_per_sqft: float = Field(gt=0)
    distance_km: float = Field(ge=0)  # haversine distance from the subject


class ScoredComp(BaseModel):
    """A comp after similarity scoring, hedonic adjustment, and outlier flagging."""

    comp: Comp
    similarity: float = Field(ge=0, le=1)
    subscores: dict[str, float]  # distance, recency, area, bed_bath, age, grade — each 0–1
    adjustments: dict[str, float]  # line-item $ deltas applied to sale_price
    adjusted_price: int
    flagged: bool = False
    flag_reason: str | None = None


class Valuation(BaseModel):
    """The full valuation result. ``conservative_value`` is the lender-facing headline."""

    conservative_value: int  # headline: the defensible floor a lender should size against
    point_estimate: int
    range_low: int
    range_high: int
    confidence: Literal["High", "Medium", "Low"]
    confidence_factors: dict[str, float]  # comp_count, mean_distance, recency, dispersion, ...
    comps: list[ScoredComp]  # 10–20; flagged comps included and marked
    rationale: str  # plain-English, written by the LLM (or a template in deterministic mode)
    mode: Literal["agent", "deterministic"]
    elapsed_ms: int
