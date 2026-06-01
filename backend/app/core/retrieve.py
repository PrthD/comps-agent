"""Candidate retrieval: hard filters + haversine, with progressive widening (BUILD_BRIEF §6).

Leakage rule (enforced FIRST): only comps with ``sale_date`` strictly before ``subject.as_of_date``.
The strict ``<`` also excludes the subject's own sale in the backtest, where ``as_of_date`` equals
that held-out sale date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app import config
from app.core.data import ATTACHED_TYPES, derive_property_type
from app.schemas import Comp, Subject

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km. Accepts scalars or numpy arrays (broadcasts elementwise)."""
    lat1r, lng1r, lat2r, lng2r = (np.radians(v) for v in (lat1, lng1, lat2, lng2))
    dlat = lat2r - lat1r
    dlng = lng2r - lng1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlng / 2.0) ** 2
    return EARTH_RADIUS_KM * 2.0 * np.arcsin(np.sqrt(a))


def _row_to_comp(rec: dict) -> Comp:
    """Build a validated Comp from a store row (distance_km already attached)."""

    def _opt_int(key: str) -> int | None:
        v = rec.get(key)
        return int(v) if pd.notna(v) else None

    return Comp(
        property_type=rec["property_type"],
        beds=float(rec["beds"]),
        baths=float(rec["baths"]),
        sqft_living=int(rec["sqft_living"]),
        sqft_lot=_opt_int("sqft_lot"),
        year_built=_opt_int("year_built"),
        condition=_opt_int("condition"),
        grade=_opt_int("grade"),
        lat=float(rec["lat"]),
        lng=float(rec["lng"]),
        sale_price=int(rec["sale_price"]),
        sale_date=pd.Timestamp(rec["sale_date"]).date(),
        price_per_sqft=float(rec["price_per_sqft"]),
        distance_km=float(rec["distance_km"]),
    )


def search_comps(subject: Subject, store: pd.DataFrame) -> list[Comp]:
    """Return 10–20 leakage-safe, type-compatible candidates, widening radius/time as needed."""
    subject_type = derive_property_type(subject.grade)  # shared mapping, applied to the subject
    as_of = pd.Timestamp(subject.as_of_date)
    sale_dates = pd.to_datetime(store["sale_date"])

    # Leakage guard FIRST, then compatible property type.
    mask_leak = sale_dates < as_of
    types = store["property_type"]
    if subject_type in ATTACHED_TYPES:
        mask_type = types.isin(list(ATTACHED_TYPES))
    else:
        mask_type = types == subject_type
    base = store[mask_leak & mask_type].copy()
    if base.empty:
        return []

    base["distance_km"] = haversine_km(
        subject.lat, subject.lng, base["lat"].to_numpy(), base["lng"].to_numpy()
    )
    base["age_days"] = (as_of - pd.to_datetime(base["sale_date"])).dt.days

    # Progressive widening: take the first tier reaching the target floor, else the widest tier.
    chosen = base.iloc[0:0]
    for radius_km, window_days in config.RETRIEVAL_TIERS:
        chosen = base[(base["distance_km"] <= radius_km) & (base["age_days"] <= window_days)]
        if len(chosen) >= config.TARGET_COMPS_MIN:
            break
    return [_row_to_comp(rec) for rec in chosen.to_dict("records")]
