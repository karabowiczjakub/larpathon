"""Map overlay: per-edge shade and discomfort inside a bounding box (GET /api/layers/shade)."""
from __future__ import annotations

import numpy as np

from .costs import EdgeCosts
from .explain import REASONS

MAX_FEATURES = 5000


def edges_in_bbox(
    mid_lonlat: np.ndarray, length_m: np.ndarray, bbox: tuple[float, float, float, float], limit: int = MAX_FEATURES
) -> tuple[np.ndarray, bool]:
    """Edges with the midpoint in bbox, one per two-way street; the longest ones when over the limit."""
    w, s, e, n = bbox
    mid = np.asarray(mid_lonlat, dtype=np.float64)
    eids = np.flatnonzero((mid[:, 0] >= w) & (mid[:, 0] <= e) & (mid[:, 1] >= s) & (mid[:, 1] <= n))
    _, first = np.unique(np.round(mid[eids], 6), axis=0, return_index=True)  # both directions share the midpoint
    eids = eids[np.sort(first)]
    truncated = len(eids) > limit
    if truncated:
        eids = np.sort(eids[np.argsort(-np.asarray(length_m)[eids], kind="stable")[:limit]])
    return eids, truncated


def feature_collection(graph, eids: np.ndarray, costs: EdgeCosts) -> dict:
    exp = costs.exposure
    shade = np.round(costs.shade[eids], 2).tolist()
    discomfort = np.round(np.asarray(exp.discomfort)[eids], 2).tolist()
    reasons = [REASONS.get(int(r), "ok") for r in np.asarray(exp.reason)[eids]]
    names = graph.edge_name[eids]
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": graph.geometry(np.array([e], dtype=np.int64))},
            "properties": {"eid": int(e), "name": name if isinstance(name, str) else None,
                           "shade": sh, "discomfort": d, "reason": r},
        }
        for e, name, sh, d, r in zip(eids, names, shade, discomfort, reasons, strict=True)
    ]
    return {"type": "FeatureCollection", "features": features}
