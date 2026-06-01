"""Global hedonic regression for interpretable marginal $/feature (BUILD_BRIEF §6).

Fit once at boot: ``log(price) ~ log(sqft_living) + beds + baths + grade + age (+ zip)``
with a plain sklearn ``LinearRegression`` (not a black box). Logging sqft gives a scale-free
elasticity, so size no longer swamps the small-integer features. Both the fitted coefficients
(``raw_coef``) and the applied ones (``adj_coef``) are surfaced; applied coefficients are clamped
to their economically sensible sign, so a backwards-signed feature (e.g. beds < 0) contributes no
adjustment rather than a reversed one. Coefficients act multiplicatively, applied sequentially so
the line-item deltas sum exactly to ``adjusted_price - sale_price``. A monthly $/sqft index
supplies the time adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from app import config
from app.schemas import Comp, Subject


@dataclass
class HedonicModel:
    """Fitted log-price model: surfaced + clamped coefficients and a monthly $/sqft time index."""

    model: LinearRegression
    feature_names: list[str]
    log_features: list[str]  # features fit/applied in log space (elasticities)
    zip_columns: list[str]
    raw_coef: dict[str, float]  # fitted coefficients, as-is (may be backwards-signed)
    adj_coef: dict[str, float]  # coefficients actually applied (sign-clamped)
    clamped_features: list[str]  # features whose sign was clamped to 0 (raw != adj)
    monthly_factor: dict  # pandas Period -> $/sqft factor (normalized to ~1)
    min_period: pd.Period
    max_period: pd.Period
    sqft_elasticity: float  # log-log elasticity of price w.r.t. sqft (0 if sqft not logged)
    implied_marginal_ppsf: float  # elasticity * median $/sqft — the marginal sqft rate
    implied_level_ppsf: float  # median(model-predicted price / sqft) — the implied price LEVEL


def _feature_column(df: pd.DataFrame, feature: str) -> pd.Series:
    col = df[feature].astype(float)
    return np.log(col) if feature in config.HEDONIC_LOG_FEATURES else col


def _clamp_sign(feature: str, coef: float) -> float:
    """Clamp a coefficient to its economically sensible half-line (0 if backwards-signed)."""
    if not config.HEDONIC_CLAMP_SIGNS:
        return coef
    sign = config.HEDONIC_EXPECTED_SIGN.get(feature, 0)
    if sign > 0:
        return max(0.0, coef)
    if sign < 0:
        return min(0.0, coef)
    return coef


def fit_hedonic(store: pd.DataFrame) -> HedonicModel:
    """Fit the global hedonic model and monthly time index once over the whole store."""
    df = store.copy()
    sale_dt = pd.to_datetime(df["sale_date"])
    df["age"] = sale_dt.dt.year - df["year_built"]
    df = df[df["age"].notna() & (df["sale_price"] > 0) & (df["sqft_living"] > 0)]

    feats = list(config.HEDONIC_FEATURES)
    x_struct = pd.DataFrame({f: _feature_column(df, f) for f in feats}, index=df.index)
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
    raw_coef = {f: float(c) for f, c in zip(feats, model.coef_[: len(feats)], strict=False)}
    adj_coef = {f: _clamp_sign(f, c) for f, c in raw_coef.items()}
    clamped = [f for f in feats if abs(adj_coef[f] - raw_coef[f]) > 1e-12]

    period = pd.to_datetime(df["sale_date"]).dt.to_period(config.TIME_INDEX_FREQ)
    base = float(df["price_per_sqft"].median())
    monthly_factor = (df.groupby(period)["price_per_sqft"].median() / base).to_dict()

    median_ppsf = float(df["price_per_sqft"].median())
    median_price = float(df["sale_price"].median())
    sqft_logged = "sqft_living" in config.HEDONIC_LOG_FEATURES
    elasticity = adj_coef["sqft_living"] if sqft_logged else 0.0
    # Marginal sqft rate: log-log → elasticity * median $/sqft; level spec → coef * median price.
    if sqft_logged:
        implied_marginal = elasticity * median_ppsf
    else:
        implied_marginal = adj_coef["sqft_living"] * median_price
    # Implied price LEVEL: median of model-predicted price / sqft (exercises all coefficients).
    predicted = np.exp(model.predict(x.to_numpy(dtype=float)))
    implied_level = float(np.median(predicted / df["sqft_living"].to_numpy(dtype=float)))

    return HedonicModel(
        model=model,
        feature_names=feats,
        log_features=list(config.HEDONIC_LOG_FEATURES),
        zip_columns=zip_columns,
        raw_coef=raw_coef,
        adj_coef=adj_coef,
        clamped_features=clamped,
        monthly_factor=monthly_factor,
        min_period=period.min(),
        max_period=period.max(),
        sqft_elasticity=float(elasticity),
        implied_marginal_ppsf=float(implied_marginal),
        implied_level_ppsf=implied_level,
    )


def validate_hedonic(model: HedonicModel) -> None:
    """Assert the model's implied marginal $/sqft is sane before it's trusted (BUILD_BRIEF §6)."""
    low, high = config.HEDONIC_IMPLIED_PPSF_RANGE
    ppsf = model.implied_level_ppsf
    if not (low <= ppsf <= high):
        raise ValueError(
            f"Implied $/sqft level ${ppsf:,.0f} is outside the sane band "
            f"[${low:,.0f}, ${high:,.0f}] — hedonic scaling looks wrong; do not trust the backtest."
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
        sv, cv, coef = subj[f], comp_v[f], model.adj_coef[f]
        if sv is None or cv is None or coef == 0.0:
            deltas[f] = 0.0
            continue
        if f in model.log_features:
            if sv <= 0 or cv <= 0:
                deltas[f] = 0.0
                continue
            factor = (sv / cv) ** coef  # elasticity: (subject/comp)^coef
        else:
            factor = float(np.exp(coef * (sv - cv)))
        new = running * factor
        deltas[f] = new - running
        running = new

    time_factor = _time_factor(model, subject.as_of_date) / _time_factor(model, comp.sale_date)
    new = running * time_factor
    deltas["time"] = new - running
    running = new
    return deltas, int(round(running))
