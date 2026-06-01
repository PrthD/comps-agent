"""Load the bundled King County comps into an in-memory store (BUILD_BRIEF §6, implemented in P1).

DuckDB-only parquet I/O: we deliberately skip ``pyarrow``, so every parquet read in this codebase
must go through DuckDB (e.g. ``duckdb.read_parquet(path)`` or ``SELECT * FROM read_parquet(?)``) —
never ``pd.read_parquet``. ``scripts/prepare_data.py`` writes the file the same way.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.config import DATA_PATH


def load_comps(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load the read-only comps store from the bundled parquet via DuckDB. (P1)"""
    raise NotImplementedError("P1: load the comps store via DuckDB")
