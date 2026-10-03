"""Explanations for the UI: coloured segments along a route and streets the ECO route avoids."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

REASONS = {-1: "ok", 0: "heat", 1: "air", 2: "uv"}


def edge_coord_spans(coord_counts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """First/last index of each edge in the concatenated route geometry (shared nodes are not duplicated)."""
    steps = np.maximum(np.asarray(coord_counts, dtype=np.int64) - 1, 0)
    ends = np.cumsum(steps)
    return ends - steps, ends


def segments(
    coord_counts: np.ndarray, discomfort: np.ndarray, reason: np.ndarray, time_s: np.ndarray
) -> list[dict]:
    """Merge consecutive edges with the same reason; `from`/`to` are inclusive geometry indices.

    All arrays are already restricted to the route's edges, in route order.
    """
    if len(reason) == 0:
        return []
    starts, ends = edge_coord_spans(coord_counts)
    cuts = np.flatnonzero(np.diff(reason)) + 1
    out = []
    for idx in np.split(np.arange(len(reason)), cuts):
        w = np.maximum(time_s[idx], 1e-9)
        out.append({
            "from": int(starts[idx[0]]),
            "to": int(ends[idx[-1]]),
            "discomfort": round(float(np.average(discomfort[idx], weights=w)), 2),
            "reason": REASONS.get(int(reason[idx[0]]), "ok"),
        })
    return out


def avoids(
    reference_eids: np.ndarray,
    eids: np.ndarray,
    discomfort: np.ndarray,
    reason: np.ndarray,
    edge_name: np.ndarray,
    edge_length_m: np.ndarray,
    threshold: float = 0.5,
    top: int = 3,
) -> list[str]:
    """Named streets of the reference route with high discomfort that this route does not use."""
    skipped = np.setdiff1d(reference_eids, eids)
    bad = skipped[discomfort[skipped] > threshold]
    length: dict[str, float] = defaultdict(float)
    why: dict[str, Counter] = defaultdict(Counter)
    for e in bad:
        name = edge_name[e]
        if not name or not isinstance(name, str):
            continue
        length[name] += float(edge_length_m[e])
        why[name][REASONS.get(int(reason[e]), "ok")] += 1
    best = sorted(length, key=length.get, reverse=True)[:top]
    return [f"{name} ({why[name].most_common(1)[0][0]})" for name in best]
