"""'Optimize order': best visiting order of via points (start and end stay fixed)."""
from __future__ import annotations

from itertools import pairwise, permutations

import numpy as np

EARTH_RADIUS_M = 6_371_000.0


def straight_line_matrix(points: list[tuple[float, float]]) -> np.ndarray:
    """Haversine distances [m] between (lat, lon) points."""
    lat, lon = np.radians(np.asarray(points, dtype=np.float64)).T
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def best_order(cost: np.ndarray) -> list[int]:
    """Exhaustive search over the middle points; fine for the API limit of 5 points."""
    k = len(cost)
    if k <= 3:
        return list(range(k))
    best, best_cost = list(range(k)), float("inf")
    for middle in permutations(range(1, k - 1)):
        order = [0, *middle, k - 1]
        total = sum(float(cost[a, b]) for a, b in pairwise(order))
        if total < best_cost:
            best, best_cost = order, total
    return best
