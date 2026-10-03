"""Rola 2 z modułami z main: RoutingGraph (Rola 1) i MockShade/ShadeModel (Rola 3)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyproj import Transformer
from scipy.sparse import csr_matrix

from app.env.exposure import compute_edge_exposure
from app.env.service import EnvironmentService
from app.graph.routing import RoutingGraph
from app.shade.mock import MockShade
from app.shade.model import ShadeModel

SCEN = Path(__file__).resolve().parents[1] / "scenarios"
# A(0) → B(3): krótko arterią przez 1 albo dłużej drogą rowerową w parku przez 2
POINTS = [(50.0600, 19.9300), (50.0610, 19.9315), (50.0590, 19.9315), (50.0600, 19.9330)]   # (lat, lon)
EDGES = [(0, 1, "primary", 140.0), (1, 3, "primary", 140.0), (0, 2, "cycleway", 150.0), (2, 3, "cycleway", 150.0)]


@pytest.fixture(scope="module")
def graph() -> RoutingGraph:
    lat, lon = np.array(POINTS).T
    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
    u, v = np.array([e[0] for e in EDGES]), np.array([e[1] for e in EDGES])
    base = csr_matrix((np.arange(1, len(EDGES) + 1), (u, v)), shape=(len(POINTS), len(POINTS)))
    z = {"indptr": base.indptr, "indices": base.indices, "perm": base.data - 1, "node_x": x, "node_y": y,
         "node_lon": lon, "node_lat": lat, "edge_u": u, "edge_v": v,
         "edge_length_m": np.array([e[3] for e in EDGES]),
         "edge_mid_lon": (lon[u] + lon[v]) / 2, "edge_mid_lat": (lat[u] + lat[v]) / 2}
    gc = {"coords": np.array([[lon[n], lat[n]] for pair in zip(u, v) for n in pair]),
          "offs": np.arange(0, 2 * len(EDGES) + 1, 2)}
    meta = pd.DataFrame({"eid": np.arange(len(EDGES)), "highway": [e[2] for e in EDGES], "name": None})
    return RoutingGraph(z, gc, meta)


@pytest.fixture(scope="module")
def env(tmp_path_factory) -> EnvironmentService:
    return EnvironmentService(SCEN, tmp_path_factory.mktemp("env"), refresh=False)


def _eco_cost(graph, exp, alpha=3.0):
    return graph.edge_length_m / 4.2 * (1 + alpha * exp.discomfort)


@pytest.mark.parametrize("scenario", ["heatwave_2025-07-03", "smog_2025-01-20"])
def test_exposure_drives_routing_on_real_graph(graph, env, scenario):
    tree = np.array([0.0, 0.0, 0.9, 0.9], np.float32)                 # arteria bez drzew, park z drzewami
    shade = MockShade(graph.n_edges, tree_frac=tree)
    ctx = env.get(scenario, None)
    exp = compute_edge_exposure(ctx, shade.edge_shade(ctx.timestamp), graph, shade.edge_tree_frac, "standard")
    assert exp.discomfort.shape == (graph.n_edges,)
    assert (exp.discomfort[:2] > exp.discomfort[2:]).all()

    a, b = POINTS[0], POINTS[3]
    fastest = graph.route([a, b], graph.edge_length_m)
    eco = graph.route([a, b], _eco_cost(graph, exp))
    assert fastest.eids.tolist() == [0, 1]
    assert eco.eids.tolist() == [2, 3]                                 # ECO omija arterię
    assert graph.geometry(eco.eids)[0] == pytest.approx([POINTS[0][1], POINTS[0][0]])


def test_exposure_accepts_shade_model_output(graph, env):
    az, el = np.arange(0, 360, 45.0), np.array([5.0, 30.0, 60.0])
    table = np.zeros((graph.n_edges, len(az), len(el)), np.uint8)
    table[2:] = 255                                                    # park w pełnym cieniu
    model = ShadeModel(table, np.array([0.0, 0.0, 0.9, 0.9]), az, el)
    ctx = env.get("heatwave_2025-07-03", None)
    shade = model.edge_shade(ctx.timestamp)                            # tablica tylko do odczytu
    exp = compute_edge_exposure(ctx, shade, graph, model.edge_tree_frac, "senior")
    assert exp.utci_c[2] < exp.utci_c[0] - 5 and exp.uv_eff[2] < exp.uv_eff[0]
