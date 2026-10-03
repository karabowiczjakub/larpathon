import numpy as np
from scipy.interpolate import RegularGridInterpolator
from ..contracts import EdgeExposure
from .fuzzy_profiles import PROFILES

# Fallback utci (pythermalcomfort imported conditionally or mocked)
def utci_fast(ta, tmrt, v, rh):
    q = np.column_stack([np.round(ta * 2) / 2, np.round(tmrt - ta), np.round(v * 2) / 2])
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    try:
        from pythermalcomfort.models import utci as _utci
        res = _utci(tdb=uniq[:, 0], tr=uniq[:, 0] + uniq[:, 1], v=uniq[:, 2], rh=rh, limit_inputs=False)
        vals = np.asarray(getattr(res, "utci", res), dtype=np.float32)       # pythermalcomfort 2.x vs 3.x
    except Exception:
        # PLAN B
        vals = (uniq[:, 0] + 0.33 * uniq[:, 1] - 0.7 * uniq[:, 2]).astype(np.float32)
    return vals[inv.ravel()]

BANDS = {"pm25": [0, 10, 20, 25, 50, 75, 800],
         "pm10": [0, 20, 40, 50, 100, 150, 1200],
         "no2":  [0, 40, 90, 120, 230, 340, 1000]}

def air_index(c: dict, ve_ratio: float = 1.0) -> np.ndarray:
    return np.maximum.reduce([np.interp(c[k] * ve_ratio, b, np.arange(7)) for k, b in BANDS.items()])

F_ROAD = {"trunk": (1.35, 1.8), "trunk_link": (1.35, 1.8), "primary": (1.35, 1.8), "primary_link": (1.35, 1.8),
          "secondary": (1.2, 1.4), "secondary_link": (1.2, 1.4), "tertiary": (1.1, 1.2), "tertiary_link": (1.1, 1.2),
          "cycleway": (0.95, 0.9), "path": (0.95, 0.9), "track": (0.95, 0.9), "footway": (0.95, 0.9)}
_cache = {}

def _road_factors(graph):
    if "road" not in _cache:
        pm = np.array([F_ROAD.get(h, (1.0, 1.0))[0] for h in graph.edge_highway], np.float32)
        no2 = np.array([F_ROAD.get(h, (1.0, 1.0))[1] for h in graph.edge_highway], np.float32)
        _cache["road"] = (pm, no2)
    return _cache["road"]

def _lut(profile):
    if profile not in _cache:
        try:
            g = np.load("data/processed/lut_grid.npz")
            lut = np.load(f"data/processed/lut_{profile}.npy")
            _cache[profile] = RegularGridInterpolator((g["heat"], g["air"], g["uv"]), lut, bounds_error=False, fill_value=None)
        except Exception:
            return None
    return _cache[profile]

def compute_edge_exposure(ctx, shade, graph, tree_frac, profile) -> EdgeExposure:
    p = PROFILES.get(profile, PROFILES["standard"])
    rad = min(1.0, ctx.shortwave_wm2 / 600)
    ta = ctx.temperature_c - 1.0 * tree_frac * rad
    tmrt = ta + (1 - shade) * 0.03 * ctx.dni_wm2 + (2.0 if ctx.shortwave_wm2 > 100 else 0.0)
    v = np.clip(ctx.wind_ms * (1 - 0.3 * tree_frac), 0.5, 17)
    utci = utci_fast(ta, tmrt, v, ctx.humidity_pct)

    f_pm, f_no2 = _road_factors(graph)
    green = 1 - 0.1 * tree_frac
    pm25 = ctx.pm25 * f_pm * green
    conc = {"pm25": pm25, "pm10": ctx.pm10 * f_pm * green, "no2": ctx.no2 * f_no2 * green}
    air = air_index(conc, p["ve_ratio"])
    uv = ctx.uv_index * (1 - 0.6 * shade)

    lut_interp = _lut(profile)
    if lut_interp is not None:
        D = lut_interp(np.column_stack([np.clip(utci, -30, 50), np.clip(air, 0, 6), np.clip(uv, 0, 12)])) / 10.0
    else:
        # PLAN B
        D = np.clip(np.maximum.reduce([(utci - 26) / 12, (air - 1) / 4, (uv - 3) / 6]), 0, 1)

    sev = np.column_stack([np.clip((utci - 26) / 12, 0, 1), np.clip((air - 1) / 4, 0, 1), np.clip((uv - 3) / 6, 0, 1)])
    reason = np.where(sev.max(1) < 0.15, -1, sev.argmax(1)).astype(np.int8)
    
    return EdgeExposure(utci_c=utci, air_index=air, pm25=pm25, uv_eff=uv,
                        discomfort=np.clip(D, 0, 1).astype(np.float32), reason=reason)
