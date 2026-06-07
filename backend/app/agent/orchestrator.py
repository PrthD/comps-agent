"""Bounded agent loop with deterministic fallback (BUILD_BRIEF §7).

``value_deterministic`` is the pure pipeline (retrieve → score → flag → estimate) — it needs no API
key and is what both the backtest and the agent's fallback run. ``run_valuation`` wraps it with the
Gemini layer: an optional one-shot, *deterministic* re-query (widen retrieval when the result is
thin/low-confidence — NOT an LLM round-trip) and a single reasoning call for the prose rationale.
The trust boundary is absolute: the LLM only writes the rationale; every number comes from the core.

Failure modes are first-class: with no key, or on any Gemini error/429, ``run_valuation`` returns a
complete ``Valuation`` in ``mode="deterministic"`` with the templated rationale — it never breaks.
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

# Loaded once (lazily, then cached) — the store + hedonic fit are reused across every valuation.
_STORE: pd.DataFrame | None = None
_HEDONIC: HedonicModel | None = None


def init() -> tuple[pd.DataFrame, HedonicModel]:
    """Load the comps store and fit the hedonic model once; cache for the process lifetime."""
    global _STORE, _HEDONIC
    if _STORE is None or _HEDONIC is None:
        store = load_comps()
        _STORE, _HEDONIC = store, fit_hedonic(store)
    return _STORE, _HEDONIC


def value_deterministic(subject: Subject, store: pd.DataFrame, hedonic: HedonicModel) -> Valuation:
    """Run the full deterministic valuation pipeline and stamp ``elapsed_ms``."""
    start = time.perf_counter()
    candidates = search_comps(subject, store)
    scored = score_comps(subject, candidates)
    scored = flag_outliers(scored)
    valuation = estimate_value(subject, scored, hedonic)
    valuation.elapsed_ms = int((time.perf_counter() - start) * 1000)
    return valuation


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


def run_valuation(
    subject: Subject,
    store: pd.DataFrame | None = None,
    hedonic: HedonicModel | None = None,
) -> Valuation:
    """Value a ``Subject``: deterministic core → one bounded re-query → LLM rationale.

    ``store``/``hedonic`` default to the cached singletons; tests inject a small store to stay
    offline and fast. The only LLM call here is the reasoning step; extraction (when the input is a
    document) happens upstream via ``extract_subject`` / ``value_document``, keeping the total ≤2.
    """
    start = time.perf_counter()
    if store is None or hedonic is None:
        store, hedonic = init()

    valuation = value_deterministic(subject, store, hedonic)

    # Bounded deterministic re-query: widen ONCE, adopt only if it found strictly more usable comps.
    if _should_requery(valuation):
        widened = _requery(subject, store, hedonic)
        if widened is not None and _usable_count(widened) > _usable_count(valuation):
            valuation = widened

    # Reasoning: the single LLM call. Any failure (no key, 429, empty) → deterministic fallback.
    mode = "deterministic"
    if config.MODEL_AVAILABLE:
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
