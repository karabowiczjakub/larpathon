"""Shared contracts between roles (source of truth: roles/04_backend_integration.md, section 4).

Every per-edge array has length E and follows the `eid` order of data/processed/edges.parquet.
Change these types only after announcing it to the whole team.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Literal, Protocol

import numpy as np


class PointOutsideArea(Exception):
    """A point is farther than 300 m from the bike network or outside Kraków."""

    def __init__(self, message: str = "point outside the routing area", index: int | None = None):
        super().__init__(message)
        self.index = index


class NoRoute(Exception):
    """The graph has no path between two consecutive points."""


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
class WeatherPoint:
    """Local weather against the city value at one point of a regular grid (weather model, ~2 km)."""

    lat: float
    lon: float
    dt_c: float  # temperature here minus the city temperature [°C]
    wind_ratio: float  # wind speed here / the city wind speed


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
    weather_grid: tuple[WeatherPoint, ...] = ()  # empty: the same weather in the whole city

    def summary(self) -> dict:
        out = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in {"stations", "weather_grid"}}
        out["timestamp"] = self.timestamp.isoformat()
        return out


@dataclass(frozen=True)
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


class ExposureFn(Protocol):
    def __call__(
        self,
        ctx: EnvironmentalContext,
        shade: np.ndarray,
        graph: RoutingGraphP,
        tree_frac: np.ndarray,
        profile: str,
    ) -> EdgeExposure: ...


# ---------- Role 3: Shade + Sun ----------
@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float  # from north, clockwise
    elevation_deg: float  # < 0 means night


class ShadeModelP(Protocol):
    edge_tree_frac: np.ndarray  # (E,)

    def sun(self, at: datetime) -> SunPosition: ...

    def edge_shade(self, at: datetime) -> np.ndarray: ...  # (E,) float32 0..1


# ---------- Role 1: Graph + Routing ----------
@dataclass(frozen=True)
class Route:
    eids: np.ndarray  # int64, consecutive edges of the route
    node_path: np.ndarray


class RoutingGraphP(Protocol):
    n_edges: int
    edge_length_m: np.ndarray  # (E,)
    edge_mid_lonlat: np.ndarray  # (E, 2)
    edge_highway: np.ndarray  # (E,) str
    edge_name: np.ndarray  # (E,) str | None

    def snap(self, lat: float, lon: float, index: int | None = None) -> int: ...  # raises PointOutsideArea

    def route(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> Route: ...  # raises NoRoute

    def geometry(self, eids: np.ndarray) -> list[list[float]]: ...  # [[lon, lat], ...]

    def coord_counts(self, eids: np.ndarray) -> np.ndarray: ...  # geometry points per edge


class SupportsCostMatrix(Protocol):
    """Optional Role 1 capability used by "optimize order"; without it Backend uses straight-line distances."""

    def cost_matrix(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> np.ndarray: ...
