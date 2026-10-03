"""'Real' module factories for provider tests, referenced by "fake_modules:<name>" paths."""
import numpy as np

from app.mocks import MockGraph, MockShade

SMALL_BBOX = (19.90, 50.04, 19.97, 50.08)


def load_graph(data_dir):
    return MockGraph(bbox=SMALL_BBOX)


def load_shade_for_other_graph(data_dir, n_edges):
    shade = MockShade(MockGraph(bbox=SMALL_BBOX))
    shade.edge_tree_frac = np.zeros(n_edges + 1, np.float32)
    return shade


def missing_env(scenario_dir, data_dir):
    raise FileNotFoundError(f"{scenario_dir}/heatwave_2025-07-03.json")
