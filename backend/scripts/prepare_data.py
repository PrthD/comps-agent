"""Download, clean, and bundle the King County sales dataset.

Source: the GeoDa Center data lab mirror of the Kaggle ``harlfoxem/housesalesprediction``
dataset (CC0). The zip is downloaded and unpacked entirely in memory (no temp files, no extra
dependencies), cleaned, and written to the bundled parquet via DuckDB, we deliberately skip
``pyarrow``, so all parquet I/O in this project goes through DuckDB.

Usage (run from backend/):
    uv run python scripts/prepare_data.py
    uv run python scripts/prepare_data.py --source local --input /path/to/kc_house_data.csv
    uv run python scripts/prepare_data.py --url https://.../kingcounty.zip
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

# Make ``app`` importable even when run as a plain script (not just via the editable install).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import DATA_PATH  # noqa: E402  (import after sys.path bootstrap)

DEFAULT_URL = "https://geodacenter.github.io/data-and-lab//data/kingcounty.zip"
DEFAULT_MEMBER = "kingcounty/kc_house_data.csv"

# Raw KC columns we keep and their rename to schema-friendly names.
RAW_COLUMNS = [
    "date",
    "price",
    "bedrooms",
    "bathrooms",
    "sqft_living",
    "sqft_lot",
    "floors",
    "condition",
    "grade",
    "yr_built",
    "zipcode",
    "lat",
    "long",
]
RENAME = {
    "date": "sale_date",
    "price": "sale_price",
    "bedrooms": "beds",
    "bathrooms": "baths",
    "yr_built": "year_built",
    "long": "lng",
}
# Final column order written to the parquet (sale_date cast to DATE at write time).
FINAL_COLUMNS = [
    "sale_date",
    "sale_price",
    "beds",
    "baths",
    "sqft_living",
    "sqft_lot",
    "floors",
    "condition",
    "grade",
    "year_built",
    "zipcode",
    "lat",
    "lng",
    "price_per_sqft",
]


def load_raw(source: str, url: str, member: str, input_path: Path | None) -> pd.DataFrame:
    """Load the raw KC CSV from a zip URL, a plain CSV URL, or a local file."""
    if source == "local":
        if not input_path:
            raise SystemExit("--source local requires --input <csv path>")
        return pd.read_csv(input_path)
    if source == "kaggle":
        raise SystemExit(
            "The 'kaggle' source needs `kagglehub` + credentials (not a default dependency). "
            "Use --source url (default) or --source local."
        )
    print(f"Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "kv-comps-agent/0.1"})
    with urllib.request.urlopen(req) as resp:
        blob = resp.read()
    if url.endswith(".zip") or member:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
            name = member if member in names else next(n for n in names if n.endswith(".csv"))
            with zf.open(name) as fh:
                return pd.read_csv(fh)
    return pd.read_csv(io.BytesIO(blob))


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Select + rename columns, parse dates, drop bad rows, and derive price_per_sqft."""
    df = df[RAW_COLUMNS].rename(columns=RENAME)
    # KC date format, e.g. '20141013T000000'.
    df["sale_date"] = pd.to_datetime(df["sale_date"], format="%Y%m%dT%H%M%S")
    df = df.dropna(subset=["sale_price", "sqft_living", "lat", "lng", "sale_date"])
    df = df[(df["sale_price"] > 0) & (df["sqft_living"] > 0)]
    df = df.drop_duplicates()
    df["sale_price"] = df["sale_price"].astype(int)
    df["price_per_sqft"] = (df["sale_price"] / df["sqft_living"]).round(2)
    return df[FINAL_COLUMNS].reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the King County comps parquet.")
    parser.add_argument("--source", choices=["url", "local", "kaggle"], default="url")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--member", default=DEFAULT_MEMBER, help="CSV path inside the zip")
    parser.add_argument("--input", type=Path, default=None, help="local CSV (for --source local)")
    parser.add_argument("--output", type=Path, default=DATA_PATH)
    args = parser.parse_args()

    df = clean(load_raw(args.source, args.url, args.member, args.input))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("raw_df", df)
    con.execute(
        "COPY (SELECT CAST(sale_date AS DATE) AS sale_date, * EXCLUDE (sale_date) FROM raw_df) "
        f"TO '{args.output}' (FORMAT PARQUET)"
    )
    con.close()

    print(f"Wrote {len(df):,} rows to {args.output}")
    print(f"Columns: {list(df.columns)}")
    print(f"Date range: {df['sale_date'].min().date()} → {df['sale_date'].max().date()}")


if __name__ == "__main__":
    main()
