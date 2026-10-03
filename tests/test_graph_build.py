import json
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import quoteattr

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from shapely.geometry import LineString

from app.graph.routing import RoutingGraph
from pipeline.graph_build import contraflow, keep, save_graph


class BikeFilterTests(unittest.TestCase):
    def test_excluded_roads(self):
        for tags in [
            {"highway": "steps"},
            {"highway": "motorway"},
            {"highway": "planned"},
            {"highway": "footway"},
            {"highway": "residential", "bicycle": "no"},
            {"highway": "service", "service": "parking_aisle"},
        ]:
            self.assertFalse(keep(tags))
        self.assertTrue(keep({"highway": "footway", "bicycle": "designated"}))

    def test_contraflow_overrides_oneway_and_roundabouts(self):
        for tags in [
            dict(oneway="yes", **{"oneway:bicycle": "no"}),
            {"oneway": "yes", "cycleway": "opposite_lane"},
            dict(junction="roundabout", **{"oneway:bicycle": "no"}),
        ]:
            self.assertEqual(contraflow(tags)["oneway"], "no")
        self.assertEqual(contraflow({"oneway": "yes"})["oneway"], "yes")

    def test_xml_graph_obeys_bicycle_directions(self):
        cases = [
            ({"oneway": "yes"}, {(1, 2)}),
            ({"oneway": "-1"}, {(2, 1)}),
            ({"oneway": "yes", "oneway:bicycle": "no"}, {(1, 2), (2, 1)}),
            ({"junction": "roundabout", "oneway:bicycle": "no"}, {(1, 2), (2, 1)}),
            ({"oneway": "yes", "cycleway:left": "opposite_lane"}, {(1, 2), (2, 1)}),
            ({"oneway": "no", "oneway:bicycle": "-1"}, {(2, 1)}),
            ({"cycleway": "opposite", "oneway:bicycle": "yes"}, {(1, 2)}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "directions.osm"
            for tags, expected in cases:
                with self.subTest(tags=tags):
                    converted = contraflow({"highway": "residential", **tags})
                    xml_tags = "".join(
                        f"<tag k={quoteattr(k)} v={quoteattr(v)}/>"
                        for k, v in converted.items()
                    )
                    path.write_text(
                        '<osm version="0.6"><node id="1" lat="50.06" lon="19.94"/>'
                        '<node id="2" lat="50.06" lon="19.941"/>'
                        '<way id="10"><nd ref="1"/><nd ref="2"/>'
                        + xml_tags
                        + "</way></osm>",
                        encoding="utf-8",
                    )
                    graph = ox.graph_from_xml(path, simplify=False, retain_all=True)
                    self.assertEqual(set(graph.edges()), expected)

    def test_export_deduplicates_and_orients_geometry(self):
        graph = nx.MultiDiGraph(crs="EPSG:2180")
        graph.add_node(10, x=567000.0, y=244000.0)
        graph.add_node(20, x=567100.0, y=244000.0)
        for u, v, key, length in [(10, 20, 1, 120), (10, 20, 0, 100), (20, 10, 0, 100)]:
            graph.add_edge(
                u,
                v,
                key=key,
                length=length,
                highway="residential",
                name="Test",
                geometry=LineString([(567100, 244000), (567000, 244000)]),
            )
        with tempfile.TemporaryDirectory() as directory:
            graph.edges[10, 20, 0]["highway"] = ["path", "cycleway"]
            graph.edges[10, 20, 0]["name"] = ["Z Street", "A Street"]
            save_graph(graph, directory)
            routing = RoutingGraph.load(directory)
            self.assertEqual(routing.n_edges, 2)
            np.testing.assert_array_equal(routing.edge_length_m, [100, 100])
            np.testing.assert_array_equal(routing.edge_u, [0, 1])
            np.testing.assert_array_equal(routing.edge_v, [1, 0])
            meta = gpd.read_parquet(Path(directory) / "edges.parquet")
            self.assertEqual(meta.crs.to_epsg(), 2180)
            first_manifest = json.loads(
                (Path(directory) / "graph_manifest.json").read_text()
            )
            reordered = nx.MultiDiGraph(crs=graph.graph["crs"])
            reordered.add_nodes_from(reversed(list(graph.nodes(data=True))))
            for u, v, key, data in reversed(list(graph.edges(keys=True, data=True))):
                reordered.add_edge(
                    u,
                    v,
                    key=key,
                    **{
                        k: v[::-1] if isinstance(v, list) else v
                        for k, v in data.items()
                    },
                )
            save_graph(reordered, directory)
            second_manifest = json.loads(
                (Path(directory) / "graph_manifest.json").read_text()
            )
            self.assertEqual(first_manifest, second_manifest)
            with (Path(directory) / "edges.parquet").open("ab") as artifact:
                artifact.write(b"mismatched artifact")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                RoutingGraph.load(directory)
