import time
from dataclasses import fields, replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.contracts import EdgeExposure, StationReading
from app.env import exposure as ex
from app.env.gios_sensors import GIOS_STATIONS, TRAFFIC_STATION
from app.env.service import EnvironmentService

TZ = ZoneInfo("Europe/Warsaw")
SCEN = Path(__file__).resolve().parents[1] / "scenarios"
STATION_LONLAT = {sid: (lon, lat) for sid, _, lat, lon, _ in GIOS_STATIONS}


class Graph:
    """Część RoutingGraphP, której używa compute_edge_exposure."""

    def __init__(self, highway, mid_lonlat):
        self.edge_highway = np.asarray(highway, dtype=object)
        self.edge_mid_lonlat = np.asarray(mid_lonlat, dtype=np.float64)
        self.n_edges = len(self.edge_highway)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    return EnvironmentService(SCEN, tmp_path_factory.mktemp("env"), refresh=False)


def _run(ctx, graph, shade=0.0, tree=0.0, profile="standard"):
    e = graph.n_edges
    return ex.compute_edge_exposure(ctx, np.full(e, shade, np.float32), graph, np.full(e, tree, np.float32), profile)


def test_contract_shapes_dtypes_and_ranges(env):
    g = Graph(["primary", "cycleway", "residential", "footway", "unknown", None], [(19.94, 50.06)] * 6)
    for scenario in ("heatwave_2025-07-03", "smog_2025-01-20"):
        res = _run(env.get(scenario, None), g, shade=0.3, tree=0.2)
        assert isinstance(res, EdgeExposure)
        for f in fields(res):
            arr = getattr(res, f.name)
            assert arr.shape == (6,) and arr.dtype == (np.int8 if f.name == "reason" else np.float32), f.name
            assert np.isfinite(arr).all()
        assert ((res.discomfort >= 0) & (res.discomfort <= 1)).all()
        assert set(res.reason) <= {-1, 0, 1, 2}


def test_shade_and_trees_reduce_heat_and_uv(env):
    ctx = env.get("heatwave_2025-07-03", None)
    g = Graph(["residential"], [(19.94, 50.06)])
    sun, shade = _run(ctx, g), _run(ctx, g, shade=1.0, tree=1.0)
    assert shade.utci_c[0] < sun.utci_c[0] - 5
    assert shade.uv_eff[0] == pytest.approx(0.4 * sun.uv_eff[0])
    assert shade.discomfort[0] <= sun.discomfort[0]
    assert sun.reason[0] == 0                                     # upał


def test_main_roads_are_more_polluted(env):
    ctx = env.get("smog_2025-01-20", None)
    g = Graph(["primary", "cycleway"], [(19.94, 50.06)] * 2)
    res = _run(ctx, g)
    assert res.pm25[0] / res.pm25[1] == pytest.approx(ex.ROAD["primary"][0] / ex.ROAD["cycleway"][0], rel=1e-5)
    assert res.air_index[0] > res.air_index[1]
    assert res.reason[0] == 1                                     # powietrze


def test_road_factors_are_calibrated_from_gios():
    primary = ex.load_road_factors()["primary"]
    assert primary != ex.F_ROAD["primary"] and 1.0 <= primary[0] <= 3.0 and 1.0 <= primary[1] <= 3.0


def _ctx_with_pm10(env, values: dict):
    st = tuple(StationReading(sid, name, lat, lon, values.get(sid), None, None) for sid, name, lat, lon, _ in GIOS_STATIONS)
    return replace(env.get("smog_2025-01-20", None), stations=st)


def test_station_field_follows_nearby_background_stations(env):
    values = {sid: 40.0 for sid in STATION_LONLAT}
    values[10123] = 120.0                                          # Złoty Róg: lokalny epizod
    values[TRAFFIC_STATION] = 400.0                                # komunikacyjna nie wchodzi do tła
    g = Graph(["residential"] * 3, [STATION_LONLAT[10123], STATION_LONLAT[11303], STATION_LONLAT[TRAFFIC_STATION]])
    pm = _run(_ctx_with_pm10(env, values), g).pm25
    assert pm[0] > 1.5 * pm[1]
    assert pm[2] < pm[0]


def test_station_field_needs_three_background_stations(env):
    g = Graph(["residential"] * 2, [STATION_LONLAT[10123], STATION_LONLAT[11303]])
    pm = _run(_ctx_with_pm10(env, {10123: 120.0, 11303: 20.0}), g).pm25
    assert pm[0] == pytest.approx(pm[1])


def test_worse_conditions_never_lower_discomfort(env):
    base = env.get("heatwave_2025-07-03", None)
    g = Graph(["primary", "cycleway", "residential"], [(19.94, 50.06)] * 3)
    d0 = _run(base, g).discomfort
    for worse in ({"temperature_c": base.temperature_c + 4}, {"pm25": base.pm25 * 4, "pm10": base.pm10 * 4},
                  {"uv_index": base.uv_index + 3}, {"no2": base.no2 * 3}):
        assert (_run(replace(base, **worse), g).discomfort >= d0 - 1e-6).all(), worse


def test_sensitive_profiles_rate_smog_at_least_as_bad(env):
    ctx = env.get("smog_2025-01-20", None)
    g = Graph(["primary", "residential", "cycleway"], [(19.94, 50.06)] * 3)
    std = _run(ctx, g).discomfort
    for profile in ("asthma", "athlete"):
        assert (_run(ctx, g, profile=profile).discomfort >= std - 1e-6).all(), profile
    assert (_run(ctx, g, profile="nobody").discomfort == std).all()   # nieznany profil → standard


