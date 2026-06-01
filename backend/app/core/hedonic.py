"""Global hedonic regression for interpretable marginal $/feature (BUILD_BRIEF §6).

Fit once at boot: ``log(price) ~ sqft_living + beds + baths + grade + age (+ zip dummies)`` with a
plain sklearn ``LinearRegression`` (interpretable, not a black box). The log-linear coefs give
a multiplicative per-feature adjustment, applied sequentially so the line-item deltas sum exactly to
``adjusted_price - sale_price``. A simple monthly $/sqft index supplies the time adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from app import config
from app.schemas import Comp, Subject


@dataclass
class HedonicModel:
    """Fitted log-price model: marginal coefficients + a monthly $/sqft time index."""

    model: LinearRegression
    feature_names: list[str]
    zip_columns: list[str]
    coef: dict[str, float]  # structural feature -> log-price coefficient
    monthly_factor: dict  # pandas Period -> $/sqft factor (normalized to ~1)
    min_period: pd.Period
    max_period: pd.Period
    extras: dict = field(default_factory=dict)


def fit_hedonic(store: pd.DataFrame) -> HedonicModel:
    """Fit the global hedonic model and monthly time index once over the whole store."""
    df = store.copy()
    sale_dt = pd.to_datetime(df["sale_date"])
    df["age"] = sale_dt.dt.year - df["year_built"]
    df = df[df["age"].notna() & (df["sale_price"] > 0) & (df["sqft_living"] > 0)]

    feats = list(config.HEDONIC_FEATURES)  # sqft_living, beds, baths, grade, age
    x_struct = df[feats].astype(float)
    if config.HEDONIC_USE_ZIP:
        zdummies = pd.get_dummies(df["zipcode"].astype("category"), prefix="zip", drop_first=True)
        x = pd.concat([x_struct, zdummies], axis=1)
        zip_columns = list(zdummies.columns)
    else:
        x = x_struct
        zip_columns = []

    y = np.log(df["sale_price"].to_numpy(dtype=float))
    model = LinearRegression()
    model.fit(x.to_numpy(dtype=float), y)
    coef = {f: float(c) for f, c in zip(feats, model.coef_[: len(feats)], strict=False)}

    period = pd.to_datetime(df["sale_date"]).dt.to_period(config.TIME_INDEX_FREQ)
    base = float(df["price_per_sqft"].median())
    monthly_factor = (df.groupby(period)["price_per_sqft"].median() / base).to_dict()
    return HedonicModel(
        model=model,
        feature_names=feats,
        zip_columns=zip_columns,
        coef=coef,
        monthly_factor=monthly_factor,
        min_period=period.min(),
        max_period=period.max(),
    )


def _time_factor(model: HedonicModel, when) -> float:
    """Normalized $/sqft factor for a date, clamped to the fitted data range (no extrapolation)."""
    period = pd.Period(pd.Timestamp(when), freq=config.TIME_INDEX_FREQ)
    period = max(model.min_period, min(model.max_period, period))
    return float(model.monthly_factor.get(period, 1.0))


def adjust_comp(subject: Subject, comp: Comp, model: HedonicModel) -> tuple[dict[str, float], int]:
    """Return (line-item $ deltas, adjusted_price) moving the comp toward the subject."""
    as_of_year = subject.as_of_date.year
    subj = {
        "sqft_living": float(subject.sqft_living),
        "beds": float(subject.beds),
        "baths": float(subject.baths),
        "grade": None if subject.grade is None else float(subject.grade),
        "age": None if subject.year_built is None else float(as_of_year - subject.year_built),
    }
    comp_v = {
        "sqft_living": float(comp.sqft_living),
        "beds": float(comp.beds),
        "baths": float(comp.baths),
        "grade": None if comp.grade is None else float(comp.grade),
        "age": None if comp.year_built is None else float(as_of_year - comp.year_built),
    }

    deltas: dict[str, float] = {}
    running = float(comp.sale_price)
    for f in model.feature_names:
        sv, cv = subj[f], comp_v[f]
        if sv is None or cv is None:
            deltas[f] = 0.0
            continue
        new = running * float(np.exp(model.coef[f] * (sv - cv)))
        deltas[f] = new - running
        running = new

    time_factor = _time_factor(model, subject.as_of_date) / _time_factor(model, comp.sale_date)
    new = running * time_factor
    deltas["time"] = new - running
    running = new
    return deltas, int(round(running))
