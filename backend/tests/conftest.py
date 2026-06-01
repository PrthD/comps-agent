"""Shared fixtures for the core test suite (BUILD_BRIEF §11).

Factories (``make_subject``/``make_comp``) build valid pydantic objects with sensible defaults;
``synthetic_store`` is a small, seeded King-County-shaped frame and ``hedonic_model`` is fit on it.
No LLM, no network — these tests exercise only the deterministic core.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core.data import DETACHED, derive_property_type
from app.core.hedonic import fit_hedonic
from app.schemas import Comp, Subject

CENTER_LAT, CENTER_LNG = 47.60, -122.33


@pytest.fixture
def make_subject():
    def _make(**overrides) -> Subject:
        params = dict(
            property_type=DETACHED,
            beds=3.0,
            baths=2.0,
            sqft_living=2000,
            sqft_lot=5000,
            year_built=1995,
            condition=3,
            grade=7,
            lat=CENTER_LAT,
            lng=CENTER_LNG,
            as_of_date=date(2015, 6, 1),
        )
        params.update(overrides)
        return Subject(**params)

    return _make


@pytest.fixture
def make_comp():
    def _make(**overrides) -> Comp:
        params = dict(
            property_type=DETACHED,
            beds=3.0,
            baths=2.0,
            sqft_living=2000,
            sqft_lot=5000,
            year_built=1995,
            condition=3,
            grade=7,
            lat=CENTER_LAT,
            lng=CENTER_LNG,
            sale_price=500000,
            sale_date=date(2015, 1, 1),
            price_per_sqft=250.0,
            distance_km=1.0,
        )
        params.update(overrides)
        return Comp(**params)

    return _make


@pytest.fixture
def synthetic_store() -> pd.DataFrame:
    """80 seeded detached-ish KC rows with a gentle size + time price signal."""
    rng = np.random.default_rng(42)
    start = date(2014, 5, 1)
    rows = []
    for _ in range(80):
        sqft = int(rng.integers(1200, 3200))
        grade = int(rng.integers(6, 11))
        months = int(rng.integers(0, 12))
        sale_dt = start + timedelta(days=30 * months + int(rng.integers(0, 28)))
        ppsf = max(120.0, 230.0 + (grade - 7) * 6.0 + months * 1.5 + float(rng.normal(0, 12)))
        price = int(round(ppsf * sqft))
        rows.append(
            dict(
                sale_date=sale_dt,
                sale_price=price,
                beds=float(rng.integers(2, 6)),
                baths=float(rng.choice([1.0, 1.5, 2.0, 2.5, 3.0])),
                sqft_living=sqft,
                sqft_lot=int(rng.integers(3000, 9000)),
                floors=float(rng.choice([1.0, 1.5, 2.0])),
                condition=int(rng.integers(2, 6)),
                grade=grade,
                year_built=int(rng.integers(1950, 2014)),
                zipcode=int(rng.choice([98101, 98103, 98115])),
                lat=CENTER_LAT + float(rng.normal(0, 0.02)),
                lng=CENTER_LNG + float(rng.normal(0, 0.02)),
                price_per_sqft=round(price / sqft, 2),
            )
        )
    df = pd.DataFrame(rows)
    df["property_type"] = [
        derive_property_type(g, f) for g, f in zip(df["grade"], df["floors"], strict=False)
    ]
    return df


@pytest.fixture
def hedonic_model(synthetic_store):
    return fit_hedonic(synthetic_store)
