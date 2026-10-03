"""MockGraph: synthetic 8-neighbour grid over Kraków with real Dijkstra (implements RoutingGraphP).

Stateless and thread-safe, so FASTEST and ECO really differ when costs differ. Replaced by Role 1's RoutingGraph.
"""
from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from ..contracts import NoRoute, PointOutsideArea, Route

BBOX = (19.79, 49.97, 20.22, 50.13)  # lon_min, lat_min, lon_max, lat_max (≈ Kraków)
STEP_M = 250.0
SNAP_MAX_M = 300.0
ARTERIAL_EVERY = 8  # every n-th grid row/column is a main road
JITTER = 0.3  # node offset as a fraction of the step: makes the fastest route unique, like a real street grid
M_PER_DEG_LAT = 111_320.0
_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


class MockGraph:
    def __init__(self, bbox: tuple[float, float, float, float] = BBOX, step_m: float = STEP_M, seed: int = 7):
        lon0, lat0, lon1, lat1 = bbox
        self._m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians((lat0 + lat1) / 2))
        self._dlat = step_m / M_PER_DEG_LAT
        self._dlon = step_m / self._m_per_deg_lon
        lats = np.arange(lat0, lat1 + 1e-9, self._dlat)
        lons = np.arange(lon0, lon1 + 1e-9, self._dlon)
        self._rows, self._cols = len(lats), len(lons)
        self.n_nodes = self._rows * self._cols
        jitter = np.random.default_rng(seed).uniform(-JITTER, JITTER, (2, self.n_nodes))
        self.node_lat = np.repeat(lats, self._cols) + jitter[0] * self._dlat
        self.node_lon = np.tile(lons, self._rows) + jitter[1] * self._dlon
        self._kd = cKDTree(np.column_stack([self.node_lon * self._m_per_deg_lon, self.node_lat * M_PER_DEG_LAT]))
        self._build_edges()

    # ---------- construction ----------
    def _build_edges(self) -> None:
        r, c = np.divmod(np.arange(self.n_nodes), self._cols)
        us, vs, horizontal, vertical = [], [], [], []
        for dr, dc in _NEIGHBOURS:
            rr, cc = r + dr, c + dc
            ok = (rr >= 0) & (rr < self._rows) & (cc >= 0) & (cc < self._cols)
            us.append(np.flatnonzero(ok))
            vs.append(rr[ok] * self._cols + cc[ok])
            horizontal.append(np.full(ok.sum(), dr == 0))
            vertical.append(np.full(ok.sum(), dc == 0))
        u, v = np.concatenate(us), np.concatenate(vs)
        order = np.lexsort((v, u))  # eid order == CSR slot order
        self.edge_u, self.edge_v = u[order], v[order]
        self.indices = self.edge_v
        self.indptr = np.searchsorted(self.edge_u, np.arange(self.n_nodes + 1))
        self.n_edges = len(self.edge_u)

        dx = (self.node_lon[self.edge_v] - self.node_lon[self.edge_u]) * self._m_per_deg_lon
        dy = (self.node_lat[self.edge_v] - self.node_lat[self.edge_u]) * M_PER_DEG_LAT
        self.edge_length_m = np.hypot(dx, dy)
        self.edge_mid_lonlat = np.column_stack([
            (self.node_lon[self.edge_u] + self.node_lon[self.edge_v]) / 2,
            (self.node_lat[self.edge_u] + self.node_lat[self.edge_v]) / 2,
        ])

        row, col = np.divmod(self.edge_u, self._cols)
        on_avenue = np.concatenate(horizontal)[order] & (row % ARTERIAL_EVERY == 0)
        on_street = np.concatenate(vertical)[order] & (col % ARTERIAL_EVERY == 0)
        self.edge_highway = np.where(on_avenue | on_street, "primary", "residential").astype(object)
        names = np.full(self.n_edges, None, dtype=object)
        names[on_avenue] = [f"Mock Avenue {k}" for k in row[on_avenue] // ARTERIAL_EVERY]
        names[on_street] = [f"Mock Street {k}" for k in col[on_street] // ARTERIAL_EVERY]
        self.edge_name = names

    # ---------- RoutingGraphP ----------
    def snap(self, lat: float, lon: float, index: int | None = None) -> int:
        d, node = self._kd.query((lon * self._m_per_deg_lon, lat * M_PER_DEG_LAT))
        if d > SNAP_MAX_M:
            raise PointOutsideArea(f"point {index} is {d:.0f} m from the bike network", index=index)
        return int(node)

    def route(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> Route:
        nodes = [self.snap(lat, lon, i) for i, (lat, lon) in enumerate(points)]
        _, pred = dijkstra(self._matrix(edge_cost), directed=True, indices=nodes[:-1], return_predecessors=True)
        pred = np.atleast_2d(pred)
        path = [nodes[0]]
        for k, (s, t) in enumerate(pairwise(nodes)):
            seg = [t]
            while seg[-1] != s:
                p = pred[k, seg[-1]]
                if p < 0:
                    raise NoRoute(f"no path between point {k} and {k + 1}")
                seg.append(int(p))
            path += seg[::-1][1:]
        eids = np.array([self._eid(a, b) for a, b in pairwise(path)], dtype=np.int64)
        return Route(eids=eids, node_path=np.asarray(path, dtype=np.int64))

    def geometry(self, eids: np.ndarray) -> list[list[float]]:
        eids = np.asarray(eids, dtype=np.int64)
        if len(eids) == 0:
            return []
        nodes = np.concatenate([self.edge_u[eids[:1]], self.edge_v[eids]])
        return np.column_stack([self.node_lon[nodes], self.node_lat[nodes]]).round(6).tolist()

    def coord_counts(self, eids: np.ndarray) -> np.ndarray:
        return np.full(len(eids), 2, dtype=np.int64)

    # ---------- optional capability (SupportsCostMatrix) ----------
    def cost_matrix(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> np.ndarray:
        nodes = [self.snap(lat, lon, i) for i, (lat, lon) in enumerate(points)]
        dist = dijkstra(self._matrix(edge_cost), directed=True, indices=nodes)
        return np.atleast_2d(dist)[:, nodes]

    # ---------- internals ----------
    def _matrix(self, edge_cost: np.ndarray) -> sp.csr_matrix:
        cost = np.asarray(edge_cost, dtype=np.float64)
        if cost.shape != (self.n_edges,):
            raise ValueError(f"edge_cost must have shape ({self.n_edges},), got {cost.shape}")
        w = np.maximum(cost, 1e-3)  # zero would mean "no edge" in CSR
        return sp.csr_matrix((w, self.indices, self.indptr), shape=(self.n_nodes, self.n_nodes))

    def _eid(self, a: int, b: int) -> int:
        lo, hi = self.indptr[a], self.indptr[a + 1]
        return int(lo + np.searchsorted(self.indices[lo:hi], b))
