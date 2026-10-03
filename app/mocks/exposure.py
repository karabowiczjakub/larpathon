"""mock_exposure: simple 'worst factor wins' discomfort (no fuzzy logic); Role 2 replaces it."""
from __future__ import annotations

import numpy as np

from ..contracts import EdgeExposure

ROAD_PM_FACTOR = {"primary": 1.35, "secondary": 1.2, "tertiary": 1.1, "cycleway": 0.95}
PROFILE_WEIGHTS = {  # severity multipliers (heat, air, uv)
    "standard": (1.0, 1.0, 1.0),
    "asthma": (1.0, 1.4, 1.0),
    "senior": (1.3, 1.15, 1.1),
    "athlete": (0.85, 1.1, 1.0),
}


def mock_exposure(ctx, shade, graph, tree_frac, profile: str) -> EdgeExposure:
    shade = np.asarray(shade, dtype=np.float64)
    tree = np.asarray(tree_frac, dtype=np.float64)
    road = np.array([ROAD_PM_FACTOR.get(h, 1.0) for h in graph.edge_highway])

    sun = min(ctx.shortwave_wm2, 1000) / 1000
    utci = ctx.temperature_c + (1 - shade) * 9 * sun - 1.5 * tree - 0.5 * max(ctx.wind_ms - 2, 0)
    pm25 = ctx.pm25 * road * (1 - 0.1 * tree)
    air = np.clip(pm25 / 20, 0, 6)
    uv = ctx.uv_index * (1 - 0.6 * shade)

    w_heat, w_air, w_uv = PROFILE_WEIGHTS.get(profile, (1.0, 1.0, 1.0))
    severity = np.column_stack([
        np.clip((utci - 26) / 16 * w_heat, 0, 1),
        np.clip((air - 1) / 4 * w_air, 0, 1),
        np.clip((uv - 3) / 6 * w_uv, 0, 1),
    ])
    discomfort = severity.max(axis=1)
    reason = np.where(discomfort < 0.15, -1, severity.argmax(axis=1)).astype(np.int8)
    return EdgeExposure(utci_c=utci, air_index=air, pm25=pm25, uv_eff=uv,
                        discomfort=discomfort.astype(np.float32), reason=reason)
