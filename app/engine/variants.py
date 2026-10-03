"""Route variants (Strategy): each one turns EdgeCosts into an edge cost vector for the graph."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ..profiles import RiderProfile
from .costs import EdgeCosts

CostFn = Callable[[EdgeCosts, RiderProfile], np.ndarray]
ECO_BASELINE_PERCENTILE = 10  # discomfort this low is available almost everywhere today: not worth a detour


@dataclass(frozen=True)
class RouteVariant:
    id: str
    label: str
    color: str
    cost: CostFn


def fastest_cost(c: EdgeCosts, p: RiderProfile) -> np.ndarray:
    return c.time_s


def eco_cost(c: EdgeCosts, p: RiderProfile) -> np.ndarray:
    """t * (1 + alpha * excess + air_weight * (relative air + air hotspot)).

    excess: only discomfort above today's city baseline (rescaled to 0..1) costs extra. In a heatwave or
    smog the fuzzy discomfort is 0.7-0.9 across the whole city, so with plain t * (1 + alpha * D) every
    detour adds discomfort-minutes and ECO collapses onto FASTEST (measured on the real graph: +0.4% time,
    +3 pp shade). On mild days the baseline is ~0 and nothing changes.

    The air term is for profiles that care most about air (asthma). Relative air (time x air index) is
    exposure, so a detour through ordinary city air is not free and the inhaled dose barely grows; the
    hotspot part still steers around streets clearly worse than today's cleaner ones (NO2 at arterials).
    Measured on the real graph for asthma: smog PM2.5 dose -1.3% (p90 +1.2%), live -87% poor-air minutes.
    """
    d = c.exposure.discomfort
    base = float(np.percentile(d, ECO_BASELINE_PERCENTILE))
    excess = np.clip((d - base) / max(1.0 - base, 1e-6), 0.0, 1.0)
    weight = 1.0 + p.eco_alpha * excess
    if p.eco_air_weight:
        weight = weight + p.eco_air_weight * air_penalty(c.exposure.air_index)
    return c.time_s * weight


def air_penalty(air_index: np.ndarray) -> np.ndarray:
    """Continuous EAQI relative to a typical street now (1 = city median), plus up to one EAQI band of
    'hotspot' above the city's cleaner streets (10th percentile)."""
    air = np.clip(np.nan_to_num(np.asarray(air_index, dtype=np.float64)), 0.1, 6.0)
    hotspot = np.clip(air - np.percentile(air, ECO_BASELINE_PERCENTILE), 0.0, 1.0)
    return air / float(np.median(air)) + hotspot


FASTEST = RouteVariant("fastest", "Fastest", "#6b7280", fastest_cost)
ECO = RouteVariant("eco", "Healthier", "#16a34a", eco_cost)
DEFAULT_VARIANTS: tuple[RouteVariant, ...] = (FASTEST, ECO)
