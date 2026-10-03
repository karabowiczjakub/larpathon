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
    """t * (1 + alpha * excess): only discomfort above today's city baseline (rescaled to 0..1) costs extra.

    In a heatwave or smog the fuzzy discomfort is 0.7-0.9 across the whole city, so with plain
    t * (1 + alpha * D) every detour adds discomfort-minutes and ECO collapses onto FASTEST (measured on
    the real graph: +0.4% time, +3 pp shade). On mild days the baseline is ~0 and nothing changes.
    """
    d = c.exposure.discomfort
    base = float(np.percentile(d, ECO_BASELINE_PERCENTILE))
    excess = np.clip((d - base) / max(1.0 - base, 1e-6), 0.0, 1.0)
    return c.time_s * (1.0 + p.eco_alpha * excess)


FASTEST = RouteVariant("fastest", "Fastest", "#6b7280", fastest_cost)
ECO = RouteVariant("eco", "Healthier", "#16a34a", eco_cost)
DEFAULT_VARIANTS: tuple[RouteVariant, ...] = (FASTEST, ECO)
