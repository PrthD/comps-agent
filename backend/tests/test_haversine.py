"""Haversine correctness."""

from __future__ import annotations

import pytest

from app.core.retrieve import haversine_km


def test_zero_distance():
    assert float(haversine_km(47.60, -122.33, 47.60, -122.33)) == pytest.approx(0.0, abs=1e-9)


def test_known_distance():
    # Space Needle → Seattle Great Wheel is ~1.65 km.
    d = float(haversine_km(47.6205, -122.3493, 47.6062, -122.3425))
    assert d == pytest.approx(1.65, abs=0.3)


def test_monotonic_in_separation():
    near = float(haversine_km(47.60, -122.33, 47.61, -122.33))
    far = float(haversine_km(47.60, -122.33, 47.70, -122.33))
    assert far > near
