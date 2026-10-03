"""Route variants (Strategy): each one turns EdgeCosts into an edge cost vector for the graph."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ..profiles import RiderProfile
from .costs import EdgeCosts

CostFn = Callable[[EdgeCosts, RiderProfile], np.ndarray]


@dataclass(frozen=True)
class RouteVariant:
    id: str
    label: str
    color: str
    cost: CostFn


def fastest_cost(c: EdgeCosts, p: RiderProfile) -> np.ndarray:
    return c.time_s


def eco_cost(c: EdgeCosts, p: RiderProfile) -> np.ndarray:
    return c.time_s * (1.0 + p.eco_alpha * c.exposure.discomfort)


FASTEST = RouteVariant("fastest", "Fastest", "#6b7280", fastest_cost)
ECO = RouteVariant("eco", "Healthier", "#16a34a", eco_cost)
DEFAULT_VARIANTS: tuple[RouteVariant, ...] = (FASTEST, ECO)
