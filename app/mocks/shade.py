"""MockShade: smooth, deterministic shade so ECO bends towards parks and the dense centre.

The sun curve is a rough approximation for the UI only; Role 3's ShadeModel uses pvlib.
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from ..contracts import SunPosition

CENTRE = (50.0614, 19.9366)  # Rynek Główny
PARKS = (  # (lat, lon, radius_m)
    (50.0614, 19.9366, 600),  # Planty
    (50.0600, 19.9080, 900),  # Błonia / Park Jordana
    (50.0540, 19.8500, 1500),  # Las Wolski
    (50.0800, 20.0350, 700),  # Łąki Nowohuckie
    (50.0350, 19.9550, 600),  # Park Bednarskiego
)
M_PER_DEG_LAT = 111_320.0


def _dist_m(lonlat: np.ndarray, lat: float, lon: float) -> np.ndarray:
    dx = (lonlat[:, 0] - lon) * M_PER_DEG_LAT * math.cos(math.radians(lat))
    dy = (lonlat[:, 1] - lat) * M_PER_DEG_LAT
    return np.hypot(dx, dy)


class MockShade:
    def __init__(self, graph):
        mid = np.asarray(graph.edge_mid_lonlat, dtype=np.float64)
        main_road = np.asarray(graph.edge_highway) == "primary"
        parks = np.max([np.exp(-((_dist_m(mid, lat, lon) / r) ** 2)) for lat, lon, r in PARKS], axis=0)
        x = (mid[:, 0] - CENTRE[1]) * M_PER_DEG_LAT * math.cos(math.radians(CENTRE[0]))
        y = (mid[:, 1] - CENTRE[0]) * M_PER_DEG_LAT
        leafy = 0.5 + 0.5 * np.sin(x / 700) * np.cos(y / 500)  # smooth mix of leafy and bare streets
        street_trees = np.where(main_road, 0.0, 0.45 * leafy)
        self.edge_tree_frac = np.clip(0.8 * parks + street_trees, 0, 1).astype(np.float32)
        density = np.exp(-((_dist_m(mid, *CENTRE) / 2500) ** 2))  # taller buildings near the centre
        self._canyon = (density * np.where(main_road, 0.3, 0.8)).astype(np.float32)

    def sun(self, at: datetime) -> SunPosition:
        doy = at.timetuple().tm_yday
        decl = 23.44 * math.sin(math.radians(360 * (doy - 81) / 365))
        noon = 12.7 if at.dst() else 11.7  # solar noon in Kraków, local time
        half_day = math.degrees(math.acos(-math.tan(math.radians(50.06)) * math.tan(math.radians(decl)))) / 15
        h = at.hour + at.minute / 60
        frac = (h - (noon - half_day)) / (2 * half_day)  # 0 at sunrise, 1 at sunset
        top = 90 - 50.06 + decl
        elevation = top * math.sin(math.pi * frac) if 0 <= frac <= 1 else -10.0
        azimuth = (90 + 180 * frac) % 360
        return SunPosition(azimuth_deg=round(azimuth, 1), elevation_deg=round(elevation, 1))

    def edge_shade(self, at: datetime) -> np.ndarray:
        elevation = self.sun(at).elevation_deg
        if elevation <= 0:
            return np.ones_like(self.edge_tree_frac)
        low_sun = 1 - min(elevation, 70) / 70  # long shadows when the sun is low
        return np.clip(self.edge_tree_frac + self._canyon * (0.3 + 0.7 * low_sun), 0, 1).astype(np.float32)
