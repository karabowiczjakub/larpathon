import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.sparse import csr_matrix

from app.contracts import NoRoute, PointOutsideArea
from app.graph.routing import RoutingGraph
from scripts.demo_routing import compare_routes


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.points = [
            (50.06, 19.94),
            (50.06, 19.941),
            (50.061, 19.94),
            (50.061, 19.941),
            (50.062, 19.94),
        ]
        lon, lat = np.array(self.points).T[::-1]
        x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
        u, v = np.array([0, 0, 1, 2]), np.array([1, 2, 3, 3])
        base = csr_matrix((np.arange(1, 5), (u, v)), shape=(5, 5))
        self.z = {
            "indptr": base.indptr,
            "indices": base.indices,
            "perm": base.data - 1,
            "node_x": x,
            "node_y": y,
            "node_lon": lon,
            "node_lat": lat,
            "edge_u": u,
            "edge_v": v,
            "edge_length_m": np.array([10, 15, 10, 15]),
            "edge_mid_lon": (lon[u] + lon[v]) / 2,
            "edge_mid_lat": (lat[u] + lat[v]) / 2,
        }
        self.gc = {
            "coords": np.array([[lon[n], lat[n]] for pair in zip(u, v) for n in pair]),
            "offs": np.arange(0, 9, 2),
        }
        self.meta = pd.DataFrame(
            {
                "eid": [3, 1, 0, 2],
                "highway": ["residential"] * 4,
                "name": ["three", "one", "zero", None],
                "u": [2, 0, 0, 1],
                "v": [3, 2, 1, 3],
                "length_m": [15, 15, 10, 10],
            }
        )
        self.g = RoutingGraph(self.z, self.gc, self.meta)

    def test_costs_and_geometry(self):
        r = self.g.route([self.points[0], self.points[3]], np.array([1, 2, 1, 2]))
        np.testing.assert_array_equal(r.eids, [0, 2])
        np.testing.assert_array_equal(r.node_path, [0, 1, 3])
        np.testing.assert_allclose(
            self.g.geometry(r.eids), np.array(self.points)[[0, 1, 3], ::-1]
        )
        np.testing.assert_array_equal(self.g.coord_counts(r.eids), [2, 2])
        self.assertEqual(self.g.edge_name[0], "zero")
        eco = self.g.route([self.points[0], self.points[3]], np.array([10, 1, 10, 1]))
        np.testing.assert_array_equal(eco.eids, [1, 3])

    def test_via_and_identical_points(self):
        r = self.g.route(
            [
                self.points[0],
                self.points[0],
                self.points[2],
                self.points[2],
                self.points[3],
            ],
            np.ones(4),
        )
        np.testing.assert_array_equal(r.node_path, [0, 2, 3])
        empty = self.g.route([self.points[0]] * 2, np.ones(4))
        self.assertEqual(empty.eids.size, 0)
        self.assertEqual(self.g.geometry(empty.eids), [])

    def test_direction_and_disconnected(self):
        for a, b in [(3, 0), (0, 4)]:
            with self.assertRaises(NoRoute):
                self.g.route([self.points[a], self.points[b]], np.ones(4))

    def test_snap_limit_and_index(self):
        to_geo = Transformer.from_crs(2180, 4326, always_xy=True)
        for distance in [299, 301]:
            lon, lat = to_geo.transform(
                self.z["node_x"][0] - distance, self.z["node_y"][0]
            )
            if distance == 299:
                self.assertEqual(self.g.snap(lat, lon), 0)
            else:
                with self.assertRaises(PointOutsideArea) as caught:
                    self.g.route([self.points[0], (lat, lon)], np.ones(4))
                self.assertEqual(caught.exception.index, 1)
        with self.assertRaises(PointOutsideArea) as caught:
            self.g.route([self.points[0], (0, -70)], np.ones(4))
        self.assertEqual(caught.exception.index, 1)
        for lat, lon in [(np.nan, 19.94), (91, 19.94), (50, 181)]:
            with self.subTest(lat=lat, lon=lon), self.assertRaises(ValueError):
                self.g.snap(lat, lon)

    def test_zero_costs_and_validation(self):
        r = self.g.route([self.points[0], self.points[3]], np.array([0, 1, 0, 1]))
        np.testing.assert_array_equal(r.eids, [0, 2])
        for cost in [
            np.ones(3),
            [-1, 1, 1, 1],
            [np.nan, 1, 1, 1],
            [np.inf] * 4,
            np.array([1 + 2j] * 4),
        ]:
            with self.assertRaises(ValueError):
                self.g.route(self.points[:2], cost)
        for points in [[], self.points * 2]:
            with self.assertRaises(ValueError):
                self.g.route(points, np.ones(4))

    def test_load_and_eid_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            np.savez(root / "graph.npz", **self.z)
            np.savez(root / "edge_coords.npz", **self.gc)
            self.meta.to_parquet(root / "edges.parquet")
            loaded = RoutingGraph.load(directory)
            np.testing.assert_array_equal(loaded.edge_name, self.g.edge_name)
        with self.assertRaises(ValueError):
            RoutingGraph(self.z, self.gc, self.meta.assign(eid=0))
        for column in ("u", "v", "length_m"):
            with self.subTest(column=column), self.assertRaises(ValueError):
                RoutingGraph(self.z, self.gc, self.meta.assign(**{column: 0}))

    def test_rejects_mismatched_artifacts(self):
        variants = [
            ("perm", self.z["perm"][::-1]),
            ("indices", np.array([1, 2, 3, 5])),
            ("edge_length_m", np.array([0, 1, 1, 1])),
            ("edge_u", np.array([1, 0, 1, 2])),
            ("indptr", np.array([0, 2, 1, 4, 4, 4])),
            ("node_lon", np.full(5, np.nan)),
        ]
        for key, value in variants:
            with self.subTest(key=key), self.assertRaises(ValueError):
                RoutingGraph({**self.z, key: value}, self.gc, self.meta)
        for key, value in [
            ("offs", np.array([0, 2, 4, 6, 9])),
            ("coords", self.gc["coords"][::-1]),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                RoutingGraph(self.z, {**self.gc, key: value}, self.meta)

    def test_geometry_rejects_invalid_edge_paths(self):
        for eids in [[-1], [4], [0.5], [[0]], [0, 3]]:
            with self.subTest(eids=eids), self.assertRaises(ValueError):
                self.g.geometry(eids)
        np.testing.assert_array_equal(self.g.coord_counts([]), [])

    def test_identical_points_skip_dijkstra(self):
        with patch(
            "app.graph.routing.dijkstra",
            side_effect=AssertionError("unexpected search"),
        ):
            r = self.g.route([self.points[0]] * 5, np.ones(4))
        np.testing.assert_array_equal(r.node_path, [0])
        self.assertEqual(r.eids.dtype, np.int64)

    def test_concurrent_cost_vectors_remain_independent(self):
        original = {key: value.copy() for key, value in self.z.items()}
        costs = [np.array([1, 5, 1, 5]), np.array([5, 1, 5, 1])] * 12

        def run(cost):
            return self.g.route([self.points[0], self.points[3]], cost).eids

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(run, costs))
        for cost, result in zip(costs, results):
            np.testing.assert_array_equal(result, [0, 2] if cost[0] == 1 else [1, 3])
        for key, value in original.items():
            np.testing.assert_array_equal(self.z[key], value)

    def test_backend_cost_formula_and_comparison(self):
        report = compare_routes(
            self.g, [self.points[0], self.points[3]], np.array([1, 0, 1, 0])
        )
        fastest, eco = [feature["properties"] for feature in report["features"]]
        self.assertEqual(fastest["distance_m"], 20)
        self.assertEqual(eco["distance_m"], 30)
        self.assertLess(eco["exposure_s"], fastest["exposure_s"])
        self.assertFalse(report["same_route"])
        empty = compare_routes(self.g, [self.points[0]] * 2, np.zeros(4))
        self.assertTrue(empty["same_route"])
        for feature in empty["features"]:
            self.assertEqual(len(feature["geometry"]["coordinates"]), 2)
            self.assertEqual(feature["properties"]["time_s"], 0)
        for score in [
            np.ones(3),
            np.full(4, np.nan),
            np.full(4, 1.1),
            np.array([1j] * 4),
        ]:
            with self.assertRaises(ValueError):
                compare_routes(self.g, self.points[:2], score)
