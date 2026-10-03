import json
import logging
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

from ..contracts import EdgeExposure
from .fuzzy_profiles import PROFILES
from .gios_sensors import GIOS_STATIONS, TRAFFIC_STATION

try:
    from pythermalcomfort.models import utci as _utci
except ImportError:                                                       # PLAN B w utci_fast
    _utci = None

log = logging.getLogger(__name__)
LUT_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
ROAD_FACTORS_FILE = Path(__file__).with_name("road_factors.json")
POLLUTANTS = ("pm10", "pm25", "no2")
_plan_b_logged: list = []


def utci_fast(ta, tmrt, v, rh):
    """UTCI tylko dla unikalnych skwantowanych wejść (T_a co 0,5 °C, ΔTmrt co 1 °C, v co 0,5 m/s).
    Trójka zakodowana w jeden int64: np.unique na 1D jest ~15× szybsze niż axis=0."""
    ta2, dt, v2 = np.broadcast_arrays(np.round(np.asarray(ta) * 2).astype(np.int64),
                                      np.round(np.asarray(tmrt) - np.asarray(ta)).astype(np.int64),
                                      np.round(np.asarray(v) * 2).astype(np.int64))
    key = (ta2 + 1000) * 1_000_000 + (dt + 500) * 1_000 + v2
    uniq, inv = np.unique(key.ravel(), return_inverse=True)
    t_u, d_u, v_u = (uniq // 1_000_000 - 1000) / 2, uniq // 1_000 % 1_000 - 500, uniq % 1_000 / 2
    try:
        res = _utci(tdb=t_u, tr=t_u + d_u, v=v_u, rh=rh, limit_inputs=False)
        vals = np.asarray(getattr(res, "utci", res), dtype=np.float32)       # pythermalcomfort 2.x vs 3.x+
    except Exception:
        if not _plan_b_logged:
            log.warning("pythermalcomfort unavailable — simplified UTCI (PLAN B)", exc_info=_utci is not None)
            _plan_b_logged.append(True)
        vals = (t_u + 0.33 * d_u - 0.7 * v_u).astype(np.float32)
    return vals[inv.ravel()].reshape(key.shape)


# EAQI po rewizji EEA (2024, wg wytycznych WHO 2021; airindex.eea.europa.eu), stężenia godzinowe [µg/m³].
# Granice pasm good | fair | moderate | poor | very poor | extremely poor → indeks ciągły 0..6.
BANDS = {"pm25": [0, 5, 15, 50, 90, 140, 800],
         "pm10": [0, 15, 45, 120, 195, 270, 1200],
         "no2":  [0, 10, 25, 60, 100, 150, 1000]}


def air_index(c: dict, ve_ratio: float = 1.0) -> np.ndarray:
    return np.maximum.reduce([np.interp(c[k] * ve_ratio, b, np.arange(7)) for k, b in BANDS.items()])


# Wartości startowe (roles/02 §6.2); `pipeline/calibrate_road.py` nadpisuje je danymi GIOŚ w road_factors.json.
F_ROAD = {"trunk": (1.35, 1.8), "trunk_link": (1.35, 1.8), "primary": (1.35, 1.8), "primary_link": (1.35, 1.8),
          "secondary": (1.2, 1.4), "secondary_link": (1.2, 1.4), "tertiary": (1.1, 1.2), "tertiary_link": (1.1, 1.2),
          "cycleway": (0.95, 0.9), "path": (0.95, 0.9), "track": (0.95, 0.9), "footway": (0.95, 0.9)}


def load_road_factors(path: Path = ROAD_FACTORS_FILE) -> dict:
    try:
        calibrated = json.loads(path.read_text(encoding="utf-8"))["f_road"]
    except FileNotFoundError:
        return dict(F_ROAD)
    except (ValueError, KeyError):
        log.warning("invalid %s — using default road factors", path)
        return dict(F_ROAD)
    return {**F_ROAD, **{h: tuple(f) for h, f in calibrated.items()}}


ROAD = load_road_factors()

# ---------- przestrzenne tło z GIOŚ (IDW, potęga 2) ----------
KM_PER_DEG_LAT = 110.57
KM_PER_DEG_LON = 111.32 * np.cos(np.radians(50.06))
IDW_MIN_KM = 0.5                     # krawędź tuż przy stacji nie dostaje nieskończonej wagi
IDW_MIN_STATIONS = 3                 # mniej stacji → wzór PM10 albo jednolite tło
FIELD_RANGE = (0.5, 2.0)
_graph_cache: dict[int, dict] = {}


def _idw_weights(mid_lonlat: np.ndarray) -> np.ndarray:
    st = np.array([(lon, lat) for _, _, lat, lon, _ in GIOS_STATIONS])
    mid = np.asarray(mid_lonlat, dtype=np.float64)
    dx = (mid[:, :1] - st[:, 0]) * KM_PER_DEG_LON
    dy = (mid[:, 1:2] - st[:, 1]) * KM_PER_DEG_LAT
    return (1.0 / np.maximum(dx * dx + dy * dy, IDW_MIN_KM ** 2)).astype(np.float32)   # (E, 8)


def _graph_arrays(graph) -> dict:
    """Stałe per graf (czynnik drogi, wagi IDW) liczone raz; klucz to graf, nie globalny singleton."""
    hw = graph.edge_highway
    cached = _graph_cache.get(id(graph))
    if cached is None or len(cached["f_pm"]) != len(hw):
        f = np.array([ROAD.get(h, (1.0, 1.0)) if isinstance(h, str) else (1.0, 1.0) for h in hw],
                     np.float32).reshape(-1, 2)
        if len(_graph_cache) >= 4:
            _graph_cache.clear()
        cached = _graph_cache[id(graph)] = {"f_pm": f[:, 0], "f_no2": f[:, 1],
                                            "w": _idw_weights(graph.edge_mid_lonlat)}
    return cached


def spatial_factors(stations, w: np.ndarray) -> dict[str, np.ndarray]:
    """Mnożnik tła per krawędź: IDW z (wartość stacji / mediana stacji) dla stacji tła.
    Stacje bez wartości pomijamy (renormalizacja wag); brak klucza = tło jednolite."""
    by_id = {s.station_id: s for s in stations}
    out = {}
    for k in POLLUTANTS:
        vals = np.zeros(len(GIOS_STATIONS), np.float32)
        for j, (sid, *_) in enumerate(GIOS_STATIONS):
            v = getattr(by_id[sid], k) if sid in by_id and sid != TRAFFIC_STATION else None
            vals[j] = v if v is not None and v > 0 else 0.0
        valid = vals > 0
        if valid.sum() >= IDW_MIN_STATIONS:
            rel = vals / np.median(vals[valid])                      # 0 dla stacji bez wartości
            out[k] = np.clip((w @ rel) / (w @ valid.astype(np.float32)), *FIELD_RANGE)
    for k in ("pm25", "no2"):                         # PM2.5 mierzą tylko 2 stacje tła → wzór PM10
        if k not in out and "pm10" in out:
            out[k] = out["pm10"]
    return out


# ---------- dyskomfort: LUT fuzzy (offline) → interpolacja liniowa ----------
_luts: dict = {}


def _lut(profile: str):
    if profile not in _luts:
        try:
            with np.load(LUT_DIR / "lut_grid.npz") as g:
                grids = (g["heat"], g["air"], g["uv"])
            _luts[profile] = (np.load(LUT_DIR / f"lut_{profile}.npy"), grids)
        except (OSError, KeyError, ValueError):
            log.warning("fuzzy LUT for %r missing in %s — 'worst factor' fallback (run: make fuzzy)", profile, LUT_DIR)
            _luts[profile] = None
    return _luts[profile]


def _grid_index(x, g: np.ndarray) -> np.ndarray:
    """Ułamkowy indeks w siatce LUT, przycięty do jej zakresu (siatki z fuzzy_build są równomierne)."""
    step = g[1] - g[0]
    if np.allclose(np.diff(g), step):
        return np.clip((x - g[0]) * (1.0 / step), 0, len(g) - 1)
    return np.interp(x, g, np.arange(len(g)))


def discomfort(profile: str, utci, air, uv) -> np.ndarray:
    lut = _lut(profile)
    if lut is None:                                   # PLAN B: najgorszy czynnik decyduje
        return np.clip(np.maximum.reduce([(utci - 26) / 12, (air - 1) / 4, (uv - 3) / 6]), 0, 1)
    table, grids = lut
    idx = [_grid_index(x, g) for x, g in zip((utci, air, uv), grids)]
    return np.clip(map_coordinates(table, idx, order=1, mode="nearest") / 10.0, 0, 1)


def dominant_factor(utci, air, uv) -> np.ndarray:
    """-1 OK, 0 upał, 1 powietrze, 2 UV (roles/02 §6.6); remis → pierwszy, jak argmax."""
    s0, s1, s2 = np.clip((utci - 26) / 12, 0, 1), np.clip((air - 1) / 4, 0, 1), np.clip((uv - 3) / 6, 0, 1)
    worst = np.maximum(np.maximum(s0, s1), s2)
    reason = np.where(s0 >= worst, 0, np.where(s1 >= worst, 1, 2)).astype(np.int8)
    reason[worst < 0.15] = -1
    return reason


def compute_edge_exposure(ctx, shade, graph, tree_frac, profile) -> EdgeExposure:
    profile = profile if profile in PROFILES else "standard"
    p = PROFILES[profile]
    shade = np.asarray(shade, dtype=np.float32)
    tree_frac = np.asarray(tree_frac, dtype=np.float32)

    rad = min(1.0, ctx.shortwave_wm2 / 600)
    ta = ctx.temperature_c - 1.0 * tree_frac * rad
    tmrt = ta + (1 - shade) * 0.03 * ctx.dni_wm2 + (2.0 if ctx.shortwave_wm2 > 100 else 0.0)
    v = np.clip(ctx.wind_ms * (1 - 0.3 * tree_frac), 0.5, 17)
    utci = utci_fast(ta, tmrt, v, ctx.humidity_pct)

    g = _graph_arrays(graph)
    field = spatial_factors(ctx.stations, g["w"])
    green = 1 - 0.1 * tree_frac
    conc = {k: getattr(ctx, k) * field.get(k, 1.0) * (g["f_no2"] if k == "no2" else g["f_pm"]) * green
            for k in POLLUTANTS}
    air = air_index(conc, p["ve_ratio"])
    uv = ctx.uv_index * (1 - 0.6 * shade)

    air = air.astype(np.float32)
    return EdgeExposure(utci_c=utci, air_index=air, pm25=conc["pm25"].astype(np.float32), uv_eff=uv.astype(np.float32),
                        discomfort=discomfort(profile, utci, air, uv).astype(np.float32),
                        reason=dominant_factor(utci, air, uv))
