from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from pyproj import Transformer
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from ..contracts import NoRoute, PointOutsideArea, Route

SNAP_MAX_M = 300.0
_to2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)


class RoutingGraph:
    @classmethod
    def load(cls, data_dir: str) -> RoutingGraph:
        root = Path(data_dir)
        manifest_path = root / "graph_manifest.json"
        manifest = None
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["format_version"] != 1:
                raise ValueError("unsupported artifact version")
            for name in ("graph.npz", "edges.parquet", "edge_coords.npz"):
                with (root / name).open("rb") as artifact:
                    if (
                        hashlib.file_digest(artifact, "sha256").hexdigest()
                        != manifest["sha256"][name]
                    ):
                        raise ValueError(f"artifact checksum mismatch: {name}")
        with (
            np.load(f"{data_dir}/graph.npz") as z,
            np.load(f"{data_dir}/edge_coords.npz") as gc,
        ):
            graph = cls(
                z,
                gc,
                pd.read_parquet(
                    f"{data_dir}/edges.parquet",
                    columns=["eid", "u", "v", "length_m", "highway", "name"],
                ),
            )
        if manifest is not None and (graph.N, graph.n_edges) != (
            manifest["nodes"],
            manifest["edges"],
        ):
            raise ValueError("manifest graph size mismatch")
        return graph

    def __init__(
        self,
        z: Mapping[str, np.ndarray],
        gc: Mapping[str, np.ndarray],
        meta: pd.DataFrame,
    ):
        meta = meta.sort_values("eid")
        if not np.array_equal(meta["eid"], np.arange(len(z["edge_length_m"]))):
            raise ValueError("metadata must contain every eid exactly once")
        self.indptr, self.indices, self.perm = z["indptr"], z["indices"], z["perm"]
        self.N = len(self.indptr) - 1
        self.n_edges = len(z["edge_length_m"])
        self.edge_length_m = z["edge_length_m"].astype(np.float64)
        self.edge_u, self.edge_v = z["edge_u"], z["edge_v"]
        self.node_lonlat = np.column_stack([z["node_lon"], z["node_lat"]])
        self.edge_mid_lonlat = np.column_stack([z["edge_mid_lon"], z["edge_mid_lat"]])
        self.edge_highway = meta["highway"].astype(object).to_numpy()
        self.edge_name = (
            meta["name"].astype(object).where(meta["name"].notna(), None).to_numpy()
        )
        self.coords, self.offs = gc["coords"], gc["offs"]
        self.kd = cKDTree(np.column_stack([z["node_x"], z["node_y"]]))
        if not np.array_equal(np.sort(self.perm), np.arange(self.n_edges)):
            raise ValueError("CSR permutation must contain every eid exactly once")
        self._validate()
        for column, expected in (("u", self.edge_u), ("v", self.edge_v)):
            if column in meta and not np.array_equal(meta[column], expected):
                raise ValueError(f"parquet {column} endpoints do not match graph.npz")
        if "length_m" in meta and not np.allclose(
            meta["length_m"], self.edge_length_m, rtol=1e-6, atol=1e-6
        ):
            raise ValueError("parquet edge lengths do not match graph.npz")

    def _validate(self) -> None:
        if self.N < 1:
            raise ValueError("graph must contain nodes")
        if self.kd.n != self.N:
            raise ValueError("projected coordinates do not match CSR node count")
        for name in ("indptr", "indices", "perm", "edge_u", "edge_v", "offs"):
            array = getattr(self, name)
            if array.ndim != 1 or array.dtype.kind not in "iu":
                raise ValueError(f"{name} must be a one-dimensional integer array")
        if (
            self.indptr[0] != 0
            or self.indptr[-1] != self.n_edges
            or (np.diff(self.indptr.astype(np.int64)) < 0).any()
            or self.indices.shape != (self.n_edges,)
        ):
            raise ValueError("invalid CSR offsets or edge count")
        for name in ("edge_u", "edge_v", "edge_length_m", "edge_highway", "edge_name"):
            if getattr(self, name).shape != (self.n_edges,):
                raise ValueError(f"{name} must have one entry per eid")
        if (self.edge_length_m <= 0).any() or not np.isfinite(self.edge_length_m).all():
            raise ValueError("edge lengths must be finite and positive")
        if any(
            (a >= self.N).any() or (a < 0).any()
            for a in (self.indices, self.edge_u, self.edge_v)
        ):
            raise ValueError("edge endpoint outside node range")
        rows = np.repeat(np.arange(self.N), np.diff(self.indptr))
        if not np.array_equal(rows, self.edge_u[self.perm]) or not np.array_equal(
            self.indices, self.edge_v[self.perm]
        ):
            raise ValueError("CSR slots do not match eid endpoints")
        same_row = rows[1:] == rows[:-1]
        if (same_row & (self.indices[1:] <= self.indices[:-1])).any():
            raise ValueError("CSR neighbors must be sorted and unique")
        if (
            self.offs.shape != (self.n_edges + 1,)
            or self.offs[0] != 0
            or self.offs[-1] != len(self.coords)
            or (np.diff(self.offs.astype(np.int64)) < 2).any()
        ):
            raise ValueError("invalid edge geometry offsets")
        for name, shape in (
            ("node_lonlat", (self.N, 2)),
            ("edge_mid_lonlat", (self.n_edges, 2)),
            ("coords", (len(self.coords), 2)),
        ):
            array = getattr(self, name)
            if array.shape != shape or not np.isfinite(array).all():
                raise ValueError(f"invalid {name} coordinates")
            if (np.abs(array[:, 0]) > 180).any() or (np.abs(array[:, 1]) > 90).any():
                raise ValueError(f"{name} must contain WGS84 lon/lat")
        if not np.allclose(
            self.coords[self.offs[:-1]],
            self.node_lonlat[self.edge_u],
            atol=3e-6,
            rtol=0,
        ) or not np.allclose(
            self.coords[self.offs[1:] - 1],
            self.node_lonlat[self.edge_v],
            atol=3e-6,
            rtol=0,
        ):
            raise ValueError("edge geometries must follow directed endpoints")

    # --- snap ---
    def snap(self, lat: float, lon: float, index: int | None = None) -> int:
        if not np.isfinite([lat, lon]).all() or not (
            -90 <= lat <= 90 and -180 <= lon <= 180
        ):
            raise ValueError("invalid latitude/longitude")
        x, y = _to2180.transform(lon, lat)
        if np.isfinite([x, y]).all():
            d, i = self.kd.query((x, y))
        else:
            d, i = float("inf"), 0
        if d > SNAP_MAX_M:
            e = PointOutsideArea(f"point {index} is {d:.0f} m from the bike network")
            e.index = index
            raise e
        return int(i)

    # --- macierz kosztów: tylko podmiana wektora data (struktura CSR stała) ---
    def _matrix(self, edge_cost: np.ndarray) -> sp.csr_matrix:
        w = edge_cost[self.perm]  # Explicit CSR entries preserve zero-cost edges.
        return sp.csr_matrix((w, self.indices, self.indptr), shape=(self.N, self.N))

    def _edge_id(self, a: int, b: int) -> int:
        lo, hi = self.indptr[a], self.indptr[a + 1]
        k = np.flatnonzero(self.indices[lo:hi] == b)[0]
        return int(self.perm[lo + k])

    # --- trasa przez punkty (A, via..., B) jednym wywołaniem Dijkstry ---
    def route(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> Route:
        if not 2 <= len(points) <= 5:
            raise ValueError("route requires 2 to 5 points")
        if np.iscomplexobj(edge_cost):
            raise ValueError("edge costs must be real numbers")
        edge_cost = np.asarray(edge_cost, dtype=np.float64)
        if (
            edge_cost.shape != (self.n_edges,)
            or not np.isfinite(edge_cost).all()
            or (edge_cost < 0).any()
        ):
            raise ValueError("cost must contain one finite nonnegative value per eid")
        nodes = [self.snap(lat, lon, i) for i, (lat, lon) in enumerate(points)]
        sources = sorted({a for a, b in pairwise(nodes) if a != b})
        if not sources:
            return Route(
                eids=np.empty(0, dtype=np.int64),
                node_path=np.array(nodes[:1], dtype=np.int64),
            )
        M = self._matrix(edge_cost)
        _, pred = dijkstra(M, directed=True, indices=sources, return_predecessors=True)
        pred = np.atleast_2d(pred)
        source_rows = {source: row for row, source in enumerate(sources)}
        path = [nodes[0]]
        for k in range(len(nodes) - 1):
            s, t = nodes[k], nodes[k + 1]
            if s == t:
                continue
            seg = [t]
            while seg[-1] != s:
                p = pred[source_rows[s], seg[-1]]
                if p < 0:
                    raise NoRoute(f"no path between point {k} and {k + 1}")
                seg.append(p)
            path += seg[::-1][1:]
        path = np.asarray(path)
        eids = np.array(
            [self._edge_id(a, b) for a, b in pairwise(path)], dtype=np.int64
        )
        return Route(eids=eids, node_path=path)

    # --- geometria do API ---
    def geometry(self, eids: np.ndarray) -> list[list[float]]:
        eids = self._validate_eids(eids)
        if len(eids) == 0:
            return []
        if not np.array_equal(self.edge_v[eids[:-1]], self.edge_u[eids[1:]]):
            raise ValueError("geometry requires a continuous directed edge path")
        parts = [self.coords[self.offs[e] : self.offs[e + 1]] for e in eids]
        out = np.vstack(
            [parts[0]] + [p[1:] for p in parts[1:]]
        )  # bez dublowania węzłów
        return np.round(out.astype(np.float64), 6).tolist()

    def coord_counts(self, eids: np.ndarray) -> np.ndarray:
        eids = self._validate_eids(eids)
        return (self.offs[eids + 1] - self.offs[eids]).astype(np.int64)

    def _validate_eids(self, eids: np.ndarray) -> np.ndarray:
        eids = np.asarray(eids)
        if eids.ndim != 1 or (eids.size and eids.dtype.kind not in "iu"):
            raise ValueError("eids must be a one-dimensional integer array")
        if (eids < 0).any() or (eids >= self.n_edges).any():
            raise ValueError("eid outside edge range")
        return eids.astype(np.int64, copy=False)
