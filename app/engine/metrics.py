"""Route metrics and FASTEST vs ECO comparison (JSON-ready numbers)."""
from __future__ import annotations

import math

import numpy as np

from ..profiles import RiderProfile
from .costs import EdgeCosts

HEAT_STRESS_UTCI_C = 32.0  # UTCI "strong heat stress" threshold
HIGH_UV_INDEX = 6.0  # WHO "high" UV, applied to the shade-reduced UV on each edge
POOR_AIR_INDEX = 3.0  # continuous EAQI: 3 = start of "poor" (PM2.5, PM10 or NO2, the worst one decides)
HOT_FEELS_C = 26.0  # UTCI "moderate heat stress": from here a cooler route is a real benefit
# Below these gains the more comfortable route is not worth recommending over the faster one
EQUIVALENT_DISCOMFORT = 0.5  # on the 0-10 scale
EQUIVALENT_DOSE_PCT = 3.0
EQUIVALENT_MINUTES = 1.0  # of poor air, heat stress or high UV saved
EQUIVALENT_COOLING_C = 1.0
METRIC_KEYS = ("distance_m", "time_min", "avg_discomfort", "shade_pct", "pm25_dose_ug", "heat_stress_min",
               "uv_high_min", "air_poor_min", "utci_avg_c")


def _num(x: float, digits: int) -> float | int | None:
    x = float(x)
    if not math.isfinite(x):
        return None
    return round(x) if digits == 0 else round(x, digits)


def route_metrics(eids: np.ndarray, costs: EdgeCosts, profile: RiderProfile, edge_length_m: np.ndarray) -> dict:
    if len(eids) == 0:
        return {**dict.fromkeys(METRIC_KEYS, 0.0), "utci_avg_c": None}  # no ride, no felt temperature
    t = costs.time_s[eids]
    total = max(float(t.sum()), 1e-9)
    exp = costs.exposure

    def time_weighted(values: np.ndarray) -> float:
        return float((t * np.asarray(values)[eids]).sum() / total)

    dose = (np.asarray(exp.pm25)[eids] * profile.ventilation_m3h * t / 3600).sum()
    return {
        "distance_m": _num(np.asarray(edge_length_m)[eids].sum(), 0),
        "time_min": _num(total / 60, 1),
        "avg_discomfort": _num(time_weighted(exp.discomfort) * 10, 1),
        "shade_pct": _num(time_weighted(costs.shade) * 100, 1),
        "pm25_dose_ug": _num(dose, 2),
        "heat_stress_min": _num(t[np.asarray(exp.utci_c)[eids] > HEAT_STRESS_UTCI_C].sum() / 60, 1),
        "uv_high_min": _num(t[np.asarray(exp.uv_eff)[eids] >= HIGH_UV_INDEX].sum() / 60, 1),
        "air_poor_min": _num(t[np.asarray(exp.air_index)[eids] >= POOR_AIR_INDEX].sum() / 60, 1),
        "utci_avg_c": _num(time_weighted(exp.utci_c), 1),  # felt temperature along the ride
    }


def _delta(a: float | None, b: float | None, digits: int = 1) -> float:
    return round(b - a, digits) if a is not None and b is not None else 0.0


def _delta_pct(a: float | None, b: float | None) -> float:
    return round((b - a) / a * 100, 1) if a and b is not None else 0.0


def _gain(fastest: dict, eco: dict, key: str) -> float:
    """How much lower the more comfortable route is on `key` (0 when unknown)."""
    a, b = fastest.get(key), eco.get(key)
    return a - b if a is not None and b is not None else 0.0


def equivalent(fastest: dict, eco: dict) -> bool:
    """True when the more comfortable route brings nothing that matters, e.g. 36% more trees at night for +7% time
    and +1% inhaled dose: then the faster route is just as good."""
    hot = (fastest.get("utci_avg_c") or 0.0) >= HOT_FEELS_C
    return (
        _gain(fastest, eco, "avg_discomfort") < EQUIVALENT_DISCOMFORT
        and _delta_pct(fastest.get("pm25_dose_ug"), eco.get("pm25_dose_ug")) > -EQUIVALENT_DOSE_PCT
        and all(_gain(fastest, eco, k) < EQUIVALENT_MINUTES for k in ("air_poor_min", "heat_stress_min", "uv_high_min"))
        and not (hot and _gain(fastest, eco, "utci_avg_c") >= EQUIVALENT_COOLING_C)
    )


def compare(fastest: dict, eco: dict, same_route: bool) -> dict:
    return {
        "same_route": bool(same_route),
        "equivalent": bool(same_route) or equivalent(fastest, eco),
        "time_delta_min": _delta(fastest["time_min"], eco["time_min"]),
        "time_delta_pct": _delta_pct(fastest["time_min"], eco["time_min"]),
        "pm25_dose_delta_pct": _delta_pct(fastest["pm25_dose_ug"], eco["pm25_dose_ug"]),
        "shade_delta_pp": _delta(fastest["shade_pct"], eco["shade_pct"]),
        "heat_stress_delta_min": _delta(fastest["heat_stress_min"], eco["heat_stress_min"]),
        "uv_high_delta_min": _delta(fastest["uv_high_min"], eco["uv_high_min"]),
        "air_poor_delta_min": _delta(fastest["air_poor_min"], eco["air_poor_min"]),
        "utci_delta_c": _delta(fastest["utci_avg_c"], eco["utci_avg_c"]),
    }
