"""Route metrics and FASTEST vs ECO comparison (JSON-ready numbers)."""
from __future__ import annotations

import math

import numpy as np

from ..profiles import RiderProfile
from .costs import EdgeCosts

HEAT_STRESS_UTCI_C = 32.0  # UTCI "strong heat stress" threshold
METRIC_KEYS = ("distance_m", "time_min", "avg_discomfort", "shade_pct", "pm25_dose_ug", "heat_stress_min")


def _num(x: float, digits: int) -> float | int | None:
    x = float(x)
    if not math.isfinite(x):
        return None
    return round(x) if digits == 0 else round(x, digits)


def route_metrics(eids: np.ndarray, costs: EdgeCosts, profile: RiderProfile, edge_length_m: np.ndarray) -> dict:
    if len(eids) == 0:
        return dict.fromkeys(METRIC_KEYS, 0.0)
    t = costs.time_s[eids]
    total = max(float(t.sum()), 1e-9)
    exp = costs.exposure

    def time_weighted(values: np.ndarray) -> float:
        return float((t * values[eids]).sum() / total)

    dose = (np.asarray(exp.pm25)[eids] * profile.ventilation_m3h * t / 3600).sum()
    return {
        "distance_m": _num(np.asarray(edge_length_m)[eids].sum(), 0),
        "time_min": _num(total / 60, 1),
        "avg_discomfort": _num(time_weighted(exp.discomfort) * 10, 1),
        "shade_pct": _num(time_weighted(costs.shade) * 100, 1),
        "pm25_dose_ug": _num(dose, 2),
        "heat_stress_min": _num(t[np.asarray(exp.utci_c)[eids] > HEAT_STRESS_UTCI_C].sum() / 60, 1),
    }


def _delta(a: float | None, b: float | None, digits: int = 1) -> float:
    return round(b - a, digits) if a is not None and b is not None else 0.0


def _delta_pct(a: float | None, b: float | None) -> float:
    return round((b - a) / a * 100, 1) if a and b is not None else 0.0


def compare(fastest: dict, eco: dict, same_route: bool) -> dict:
    return {
        "same_route": bool(same_route),
        "time_delta_min": _delta(fastest["time_min"], eco["time_min"]),
        "time_delta_pct": _delta_pct(fastest["time_min"], eco["time_min"]),
        "pm25_dose_delta_pct": _delta_pct(fastest["pm25_dose_ug"], eco["pm25_dose_ug"]),
        "shade_delta_pp": _delta(fastest["shade_pct"], eco["shade_pct"]),
        "heat_stress_delta_min": _delta(fastest["heat_stress_min"], eco["heat_stress_min"]),
    }
