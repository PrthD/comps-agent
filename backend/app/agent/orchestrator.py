"""Bounded agent loop with deterministic fallback.

``value_deterministic`` is the pure pipeline (retrieve → score → flag → estimate), it needs no API
key and is what both the backtest and the agent's fallback run. ``run_valuation`` wraps it with the
Gemini layer: an optional one-shot, *deterministic* re-query (widen retrieval when the result is
thin/low-confidence, NOT an LLM round-trip) and a single reasoning call for the prose rationale.
The trust boundary is absolute: the LLM only writes the rationale; every number comes from the core.

Failure modes are first-class: with no key, or on any Gemini error/429, ``run_valuation`` returns a
complete ``Valuation`` in ``mode="deterministic"`` with the templated rationale, it never breaks.
"""

from __future__ import annotations

import time

import pandas as pd

from app import config
from app.agent.extract import extract_subject
from app.agent.reason import reason_over_valuation
from app.core.data import load_comps
from app.core.estimate import estimate_value
from app.core.hedonic import HedonicModel, fit_hedonic
from app.core.outliers import flag_outliers
from app.core.retrieve import _row_to_comp, haversine_km, search_comps
from app.core.score import score_comps
from app.schemas import Subject, Valuation

# Loaded once (lazily, then cached), the store + hedonic fit are reused across every valuation.
_STORE: pd.DataFrame | None = None
_HEDONIC: HedonicModel | None = None


_CONFIDENCE_RANK = {"Low": 0, "Medium": 1, "High": 2}

# Fields the math cannot run without. Optional on the Subject wire, so guard before valuing.
_VALUE_CRITICAL = ("sqft_living", "beds", "baths", "lat", "lng")


def _require_valuable(subject: Subject) -> None:
    """Fail fast with a clear error if a value-critical field is None (gate the subject first).

    ``/api/value`` enforces the completeness gate up front, so a valued subject always has these.
    This guards direct callers from silent failures, e.g. None coords → NaN haversine distances.
    """
    missing = [f for f in _VALUE_CRITICAL if getattr(subject, f) is None]
    if missing:
        raise ValueError(
            f"cannot value subject: {missing} not provided (None); "
            "run the completeness gate (required_fields_missing) before valuing"
        )


def init() -> tuple[pd.DataFrame, HedonicModel]:
    """Load the comps store and fit the hedonic model once; cache for the process lifetime."""
    global _STORE, _HEDONIC
    if _STORE is None or _HEDONIC is None:
        store = load_comps()
        _STORE, _HEDONIC = store, fit_hedonic(store)
    return _STORE, _HEDONIC


def store_size() -> int:
    """Number of comps currently loaded (0 if ``init`` has not run), for the health endpoint."""
    return 0 if _STORE is None else int(len(_STORE))


def value_deterministic(subject: Subject, store: pd.DataFrame, hedonic: HedonicModel) -> Valuation:
    """Run the full deterministic valuation pipeline and stamp ``elapsed_ms``."""
    _require_valuable(subject)  # guard: None coords/size would silently produce NaN/garbage
    start = time.perf_counter()
    candidates = search_comps(subject, store)
    scored = score_comps(subject, candidates)
    scored = flag_outliers(scored)
    valuation = estimate_value(subject, scored, hedonic)
    valuation.elapsed_ms = int((time.perf_counter() - start) * 1000)
    return valuation


def _has_value(valuation: Valuation) -> bool:
    """A real valuation, not the empty / insufficient-comps state (which zeroes every figure)."""
    return valuation.point_estimate > 0


def _usable_count(valuation: Valuation) -> int:
    """Comps that actually drove the estimate (non-flagged, or all of them if all were flagged)."""
    non_flagged = sum(1 for sc in valuation.comps if not sc.flagged)
    return non_flagged or len(valuation.comps)


def _should_requery(valuation: Valuation) -> bool:
    """Deterministic trigger (no LLM): widen once when the result is thin or low-confidence."""
    return (
        not valuation.comps
        or len(valuation.comps) < config.TARGET_COMPS_MIN
        or valuation.confidence == "Low"
    )


def _widened_candidates(subject: Subject, store: pd.DataFrame) -> list:
    """Same tiers + leakage guard as ``search_comps`` but with the property-type filter relaxed.

    Mirrors the core retrieval (reusing its haversine + row builder so candidates are identical in
    shape) and only drops the type compatibility test. On the near-single-type King County data this
    is typically inert; it earns its keep in sparser, multi-type markets.
    """
    as_of = pd.Timestamp(subject.as_of_date)
    sale_dates = pd.to_datetime(store["sale_date"])
    base = store[sale_dates < as_of].copy()  # leakage guard preserved (strict <)
    if base.empty:
        return []
    base["distance_km"] = haversine_km(
        subject.lat, subject.lng, base["lat"].to_numpy(), base["lng"].to_numpy()
    )
    base["age_days"] = (as_of - pd.to_datetime(base["sale_date"])).dt.days
    chosen = base.iloc[0:0]
    for radius_km, window_days in config.RETRIEVAL_TIERS:
        chosen = base[(base["distance_km"] <= radius_km) & (base["age_days"] <= window_days)]
        if len(chosen) >= config.TARGET_COMPS_MIN:
            break
    return [_row_to_comp(rec) for rec in chosen.to_dict("records")]


