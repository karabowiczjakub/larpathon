import json
import tempfile
import unittest
from pathlib import Path
from time import perf_counter

from src.graph import Edge, Graph, NoRoute
from src.pareto import knee, nondominated
from src.router_fast import route, sweep


def demo_graph() -> tuple[Graph, dict]:
    nodes = {
        0: (19.93, 50.06),
        1: (19.94, 50.06),
        2: (19.94, 50.07),
        3: (19.95, 50.06),
        4: (19.96, 50.06),
    }
    specs = [
        (0, 1, 0, 100, 10, 9),
        (0, 1, 1, 120, 12, 1),
        (1, 3, 0, 100, 10, 9),
        (0, 2, 0, 150, 15, 1),
        (2, 3, 0, 150, 15, 1),
    ]
    edges = [
        Edge(u, v, key, length, time, (nodes[u], nodes[v]))
        for u, v, key, length, time, _ in specs
    ]
    return Graph(nodes, edges), {
        (u, v, key): d for u, v, key, _, _, d in specs
    }


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.graph, self.discomfort = demo_graph()
        self.start = self.graph.nodes[0]
        self.end = self.graph.nodes[3]

    def test_fastest_and_eco(self):
        fastest = route(self.graph, self.start, self.end, self.discomfort)
        eco = route(self.graph, self.start, self.end, self.discomfort, 1)
        self.assertEqual(fastest.edge_ids, ((0, 1, 0), (1, 3, 0)))
        self.assertEqual(eco.edge_ids, ((0, 2, 0), (2, 3, 0)))
        self.assertEqual((fastest.time_s, fastest.exposure), (20, 180))
        self.assertEqual((eco.time_s, eco.exposure), (30, 30))
        self.assertEqual(eco.distance_m, 300)
        self.assertEqual(eco.discomfort_avg, 1)
        self.assertEqual(eco.geometry["coordinates"][0], list(self.start))
        self.assertEqual(eco.geometry["coordinates"][-1], list(self.end))
        self.assertEqual(len(eco.coordinates), 3)

    def test_parallel_edge_identity(self):
        fastest = route(
            self.graph, self.start, self.graph.nodes[1], self.discomfort
        )
        eco = route(
            self.graph, self.start, self.graph.nodes[1], self.discomfort, 1
        )
        self.assertEqual(fastest.edge_ids, ((0, 1, 0),))
        self.assertEqual(eco.edge_ids, ((0, 1, 1),))

    def test_no_route_and_direction(self):
        for end in (self.graph.nodes[4], self.start):
            with self.assertRaises(NoRoute):
                route(self.graph, self.end, end, self.discomfort)

    def test_same_node(self):
        result = route(self.graph, self.start, self.start, self.discomfort)
        self.assertEqual(result.edge_ids, ())
        self.assertEqual(result.time_s, 0)
        self.assertEqual(result.discomfort_avg, 0)
        self.assertEqual(len(result.geometry["coordinates"]), 2)

    def test_zero_discomfort(self):
        scores = dict.fromkeys(self.graph.edges, 0.0)
        result = route(self.graph, self.start, self.end, scores, 1)
        self.assertEqual(result.exposure, 0)
        self.assertEqual(result.coordinates[-1], self.end)

    def test_weights_against_all_possible_routes(self):
        paths = [
            ((0, 1, 0), (1, 3, 0)),
            ((0, 1, 1), (1, 3, 0)),
            ((0, 2, 0), (2, 3, 0)),
        ]
        mean = sum(self.discomfort.values()) / len(self.discomfort)
        for lam in (0, .1, .2, .35, .5, .65, .8, .9, 1):
            def cost(path, weight=lam):
                return sum(
                    self.graph.edges[e].time_s
                    * (1 - weight + weight * self.discomfort[e] / mean)
                    for e in path
                )

            result = route(
                self.graph, self.start, self.end, self.discomfort, lam
            )
            self.assertAlmostEqual(
                cost(result.edge_ids), min(cost(path) for path in paths)
            )

    def test_curved_geometry_and_zero_cost_cycle(self):
        nodes = {0: (19.93, 50.06), 1: (19.94, 50.06)}
        bend = (19.935, 50.065)
        edges = [
            Edge(0, 0, 0, 10, 1, (nodes[0], nodes[0])),
            Edge(0, 1, 0, 100, 10, (nodes[0], bend, nodes[1])),
        ]
        graph = Graph(nodes, edges)
        result = route(
            graph, nodes[0], nodes[1], dict.fromkeys(graph.edges, 0.0), 1
        )
        self.assertEqual(result.edge_ids, ((0, 1, 0),))
        self.assertEqual(result.coordinates, (nodes[0], bend, nodes[1]))

    def test_invalid_inputs(self):
        for value in (-1, 11, float("nan"), float("inf")):
            scores = dict(self.discomfort)
            scores[(0, 1, 0)] = value
            with self.assertRaises(ValueError):
                route(self.graph, self.start, self.end, scores)
        with self.assertRaises(ValueError):
            route(self.graph, (200, 50), self.end, self.discomfort)
        with self.assertRaises(ValueError):
            route(self.graph, self.start, self.end, self.discomfort, -1)
        with self.assertRaises(ValueError):
            route(self.graph, self.start, self.end, {})
        with self.assertRaises(ValueError):
            self.graph.shortest(0, 3, dict.fromkeys(self.graph.edges, -1))
        with self.assertRaises(ValueError):
            Graph(self.graph.nodes, [self.graph.edges[(0, 1, 0)]] * 2)
        with self.assertRaises(ValueError):
            Graph(self.graph.nodes, [Edge(0, 1, 0, 100, -1, ())])

    def test_load(self):
        data = {
            "nodes": self.graph.nodes,
            "edges": [
                {
                    "u": e.u, "v": e.v, "key": e.key,
                    "length_m": e.length_m, "time_s": e.time_s,
                    "coordinates": e.coordinates,
                }
                for e in self.graph.edges.values()
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            loaded = Graph.load(path)
        self.assertEqual(loaded.edges, self.graph.edges)

    def test_sweep_three_compromises(self):
        nodes = {0: self.start, 1: self.end}
        edges = [
            Edge(0, 1, key, time * 10, time, (self.start, self.end))
            for key, time in enumerate((20, 25, 30))
        ]
        graph = Graph(nodes, edges)
        scores = {(0, 1, 0): 9, (0, 1, 1): 3, (0, 1, 2): 1}
        result = sweep(graph, self.start, self.end, scores)
        self.assertEqual(len(result.front), 3)
        self.assertEqual(list(result.routes), [
            "fastest", "balanced", "cleanest",
        ])
        for name, key in (("fastest", 0), ("balanced", 1), ("cleanest", 2)):
            self.assertEqual(result.routes[name].edge_ids, ((0, 1, key),))
        self.assertEqual(
            [(r.time_s, r.exposure) for r in result.front],
            [(20, 180), (25, 75), (30, 30)],
        )

    def test_sweep_one_or_two_routes(self):
        result = sweep(
            self.graph, self.start, self.graph.nodes[1], self.discomfort
        )
        self.assertEqual(list(result.routes), ["fastest", "cleanest"])
        self.assertEqual(len(result.front), 2)
        same_node = sweep(
            self.graph, self.start, self.start, self.discomfort
        )
        self.assertEqual(list(same_node.routes), ["fastest"])
        self.assertEqual(len(same_node.front), 1)
        zero_scores = dict.fromkeys(self.graph.edges, 0.0)
        zero = sweep(self.graph, self.start, self.end, zero_scores)
        self.assertEqual(len(zero.front), 1)
        self.assertEqual(zero.front[0].time_s, 20)

    def test_sweep_no_route(self):
        with self.assertRaises(NoRoute):
            sweep(self.graph, self.end, self.start, self.discomfort)

    def test_pareto_dominance_and_ties(self):
        objectives = [(30, 30), (20, 180), (25, 75), (25, 90),
                      (25, 75), (40, 60), (22, 180)]
        self.assertEqual(nondominated(objectives), [1, 2, 0])
        self.assertEqual(nondominated([]), [])
        self.assertEqual(nondominated([(10, 5), (10, 3)]), [1])
        self.assertEqual(nondominated([(10, 3), (20, 3)]), [0])

    def test_knee(self):
        self.assertEqual(knee([(20, 180), (25, 75), (30, 30)]), 1)
        self.assertEqual(knee([(1, 3), (2, 2), (3, 1)]), 1)
        self.assertEqual(knee([(20, 30)]), 0)
        with self.assertRaises(ValueError):
            knee([])

    def test_sweep_similar_routes_keep_full_front(self):
        nodes = {i: (19.93 + i * .001, 50.06) for i in range(23)}
        edges = [
            Edge(i, i + 1, 0, 100, 10, (nodes[i], nodes[i + 1]))
            for i in range(22)
        ]
        edges.append(Edge(21, 22, 1, 120, 12, (nodes[21], nodes[22])))
        graph = Graph(nodes, edges)
        scores = dict.fromkeys(graph.edges, 1.0)
        scores[(21, 22, 0)] = 9
        result = sweep(graph, nodes[0], nodes[22], scores)
        self.assertEqual(len(result.front), 2)
        self.assertEqual(list(result.routes), ["fastest"])


if __name__ == "__main__":
    graph, discomfort = demo_graph()
    for label, lam in (("FASTEST", 0), ("ECO", 1)):
        started = perf_counter()
        result = route(graph, graph.nodes[0], graph.nodes[3], discomfort, lam)
        elapsed_ms = (perf_counter() - started) * 1000
        print(
            f"{label}: {result.time_s:.0f} s, "
            f"exposure={result.exposure:.0f}, "
            f"computed in {elapsed_ms:.3f} ms"
        )
    unittest.main()