def test_eaqi_bands_are_revised_eea_2024():
    c = {k: np.array([v]) for k, v in {"pm25": 15.0, "pm10": 0.0, "no2": 0.0}.items()}
    assert ex.air_index(c)[0] == pytest.approx(2.0)                   # PM2.5 15 = granica fair/moderate
    c = {k: np.array([v]) for k, v in {"pm25": 0.0, "pm10": 0.0, "no2": 60.0}.items()}
    assert ex.air_index(c)[0] == pytest.approx(3.0)


def test_graph_cache_follows_the_graph(env):
    ctx = env.get("smog_2025-01-20", None)
    assert _run(ctx, Graph(["primary"] * 5, [(19.94, 50.06)] * 5)).pm25.shape == (5,)
    assert _run(ctx, Graph(["cycleway"] * 3, [(19.94, 50.06)] * 3)).pm25.shape == (3,)


def test_lut_is_found_from_any_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ex, "_luts", {})
    d = ex.discomfort("standard", np.array([20.0]), np.array([0.5]), np.array([1.0]))
    assert d[0] == pytest.approx(0.08, abs=0.01)                      # LUT (PLAN B dałby 0)


def test_plan_b_without_lut(monkeypatch, tmp_path):
    monkeypatch.setattr(ex, "LUT_DIR", tmp_path)
    monkeypatch.setattr(ex, "_luts", {})
    d = ex.discomfort("standard", np.array([38.0, 20.0]), np.array([0.5, 0.5]), np.array([1.0, 1.0]))
    assert d.tolist() == pytest.approx([1.0, 0.0])


def test_whole_city_under_100_ms(env):
    e, rng = 150_000, np.random.default_rng(0)
    g = Graph(rng.choice(["primary", "secondary", "tertiary", "residential", "cycleway", "footway"], e),
              np.column_stack([rng.uniform(19.80, 20.20, e), rng.uniform(49.98, 50.12, e)]))
    ctx = env.get("smog_2025-01-20", datetime(2025, 1, 20, 21, tzinfo=TZ))
    shade, tree = rng.random(e).astype(np.float32), rng.random(e).astype(np.float32)
    ex.compute_edge_exposure(ctx, shade, g, tree, "standard")         # cache grafu
    best = min(_timed(lambda: ex.compute_edge_exposure(ctx, shade, g, tree, "standard")) for _ in range(5))
    assert best < 0.1, f"{best * 1000:.0f} ms"


def _timed(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def _grid(dt_east: float, wind_east: float = 1.0):
    """3x3 grid; only the eastern column (20.2 E, far from the city point 19.94 E) differs."""
    from app.contracts import WeatherPoint
    lats, lons = (50.0, 50.06, 50.12), (19.8, 20.0, 20.2)
    return tuple(WeatherPoint(la, lo, dt_east if lo == 20.2 else 0.0, wind_east if lo == 20.2 else 1.0)
                 for la in lats for lo in lons)


def test_weather_grid_is_zero_at_the_city_point(env):
    """The city temperature is forecast at REF_POINT, so the field is anchored there."""
    from app.env.fetch import REF_POINT
    g = Graph(["residential"], [(REF_POINT[1], REF_POINT[0])])
    dt, wr = ex.local_weather(_grid(3.0, wind_east=0.5), g)
    assert dt[0] == pytest.approx(0.0, abs=1e-6) and wr[0] == pytest.approx(1.0)


def test_weather_grid_warms_and_calms_the_right_edges(env):
    ctx = replace(env.get("heatwave_2025-07-03", None), weather_grid=_grid(3.0))
    g = Graph(["residential"] * 3, [(19.8, 50.05), (20.1, 50.05), (20.2, 50.05)])
    plain = _run(replace(ctx, weather_grid=()), g)
    local = _run(ctx, g)
    assert local.utci_c[0] == pytest.approx(plain.utci_c[0], abs=0.15)   # west: no difference
    assert local.utci_c[2] > plain.utci_c[2] + 2                          # east: +3 °C air
    assert plain.utci_c[0] < local.utci_c[1] < local.utci_c[2]            # halfway: interpolated
    calm = _run(replace(ctx, weather_grid=_grid(0.0, wind_east=0.3)), g)
    assert calm.utci_c[2] > plain.utci_c[2] and calm.utci_c[0] == plain.utci_c[0]   # calmer east: hotter there only


def test_irregular_weather_grid_is_ignored(env):
    ctx = replace(env.get("heatwave_2025-07-03", None), weather_grid=())
    g = Graph(["residential"], [(19.9, 50.05)])
    assert ex.local_weather(_grid(3.0)[:4], g) == (0.0, 1.0)
    assert _run(replace(ctx, weather_grid=_grid(3.0)[:4]), g).utci_c[0] == _run(ctx, g).utci_c[0]


def test_whole_city_with_weather_grid_under_100_ms(env):
    e, rng = 150_000, np.random.default_rng(1)
    g = Graph(rng.choice(["primary", "residential", "cycleway"], e),
              np.column_stack([rng.uniform(19.80, 20.20, e), rng.uniform(49.98, 50.12, e)]))
    ctx = replace(env.get("heatwave_2025-07-03", None), weather_grid=_grid(2.0, 0.8))  # 3x3 test grid
    shade, tree = rng.random(e).astype(np.float32), rng.random(e).astype(np.float32)
    ex.compute_edge_exposure(ctx, shade, g, tree, "standard")
    best = min(_timed(lambda: ex.compute_edge_exposure(ctx, shade, g, tree, "standard")) for _ in range(5))
    assert best < 0.1, f"{best * 1000:.0f} ms"
