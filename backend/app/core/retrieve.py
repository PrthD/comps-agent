"""Candidate retrieval: hard filters + haversine, with progressive widening (BUILD_BRIEF §6, P1).

Enforces the leakage rule: only comps with ``sale_date`` strictly before ``subject.as_of_date``,
and never the subject itself.
"""

from __future__ import annotations

import pandas as pd

from app.schemas import Comp, Subject


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometers between two lat/lng points. (P1)"""
    raise NotImplementedError("P1: haversine")


def search_comps(subject: Subject, store: pd.DataFrame) -> list[Comp]:
    """Filter + widen across the radius/time tiers to 10–20 leakage-safe candidates. (P1)"""
    raise NotImplementedError("P1: search_comps")
