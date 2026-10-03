from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Route:
    eids: np.ndarray
    node_path: np.ndarray


class PointOutsideArea(Exception):
    index: int | None = None


class NoRoute(Exception):
    pass


class RoutingGraphP(Protocol):
    n_edges: int
    edge_length_m: np.ndarray
    edge_mid_lonlat: np.ndarray
    edge_highway: np.ndarray
    edge_name: np.ndarray

    def snap(self, lat: float, lon: float) -> int: ...
    def route(
        self, points: list[tuple[float, float]], edge_cost: np.ndarray
    ) -> Route: ...
    def geometry(self, eids: np.ndarray) -> list[list[float]]: ...
    def coord_counts(self, eids: np.ndarray) -> np.ndarray: ...
