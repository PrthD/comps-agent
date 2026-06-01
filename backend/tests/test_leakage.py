"""Leakage guard (BUILD_BRIEF §6/§11) — authored BEFORE the retrieval implementation.

The core promise to a lender: when valuing a subject we never look at sales on or after the as-of
date, and never the subject's own sale. Asserted directly against ``search_comps``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.core.data import DETACHED
from app.core.retrieve import search_comps
from app.schemas import Subject

AS_OF = date(2015, 1, 1)
CENTER_LAT, CENTER_LNG = 47.60, -122.33
SUBJECT_PRICE_MARKER = 999_999  # the subject's own (forbidden) sale, dated exactly on AS_OF


def _straddling_store() -> pd.DataFrame:
    """40 nearby comps spanning before AND after AS_OF, plus the subject's own as-of-dated sale."""
    rows = [
        dict(
            sale_date=date(2014, 1, 1) + timedelta(days=20 * i),
            sale_price=500_000,
            beds=3.0,
            baths=2.0,
            sqft_living=2000,
            sqft_lot=5000,
            floors=1.0,
            condition=3,
            grade=7,
            year_built=1995,
            zipcode=98101,
            lat=CENTER_LAT + i * 0.0002,
            lng=CENTER_LNG + i * 0.0002,
            price_per_sqft=250.0,
            property_type=DETACHED,
        )
        for i in range(40)
    ]
    rows.append(
        dict(
            sale_date=AS_OF,  # exactly the as-of date → must be excluded
            sale_price=SUBJECT_PRICE_MARKER,
            beds=3.0,
            baths=2.0,
            sqft_living=2000,
            sqft_lot=5000,
            floors=1.0,
            condition=3,
            grade=7,
            year_built=1995,
            zipcode=98101,
            lat=CENTER_LAT,
            lng=CENTER_LNG,
            price_per_sqft=500.0,
            property_type=DETACHED,
        )
    )
    return pd.DataFrame(rows)


def _subject() -> Subject:
    return Subject(
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
        as_of_date=AS_OF,
    )


def test_no_comp_dated_on_or_after_as_of_date():
    comps = search_comps(_subject(), _straddling_store())
    assert comps, "expected at least one valid prior comp"
    assert all(c.sale_date < AS_OF for c in comps)


def test_subjects_own_sale_is_never_returned():
    comps = search_comps(_subject(), _straddling_store())
    assert all(c.sale_price != SUBJECT_PRICE_MARKER for c in comps)
    assert all(c.sale_date != AS_OF for c in comps)
