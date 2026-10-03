import itertools
import unittest

import networkx as nx
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.sparse import csr_matrix

from app.graph.routing import RoutingGraph


class RoutingOracleTests(unittest.TestCase):
    def test_random_directed_graphs_match_bellman_ford(self):
        for seed in range(12):
            rng = np.random.default_rng(seed)
            count = 9
            xy = np.array(
                [[567000 + 60 * (i % 3), 244000 + 60 * (i // 3)] for i in range(count)]
            )
            lon, lat = Transformer.from_crs(2180, 4326, always_xy=True).transform(*xy.T)
            pairs = {(i, (i + 1) % count) for i in range(count)}
            pairs.update((int(u), int(v)) for u, v in rng.integers(0, count, (30, 2)))
            u, v = np.array(sorted(pairs)).T
            size = len(u)
            csr = csr_matrix((np.arange(1, size + 1), (u, v)), shape=(count, count))
            z = {
                "indptr": csr.indptr,
                "indices": csr.indices,
                "perm": csr.data - 1,
                "node_x": xy[:, 0],
                "node_y": xy[:, 1],
                "node_lon": lon,
                "node_lat": lat,
                "edge_u": u,
                "edge_v": v,
                "edge_length_m": np.ones(size),
                "edge_mid_lon": (lon[u] + lon[v]) / 2,
                "edge_mid_lat": (lat[u] + lat[v]) / 2,
            }
            gc = {
                "coords": np.array(
                    [[lon[n], lat[n]] for pair in zip(u, v) for n in pair]
                ),
                "offs": np.arange(0, size * 2 + 1, 2),
            }
            meta = pd.DataFrame(
                {
                    "eid": np.arange(size),
                    "highway": ["test"] * size,
                    "name": [None] * size,
                }
            )
            routing = RoutingGraph(z, gc, meta)
            points = np.column_stack([lat, lon])
            for n_points in range(2, 6):
                nodes = rng.integers(0, count, n_points)
                for zero_cost in [False, True]:
                    costs = np.zeros(size) if zero_cost else rng.integers(0, 10, size)
                    oracle = nx.DiGraph()
                    oracle.add_weighted_edges_from(
                        (int(a), int(b), float(cost)) for a, b, cost in zip(u, v, costs)
                    )
                    expected = sum(
                        nx.bellman_ford_path_length(oracle, int(a), int(b))
                        for a, b in itertools.pairwise(nodes)
                    )
                    result = routing.route(points[nodes].tolist(), costs)
                    with self.subTest(
                        seed=seed, n_points=n_points, zero_cost=zero_cost
                    ):
                        self.assertEqual(float(costs[result.eids].sum()), expected)
                        self.assertEqual(result.node_path[0], nodes[0])
                        self.assertEqual(result.node_path[-1], nodes[-1])
                        np.testing.assert_array_equal(
                            routing.edge_u[result.eids], result.node_path[:-1]
                        )
                        np.testing.assert_array_equal(
                            routing.edge_v[result.eids], result.node_path[1:]
                        )
