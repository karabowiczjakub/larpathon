from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.contract_checks import (
    check_edge_exposure,
    check_edge_shade,
    check_env,
    check_graph,
    check_shade,
)
from app.contracts import PointOutsideArea
from app.mocks import MockEnv, mock_exposure

TZ = ZoneInfo("Europe/Warsaw")
NOON = datetime(2025, 7, 3, 13, tzinfo=TZ)
A, B, C = (50.0614, 19.9366), (50.0675, 19.8728), (50.0510, 19.9450)


def test_mocks_satisfy_contracts(mock_modules):
    g = mock_modules.graph
    check_graph(g)
    check_shade(mock_modules.shade, g.n_edges)
    check_env(mock_modules.env)
    shade = mock_modules.shade.edge_shade(NOON)
    check_edge_shade(shade, g.n_edges)
    ctx = mock_modules.env.get("heatwave_2025-07-03", None)
    check_edge_exposure(mock_exposure(ctx, shade, g, mock_modules.shade.edge_tree_frac, "standard"), g.n_edges)


def test_route_is_continuous_and_geometry_matches(mock_graph):
    g = mock_graph
    r = g.route([A, C, B], g.edge_length_m)
    assert np.array_equal(g.edge_v[r.eids[:-1]], g.edge_u[r.eids[1:]])
    assert r.node_path[0] == g.snap(*A) and r.node_path[-1] == g.snap(*B)
    assert g.snap(*C) in r.node_path
    coords = g.geometry(r.eids)
    assert len(coords) == 1 + int((g.coord_counts(r.eids) - 1).sum())


def test_route_is_optimal_for_given_cost(mock_graph):
    g = mock_graph
    rng = np.random.default_rng(0)
    cost = g.edge_length_m * rng.uniform(1, 3, g.n_edges)
    by_length = g.route([A, B], g.edge_length_m)
    by_cost = g.route([A, B], cost)
    assert g.edge_length_m[by_length.eids].sum() <= g.edge_length_m[by_cost.eids].sum()
    assert cost[by_cost.eids].sum() <= cost[by_length.eids].sum()


def test_snap_far_point_raises_with_index(mock_graph):
    with pytest.raises(PointOutsideArea) as e:
        mock_graph.route([A, (50.149, 20.249)], mock_graph.edge_length_m)
    assert e.value.index == 1


def test_wrong_cost_shape_is_rejected(mock_graph):
    with pytest.raises(ValueError):
        mock_graph.route([A, B], np.ones(5))


def test_cost_matrix(mock_graph):
    m = mock_graph.cost_matrix([A, B, C], mock_graph.edge_length_m)
    assert m.shape == (3, 3) and np.allclose(np.diag(m), 0) and (m[~np.eye(3, dtype=bool)] > 0).all()


def test_shade_day_and_night(mock_modules):
    s = mock_modules.shade
    day = s.edge_shade(NOON)
    assert 0 <= day.min() and day.max() <= 1 and day.std() > 0.05
    assert (s.edge_shade(NOON.replace(hour=23)) == 1).all()
    assert s.sun(NOON).elevation_deg > 55 and s.sun(NOON.replace(hour=23)).elevation_deg < 0
    winter = datetime(2025, 1, 20, 12, tzinfo=TZ)
    assert 10 < s.sun(winter).elevation_deg < 25


def test_env_scenarios_and_daily_cycle():
    env = MockEnv()
    heat = env.get("heatwave_2025-07-03", None)
    assert heat.timestamp.isoformat() == "2025-07-03T14:00:00+02:00" and heat.temperature_c == 34.5
    night = env.get("heatwave_2025-07-03", heat.timestamp.replace(hour=23))
    assert night.uv_index == 0 and night.temperature_c < heat.temperature_c
    assert env.get("smog_2025-01-20", None).pm25 > 50
    assert env.get("unknown", None).summary()["source"] == "mock"
