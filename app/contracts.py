"""Shade contracts from roles/04_backend_integration.md."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float  # Clockwise from north.
    elevation_deg: float


class ShadeModelP(Protocol):
    edge_tree_frac: np.ndarray

    def sun(self, at: datetime) -> SunPosition: ...

    def edge_shade(self, at: datetime) -> np.ndarray: ...


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
        self,
        points: list[tuple[float, float]],
        edge_cost: np.ndarray,
    ) -> Route: ...

    def geometry(self, eids: np.ndarray) -> list[list[float]]: ...

    def coord_counts(self, eids: np.ndarray) -> np.ndarray: ...