"""Load the bundled King County comps into an in-memory store (BUILD_BRIEF §6).

DuckDB-only parquet I/O: we deliberately skip ``pyarrow``, so every parquet read in this codebase
must go through DuckDB — never ``pd.read_parquet``. prepare_data.py writes the file the same way.

The parquet has no ``property_type`` column (KC has no type label), so ``derive_property_type``
synthesizes one from construction grade (and floors when available). The SAME function is applied to
comps here and to the subject in retrieval, so both sides land in one canonical vocabulary.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from app.config import DATA_PATH

# §5 property-type vocabulary.
DETACHED = "detached"
TOWNHOUSE = "townhouse"
CONDO = "condo"
_ATTACHED = frozenset({TOWNHOUSE, CONDO})


def derive_property_type(grade: int | None, floors: float | None = None) -> str:
    """Map KC construction grade (+ floors when known) into the §5 property-type vocabulary.

    KC has no real property-type field and is overwhelmingly detached single-family, so
    ``detached`` is the default; only clearly low-grade stock is treated as attached. This is a
    documented heuristic proxy, not ground truth — and the single source used for BOTH comps and
    the subject, so the compatible-type filter compares like with like.
    """
    if grade is None or grade > 6:
        return DETACHED
    # Low grade → smaller/older attached stock: multi-floor reads as townhouse, else flat/condo.
    if floors is not None and floors >= 2:
        return TOWNHOUSE
    return CONDO


def types_compatible(a: str, b: str) -> bool:
    """True if two types are comparable: exact match, or both attached (townhouse/condo)."""
    return a == b or (a in _ATTACHED and b in _ATTACHED)


def load_comps(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load the comps store from the bundled parquet via DuckDB, deriving property_type."""
    df = duckdb.read_parquet(str(path)).df()
    df["property_type"] = [
        derive_property_type(g, f) for g, f in zip(df["grade"], df["floors"], strict=False)
    ]
    return df
