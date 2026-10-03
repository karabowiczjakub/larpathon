"""Runtime lookup only: no GIS or network access."""

import hashlib
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.contracts import SunPosition
from app.shade.sun import sun_position, utc_time


class ShadeModel:
    @classmethod
    def load(cls, data_dir: str | Path, n_edges: int) -> "ShadeModel":
        path = Path(data_dir)
        with (path / "shade_bins.json").open() as stream:
            bins = json.load(stream)
        table = np.load(path / "shade.npy", allow_pickle=False)
        tree = np.load(path / "edge_tree_frac.npy", allow_pickle=False)
        if table.ndim != 3 or table.shape[0] != n_edges:
            raise ValueError("Shade belongs to another graph; run make shade")
        if "edges_sha256" in bins:
            with (path / "edges.parquet").open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != bins["edges_sha256"]:
                raise ValueError("Graph changed; run make shade")
        return cls(table, tree, bins["az"], bins["el"])

    def __init__(self, table, tree, az, el):
        table = np.asarray(table)
        tree = np.asarray(tree, dtype=np.float32)
        az, el = np.asarray(az, dtype=float), np.asarray(el, dtype=float)
        for name, values, lower, upper in (
            ("azimuth", az, 0, 360),
            ("elevation", el, 0, 90),
        ):
            if (
                values.ndim != 1
                or not len(values)
                or not np.isfinite(values).all()
                or np.any(np.diff(values) <= 0)
                or values[0] < lower
                or values[-1] >= upper
            ):
                raise ValueError(f"Invalid {name} bins")
        if el[0] <= 0:
            raise ValueError("Elevation bins must be above the horizon")
        if (
            table.ndim != 3
            or table.dtype != np.uint8
            or table.shape[1:] != (len(az), len(el))
        ):
            raise ValueError("Expected uint8 shade table (E, len(az), len(el))")
        if (
            tree.shape != (len(table),)
            or not np.isfinite(tree).all()
            or np.any((tree < 0) | (tree > 1))
        ):
            raise ValueError("Expected finite tree fractions (E,) in [0, 1]")
        # Each solar-bin slice is contiguous along eid for fast interpolation.
        self.table = table.copy(order="F")
        self.edge_tree_frac = tree.copy()
        self.az, self.el = az.copy(), el.copy()
        self._ones = np.ones(len(table), dtype=np.float32)
        for array in (self.table, self.edge_tree_frac, self.az, self.el, self._ones):
            array.setflags(write=False)
        # Caches belong to this immutable dataset, not to shared graph state.
        self._sun = lru_cache(maxsize=256)(sun_position)
        self._mix = lru_cache(maxsize=64)(self._interpolate)

    def sun(self, at: datetime) -> SunPosition:
        return self._sun(utc_time(at))

    def edge_shade(self, at: datetime) -> np.ndarray:
        sun = self.sun(at)
        if not np.isfinite([sun.azimuth_deg, sun.elevation_deg]).all():
            raise ValueError("Solar position must be finite")
        if sun.elevation_deg <= 0:
            return self._ones
        distance = np.abs((self.az - sun.azimuth_deg + 180) % 360 - 180)
        i = int(distance.argmin())
        elevation = float(np.clip(sun.elevation_deg, self.el[0], self.el[-1]))
        j1 = min(int(np.searchsorted(self.el, elevation)), len(self.el) - 1)
        j0 = max(j1 - 1, 0)
        weight = (
            0.0 if j0 == j1 else (elevation - self.el[j0]) / (self.el[j1] - self.el[j0])
        )
        return self._mix(i, j0, j1, float(weight))

    def _interpolate(self, i: int, j0: int, j1: int, weight: float) -> np.ndarray:
        a = self.table[:, i, j0].astype(np.float32)
        b = self.table[:, i, j1].astype(np.float32)
        result = np.clip((a + weight * (b - a)) / 255, 0, 1)
        result.setflags(write=False)
        return result
