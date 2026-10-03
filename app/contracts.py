from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
import numpy as np

# ---------- Rola 2: Environment ----------
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
    timestamp: datetime                 # tz-aware, Europe/Warsaw — chwila, której dotyczą dane
    source: Literal["live", "scenario", "fallback", "mock"]
    temperature_c: float
    humidity_pct: float
    wind_ms: float                      # 10 m n.p.t.
    shortwave_wm2: float
    dni_wm2: float                      # direct normal irradiance
    uv_index: float
    pm25: float                         # tło miejskie po korekcie GIOŚ [µg/m³]
    pm10: float
    no2: float
    stations: tuple[StationReading, ...] = ()
    data_age_s: float = 0.0

    def summary(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "stations"}
        d["timestamp"] = self.timestamp.isoformat()
        return d

@dataclass
class EdgeExposure:                     # wszystkie tablice (E,)
    utci_c: np.ndarray
    air_index: np.ndarray               # ciągły EAQI 0..6
    pm25: np.ndarray                    # µg/m³ na krawędzi
    uv_eff: np.ndarray
    discomfort: np.ndarray              # 0..1 (fuzzy/10)
    reason: np.ndarray                  # int8: -1 ok, 0 heat, 1 air, 2 uv

class EnvironmentServiceP(Protocol):
    def get(self, scenario: str, at: datetime | None) -> EnvironmentalContext: ...
    def scenarios(self) -> list[dict]: ...

# ---------- Rola 3: Shade + Sun ----------
@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float                  # od północy, zgodnie z zegarem
    elevation_deg: float                # < 0 = noc

class ShadeModelP(Protocol):
    edge_tree_frac: np.ndarray          # (E,)
    def sun(self, at: datetime) -> SunPosition: ...
    def edge_shade(self, at: datetime) -> np.ndarray: ...   # (E,) float32 0..1

# ---------- Rola 1: Graph + Routing ----------
@dataclass
class Route:
    eids: np.ndarray                    # int64, kolejne krawędzie trasy
    node_path: np.ndarray

class RoutingGraphP(Protocol):
    n_edges: int
    edge_length_m: np.ndarray           # (E,)
    edge_mid_lonlat: np.ndarray         # (E, 2)
    edge_highway: np.ndarray            # (E,) object/str
    edge_name: np.ndarray               # (E,) object/str|None
    def snap(self, lat: float, lon: float) -> int: ...                     # raises PointOutsideArea
    def route(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> Route: ...  # raises NoRoute
    def geometry(self, eids: np.ndarray) -> list[list[float]]: ...         # [[lon, lat], ...]
    def coord_counts(self, eids: np.ndarray) -> np.ndarray: ...

class PointOutsideArea(Exception): ...
class NoRoute(Exception): ...
