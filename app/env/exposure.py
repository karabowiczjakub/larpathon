import json
import logging
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

from ..contracts import EdgeExposure
from .fetch import REF_POINT
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


def _bilinear(mid_lonlat: np.ndarray, lats: tuple, lons: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Indeksy 4 sąsiednich węzłów regularnej siatki (wiersz = szerokość) i wagi dwuliniowe per krawędź."""
    mid = np.asarray(mid_lonlat, dtype=np.float64)
    def axis(vals, grid):
        g = np.asarray(grid, dtype=np.float64)
        i = np.clip(np.searchsorted(g, vals) - 1, 0, len(g) - 2)
        f = np.clip((vals - g[i]) / (g[i + 1] - g[i]), 0.0, 1.0)      # poza siatką: najbliższy brzeg
        return i, f
    r, fr = axis(mid[:, 1], lats)
    c, fc = axis(mid[:, 0], lons)
    n = len(lons)
    idx = np.stack([r * n + c, r * n + c + 1, (r + 1) * n + c, (r + 1) * n + c + 1], axis=1)
    w = np.stack([(1 - fr) * (1 - fc), (1 - fr) * fc, fr * (1 - fc), fr * fc], axis=1).astype(np.float32)
    return idx, w


# Street heat map (pipeline/heat_map_build.py): local Landsat surface-temperature anomaly per edge. Surface is
# not air: dense blocks vs parks differ by ~7 °C on the surface but ~1-2 °C in the air (park cool islands),
# hence the factor; the effect fades with wind and is capped.
HEAT_FILE = "edge_heat.npz"
HEAT_TO_AIR = 0.2
HEAT_CAP_C = 2.0
_heat_warned: set[str] = set()


def edge_heat(graph) -> np.ndarray | float:
    """Local surface-temperature anomaly [°C] per edge, or 0 when the map is missing or for another graph."""
    cached = _graph_arrays(graph)
    if "heat" not in cached:
        path = LUT_DIR / HEAT_FILE
        heat: np.ndarray | float = 0.0
        try:
            with np.load(path) as z:
                values = z["local_lst_anomaly_c"].astype(np.float32)
            if len(values) == len(graph.edge_highway):
                heat = values
            elif "length" not in _heat_warned:
                _heat_warned.add("length")
                log.warning("%s belongs to another graph (%d edges, graph has %d): run make heat-map",
                            path, len(values), len(graph.edge_highway))
        except FileNotFoundError:
            if "missing" not in _heat_warned:
                _heat_warned.add("missing")
                log.warning("no street heat map (%s): same air temperature within each neighbourhood", path)
        cached["heat"] = heat
    return cached["heat"]


def street_heat(heat, wind_ms) -> np.ndarray | float:
    """Air-temperature correction [°C] from the heat map: strongest in calm weather (<= 2 m/s)."""
    calm = np.clip(1.0 - (np.asarray(wind_ms) - 2.0) / 6.0, 0.3, 1.0)
    return np.clip(HEAT_TO_AIR * heat * calm, -HEAT_CAP_C, HEAT_CAP_C)


def local_weather(grid, graph) -> tuple[np.ndarray, np.ndarray] | tuple[float, float]:
    """Różnica temperatury [°C] i mnożnik wiatru per krawędź z siatki modelu pogody (ctx.weather_grid).
    Pusta siatka (stare scenariusze, brak danych) = ta sama pogoda w całym mieście."""
    if not grid:
        return 0.0, 1.0
    lats = tuple(sorted({p.lat for p in grid}))
    lons = tuple(sorted({p.lon for p in grid}))
    if len(lats) < 2 or len(lons) < 2 or len(grid) != len(lats) * len(lons):
        log.warning("weather grid is not regular (%d points), ignored", len(grid))
        return 0.0, 1.0
    cached = _graph_arrays(graph)
    key = ("bilinear", lats, lons)
    if key not in cached:
        ref = np.array([[REF_POINT[1], REF_POINT[0]]])
        cached[key] = (_bilinear(graph.edge_mid_lonlat, lats, lons), _bilinear(ref, lats, lons))
    (idx, w), (ref_idx, ref_w) = cached[key]
    order = {(p.lat, p.lon): p for p in grid}
    pts = [order[(la, lo)] for la in lats for lo in lons]
    dt = np.array([p.dt_c for p in pts], np.float32)
    wr = np.array([p.wind_ratio for p in pts], np.float32)
    # Anchored at the city point: the city temperature and wind are measured/forecast there (REF_POINT),
    # so the interpolated field must give exactly 0 °C and x1 there, not the grid's local smoothing.
    dt_ref, wr_ref = float((ref_w * dt[ref_idx]).sum()), float((ref_w * wr[ref_idx]).sum())
    return (w * dt[idx]).sum(axis=1) - dt_ref, (w * wr[idx]).sum(axis=1) / max(wr_ref, 1e-3)


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
    dt_local, wind_local = local_weather(ctx.weather_grid, graph)     # dolina, wzgórza, wyspa ciepła (~2 km)
    dt_street = street_heat(edge_heat(graph), ctx.wind_ms * wind_local)   # kwartał zabudowy vs park (~150 m)
    ta = ctx.temperature_c + dt_local + dt_street - 1.0 * tree_frac * rad
    tmrt = ta + (1 - shade) * 0.03 * ctx.dni_wm2 + (2.0 if ctx.shortwave_wm2 > 100 else 0.0)
    v = np.clip(ctx.wind_ms * wind_local * (1 - 0.3 * tree_frac), 0.5, 17)
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
