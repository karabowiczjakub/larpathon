"""Runtime checks that a module implementation satisfies app/contracts.py."""
from __future__ import annotations

import numpy as np

from .contracts import EdgeExposure


class ContractError(Exception):
    """A module returned data that does not match the shared contract."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ContractError(message)


def _per_edge(name: str, arr, n_edges: int, extra: tuple[int, ...] = ()) -> None:
    shape = np.shape(arr)
    _require(shape == (n_edges, *extra), f"{name}: expected shape {(n_edges, *extra)}, got {shape}")


def check_graph(graph) -> None:
    for attr in ("snap", "route", "geometry", "coord_counts"):
        _require(callable(getattr(graph, attr, None)), f"graph: missing method {attr}()")
    n = getattr(graph, "n_edges", None)
    _require(isinstance(n, (int, np.integer)) and n > 0, f"graph: n_edges must be a positive int, got {n!r}")
    _per_edge("graph.edge_length_m", graph.edge_length_m, n)
    _per_edge("graph.edge_mid_lonlat", graph.edge_mid_lonlat, n, (2,))
    _per_edge("graph.edge_highway", graph.edge_highway, n)
    _per_edge("graph.edge_name", graph.edge_name, n)


def check_shade(shade, n_edges: int) -> None:
    for attr in ("sun", "edge_shade"):
        _require(callable(getattr(shade, attr, None)), f"shade: missing method {attr}()")
    _per_edge("shade.edge_tree_frac", shade.edge_tree_frac, n_edges)


def check_env(env) -> None:
    for attr in ("get", "scenarios"):
        _require(callable(getattr(env, attr, None)), f"env: missing method {attr}()")


def check_exposure_fn(fn) -> None:
    _require(callable(fn), "exposure: compute_edge_exposure must be callable")


def check_edge_shade(shade: np.ndarray, n_edges: int) -> None:
    _per_edge("shade.edge_shade()", shade, n_edges)


def check_edge_exposure(exp, n_edges: int) -> None:
    _require(isinstance(exp, EdgeExposure), f"exposure: expected EdgeExposure, got {type(exp).__name__}")
    for name in ("utci_c", "air_index", "pm25", "uv_eff", "discomfort", "reason"):
        _per_edge(f"exposure.{name}", getattr(exp, name), n_edges)
