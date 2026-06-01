"""Global hedonic regression for interpretable marginal $/feature (BUILD_BRIEF §6, P1)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.schemas import Comp, Subject


@dataclass
class HedonicModel:
    """Fitted log-price model + marginal feature values used to adjust comps. (P1)"""


def fit_hedonic(store: pd.DataFrame) -> HedonicModel:
    """Fit log(price) ~ sqft_living + beds + baths + grade + age (+ zip) once at boot. (P1)"""
    raise NotImplementedError("P1: fit_hedonic")


def adjust_comp(subject: Subject, comp: Comp, model: HedonicModel) -> dict[str, float]:
    """Return the line-item $ adjustments that bring a comp toward the subject. (P1)"""
    raise NotImplementedError("P1: adjust_comp")
