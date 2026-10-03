"""Shared contracts from roles/04_backend_integration.md, section 4."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Literal, Protocol

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


# ---------- Role 2: Environment ----------
@dataclass(frozen=True)
class StationReading:
    station_id: int
    name: str
    lat: float
    lon: float
    pm10: float | None
    pm25: float | None
    no2: float | None


@dataclass(frozen=True)
class EnvironmentalContext:
    timestamp: datetime  # tz-aware, Europe/Warsaw
    source: Literal["live", "scenario", "fallback", "mock"]
    temperature_c: float
    humidity_pct: float
    wind_ms: float  # at 10 m
    shortwave_wm2: float
    dni_wm2: float  # direct normal irradiance
    uv_index: float
    pm25: float  # city background after GIOŚ correction [µg/m³]
    pm10: float
    no2: float
    stations: tuple[StationReading, ...] = ()
    data_age_s: float = 0.0

    def summary(self) -> dict:
        out = {f.name: getattr(self, f.name) for f in fields(self) if f.name != "stations"}
        out["timestamp"] = self.timestamp.isoformat()
        return out


@dataclass
class EdgeExposure:
    """All arrays have shape (E,)."""

    utci_c: np.ndarray
    air_index: np.ndarray  # continuous EAQI 0..6
    pm25: np.ndarray  # µg/m³ on the edge
    uv_eff: np.ndarray
    discomfort: np.ndarray  # 0..1 (fuzzy / 10)
    reason: np.ndarray  # int8: -1 ok, 0 heat, 1 air, 2 uv


class EnvironmentServiceP(Protocol):
    def get(self, scenario: str, at: datetime | None) -> EnvironmentalContext: ...

    def scenarios(self) -> list[dict]: ...


# compute_edge_exposure(ctx, shade (E,), graph: RoutingGraphP, tree_frac (E,), profile: str) -> EdgeExposure
