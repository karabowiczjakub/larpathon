import unittest
from pathlib import Path

import numpy as np

from app.graph.routing import RoutingGraph


@unittest.skipUnless(
    Path("data/processed/graph.npz").exists(), "city artifacts missing"
)
class CityGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = RoutingGraph.load("data/processed")

    def test_reference_routes_and_geometry(self):
        points = [(50.0614, 19.9366), (50.0647, 19.9450), (50.0540, 19.9350)]
        r = self.g.route(points, self.g.edge_length_m)
        self.assertGreater(r.eids.size, 0)
        np.testing.assert_array_equal(
            self.g.edge_v[r.eids[:-1]], self.g.edge_u[r.eids[1:]]
        )
        for lat, lon in points:
            self.assertIn(self.g.snap(lat, lon), r.node_path)
        coords = np.asarray(self.g.geometry(r.eids))
        self.assertEqual(
            len(coords), self.g.coord_counts(r.eids).sum() - len(r.eids) + 1
        )
        for eid in r.eids:
            start, end = (
                self.g.coords[self.g.offs[eid]],
                self.g.coords[self.g.offs[eid + 1] - 1],
            )
            np.testing.assert_allclose(
                start, self.g.node_lonlat[self.g.edge_u[eid]], atol=2e-6, rtol=0
            )
            np.testing.assert_allclose(
                end, self.g.node_lonlat[self.g.edge_v[eid]], atol=2e-6, rtol=0
            )

    def test_shortest_route_remains_minimal(self):
        pts = [(50.0614, 19.9366), (50.0675, 19.9128)]
        shortest = self.g.route(pts, self.g.edge_length_m)
        weighted = self.g.route(
            pts,
            self.g.edge_length_m
            * np.random.default_rng(0).uniform(1, 3, self.g.n_edges),
        )
        self.assertLessEqual(
            self.g.edge_length_m[shortest.eids].sum(),
            self.g.edge_length_m[weighted.eids].sum() + 1e-6,
        )
