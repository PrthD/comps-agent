"""Shared property-type mapping for subjects and comps (BUILD_BRIEF §5; P1 priority #2)."""

from __future__ import annotations

from app.core.data import CONDO, DETACHED, TOWNHOUSE, derive_property_type, types_compatible


def test_high_grade_and_missing_grade_are_detached():
    assert derive_property_type(9, 1.0) == DETACHED
    assert derive_property_type(7, 2.0) == DETACHED
    assert derive_property_type(None) == DETACHED


def test_low_grade_maps_to_attached():
    assert derive_property_type(5, 2.0) == TOWNHOUSE
    assert derive_property_type(5, 1.0) == CONDO


def test_compatibility_rules():
    assert types_compatible(DETACHED, DETACHED)
    assert types_compatible(TOWNHOUSE, CONDO)  # both attached
    assert not types_compatible(DETACHED, CONDO)


def test_same_function_for_subject_and_comp():
    # The subject path passes no floors; a same-grade comp must land on the same canonical type.
    assert derive_property_type(9) == derive_property_type(9, 1.0) == DETACHED