def _adopt_widened(current: Valuation, widened: Valuation) -> bool:
    """Adopt the widened (type-relaxed) result only if it improves coverage WITHOUT worse comps.

    Gates on confidence, not just raw count: the widened set must reach the comp floor AND be no
    less confident than the current one, and must genuinely improve on it (more comps OR higher
    confidence). This keeps it inert on King County (same single-type set → no improvement) and,
    elsewhere, stops us trading good comps for more-but-worse ones.
    """
    widened_n = _usable_count(widened)
    if widened_n < config.TARGET_COMPS_MIN:
        return False
    if _CONFIDENCE_RANK[widened.confidence] < _CONFIDENCE_RANK[current.confidence]:
        return False
    return (
        widened_n > _usable_count(current)
        or _CONFIDENCE_RANK[widened.confidence] > _CONFIDENCE_RANK[current.confidence]
    )


def _requery(subject: Subject, store: pd.DataFrame, hedonic: HedonicModel) -> Valuation | None:
    """One bounded widening pass: relax type, re-score/flag/estimate. ``None`` if nothing new."""
    candidates = _widened_candidates(subject, store)
    if not candidates:
        return None
    scored = flag_outliers(score_comps(subject, candidates))
    valuation = estimate_value(subject, scored, hedonic)
    # Defense-in-depth: the widened pass must still honor the leakage rule.
    assert all(sc.comp.sale_date < subject.as_of_date for sc in valuation.comps)
    return valuation


def _value_with_requery(subject: Subject, store: pd.DataFrame, hedonic: HedonicModel) -> Valuation:
    """Deterministic core + the one bounded re-query. No LLM; identical across both phases.

    Re-running this is safe and reproducible (pure functions, seeded), so the rationale phase can
    re-derive the very same numbers the value phase already returned.
    """
    valuation = value_deterministic(subject, store, hedonic)
    if _should_requery(valuation):
        widened = _requery(subject, store, hedonic)
        if widened is not None and _adopt_widened(valuation, widened):
            valuation = widened
    return valuation


def value_only(
    subject: Subject,
    store: pd.DataFrame | None = None,
    hedonic: HedonicModel | None = None,
) -> Valuation:
    """Phase 1 of the progressive flow: the fast (~sub-second) deterministic valuation, no LLM.

    The UI renders this immediately (headline, stat row, map, comp table) and fetches the prose
    separately via ``generate_rationale``. ``elapsed_ms`` is therefore the actual compute time the
    user waits at "Value", ``mode`` is "deterministic", and ``rationale`` is the estimate template.
    """
    start = time.perf_counter()
    if store is None or hedonic is None:
        store, hedonic = init()
    valuation = _value_with_requery(subject, store, hedonic)
    valuation.mode = "deterministic"
    valuation.elapsed_ms = int((time.perf_counter() - start) * 1000)
    return valuation


def generate_rationale(
    subject: Subject,
    store: pd.DataFrame | None = None,
    hedonic: HedonicModel | None = None,
) -> tuple[str, str]:
    """Phase 2: re-derive the deterministic valuation and write its rationale. Returns text + mode.

    The single LLM call of the value flow. Skipped for the empty / insufficient-comps state (zeroed
    figures, nothing to reason about), so a confused model never emits meta-commentary over a $0
    payload. Falls back to the deterministic template (mode "deterministic") with no key, on that
    empty state, or on any reasoning failure (429, timeout, empty, or meta-commentary output), so
    raw model text or an API error never reaches the user.
    """
    if store is None or hedonic is None:
        store, hedonic = init()
    valuation = _value_with_requery(subject, store, hedonic)
    if config.MODEL_AVAILABLE and _has_value(valuation):
        try:
            return reason_over_valuation(subject, valuation), "agent"
        except Exception:
            return valuation.rationale, "deterministic"
    return valuation.rationale, "deterministic"


def run_valuation(
    subject: Subject,
    store: pd.DataFrame | None = None,
    hedonic: HedonicModel | None = None,
) -> Valuation:
    """Full one-shot valuation: deterministic core → bounded re-query → LLM rationale, in one call.

    Retained for the document path (``value_document``) and the backtest. The API uses the split
    ``value_only`` + ``generate_rationale`` for progressive rendering; this keeps the synchronous
    path intact. The only LLM call here is the reasoning step (extraction happens upstream), ≤2.
    """
    start = time.perf_counter()
    if store is None or hedonic is None:
        store, hedonic = init()

    valuation = _value_with_requery(subject, store, hedonic)

    mode = "deterministic"
    if config.MODEL_AVAILABLE and _has_value(valuation):
        try:
            valuation.rationale = reason_over_valuation(subject, valuation)
            mode = "agent"
        except Exception:
            mode = "deterministic"  # keep the templated rationale from estimate_value
    valuation.mode = mode
    valuation.elapsed_ms = int((time.perf_counter() - start) * 1000)
    return valuation


def value_document(
    content: bytes | str,
    mime_type: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    store: pd.DataFrame | None = None,
    hedonic: HedonicModel | None = None,
) -> Valuation:
    """Document/text entrypoint: extract a ``Subject`` (LLM call #1), patch coords, then value it.

    Coordinates are never read from the document; the caller passes ``lat``/``lng`` (e.g. from a map
    pin or geocoded address). Total LLM calls: extraction + reasoning = ≤2.
    """
    subject = extract_subject(content, mime_type)
    if lat is not None and lng is not None:
        subject.lat, subject.lng = float(lat), float(lng)
        if subject.needs_review:
            subject.needs_review = [f for f in subject.needs_review if f not in ("lat", "lng")]
    return run_valuation(subject, store=store, hedonic=hedonic)
