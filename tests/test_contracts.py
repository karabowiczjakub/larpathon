"""Contract checks on the REAL modules of roles 1-3 (skipped until their code and artefacts exist)."""
import importlib.util
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import config
from app.contract_checks import check_edge_exposure, check_edge_shade, check_env, check_graph, check_shade
from app.providers import resolve

CFG = config.from_env()
DATA = CFG["DATA_DIR"]
HEAT_AT = datetime(2025, 7, 3, 14, tzinfo=ZoneInfo("Europe/Warsaw"))


def _available(path_setting: str, *files: str) -> bool:
    module = CFG[path_setting].partition(":")[0]
    try:
        found = importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        found = False
    return found and all(os.path.exists(os.path.join(DATA, f)) for f in files)


needs_graph = pytest.mark.skipif(not _available("GRAPH_FACTORY", "graph.npz", "edges.parquet", "edge_coords.npz"),
                                 reason="Role 1 module or graph artefacts missing")
needs_shade = pytest.mark.skipif(not _available("SHADE_FACTORY", "shade.npy", "edge_tree_frac.npy"),
                                 reason="Role 3 module or shade artefacts missing")
needs_env = pytest.mark.skipif(not _available("ENV_FACTORY"), reason="Role 2 service missing")
needs_exposure = pytest.mark.skipif(not _available("EXPOSURE_FN"), reason="Role 2 exposure missing")


@pytest.fixture(scope="module")
def graph():
    return resolve(CFG["GRAPH_FACTORY"])(DATA)


@needs_graph
def test_real_graph(graph):
    check_graph(graph)
    r = graph.route([(50.0614, 19.9366), (50.0540, 19.9350)], graph.edge_length_m)
    coords = graph.geometry(r.eids)
    assert len(coords) == 1 + int((graph.coord_counts(r.eids) - 1).sum())


@needs_graph
@needs_shade
def test_real_shade_matches_graph(graph):
    shade = resolve(CFG["SHADE_FACTORY"])(DATA, n_edges=graph.n_edges)
    check_shade(shade, graph.n_edges)
    s = shade.edge_shade(HEAT_AT)
    check_edge_shade(s, graph.n_edges)
    assert 0 <= s.min() and s.max() <= 1


@needs_env
def test_real_env_offline_scenario():
    env = resolve(CFG["ENV_FACTORY"])(CFG["SCENARIO_DIR"], DATA)
    check_env(env)
    ids = [s["id"] for s in env.scenarios()]
    assert ids[0] == "live"
    ctx = env.get("heatwave_2025-07-03", None)
    assert ctx.timestamp.tzinfo is not None and set(ctx.summary()) >= {"source", "temperature_c", "pm25"}


@needs_graph
@needs_exposure
def test_real_exposure_shapes(graph):
    from app.mocks import MockEnv, MockShade

    shade = MockShade(graph)
    ctx = MockEnv().get("heatwave_2025-07-03", None)
    fn = resolve(CFG["EXPOSURE_FN"])
    exp = fn(ctx, shade.edge_shade(HEAT_AT), graph, shade.edge_tree_frac, "standard")
    check_edge_exposure(exp, graph.n_edges)
    assert 0 <= exp.discomfort.min() and exp.discomfort.max() <= 1
