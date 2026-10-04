import json
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import app.env.service as svc
from app.env import fetch
from app.env.service import EnvironmentService

TZ = ZoneInfo("Europe/Warsaw")
SCEN = Path(__file__).resolve().parents[1] / "scenarios"


@pytest.fixture
def offline(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(svc, "fetch_hours", fail)


def _smog_hours() -> dict:
    return json.loads((SCEN / "smog_2025-01-20.json").read_text(encoding="utf-8"))["hours"]


def test_scenarios_offline(tmp_path):
    env = EnvironmentService(SCEN, tmp_path, refresh=False)
    ids = [s["id"] for s in env.scenarios()]
    assert ids[0] == "live" and {"heatwave_2025-07-03", "smog_2025-01-20"} <= set(ids)
    ctx = env.get("heatwave_2025-07-03", None)
    assert ctx.source == "scenario" and 30 < ctx.temperature_c < 40 and ctx.dni_wm2 > 500
    assert ctx.timestamp == datetime(2025, 7, 3, 14, tzinfo=TZ)
    ctx = env.get("smog_2025-01-20", datetime(2025, 1, 20, 21, tzinfo=TZ))
    assert ctx.pm10 > 50 and len(ctx.stations) >= 6


def test_scenarios_are_full_measured_days():
    for path in SCEN.glob("*.json"):
        hours = json.loads(path.read_text(encoding="utf-8"))["hours"]
        assert len(hours) == 24, path.name
        assert all(h["stations"] for h in hours.values()), path.name


def test_scenario_hour_slider_stays_on_scenario_day(tmp_path):
    env = EnvironmentService(SCEN, tmp_path, refresh=False)
    ctx = env.get("heatwave_2025-07-03", datetime(2026, 10, 3, 9, tzinfo=TZ))
    assert ctx.timestamp == datetime(2025, 7, 3, 9, tzinfo=TZ)
    assert env.get("smog_2025-01-20", datetime(2025, 1, 20, 22)).timestamp.hour == 22  # noqa: DTZ001 — naive = czas Warszawy


def test_live_never_raises(monkeypatch, tmp_path):
    tried = threading.Event()

    def fail(**kwargs):
        tried.set()
        raise RuntimeError("offline")

    monkeypatch.setattr(svc, "fetch_hours", fail)
    env = EnvironmentService(SCEN, tmp_path)               # wątek w tle trafia w "offline"
    assert tried.wait(5)                                   # zanim monkeypatch zniknie — bez prawdziwej sieci w testach
    assert env.get("live", None).source == "fallback"
    assert not env.refresh()


def test_live_without_scenarios_or_cache(offline, tmp_path):
    ctx = EnvironmentService(tmp_path, tmp_path, refresh=False).get("live", None)
    assert ctx.source == "fallback" and ctx.temperature_c == 20.0


def test_live_from_cache_becomes_fallback_when_stale(tmp_path):
    (tmp_path / "last_live.json").write_text(json.dumps({"fetched_at": time.time() - 60, "hours": _smog_hours()}))
    env = EnvironmentService(SCEN, tmp_path, refresh=False)
    at = datetime(2025, 1, 20, 17, tzinfo=TZ)
    ctx = env.get("live", at)
    assert ctx.source == "live" and 50 < ctx.data_age_s < 120 and ctx.pm10 > 50
    env.live["fetched_at"] -= 4 * svc.TTL_S
    assert env.get("live", at).source == "fallback"


def test_refresh_writes_last_live_and_get_is_fast(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "fetch_hours", lambda **kw: _smog_hours())
    env = EnvironmentService(SCEN, tmp_path / "processed", refresh=False)
    assert env.refresh() and (tmp_path / "processed" / "last_live.json").exists()
    t0 = time.perf_counter()
    for _ in range(100):
        ctx = env.get("live", datetime(2025, 1, 20, 17, tzinfo=TZ))
    assert ctx.source == "live"
    assert (time.perf_counter() - t0) / 100 < 0.005


def _hour(stations: list) -> dict:
    cams = {"pm10": 40.0, "pm25": 30.0, "no2": 20.0}
    h = {f"{k}_cams": v for k, v in cams.items()}
    h["stations"] = stations
    h.update(fetch._city_background(cams, stations))
    return h


def test_fill_gaps_carries_gios_correction_into_unmeasured_hours():
    st = [{"station_id": 401, "name": "ul. Bujaka", "lat": 50.01, "lon": 19.95, "pm10": 20.0, "pm25": None, "no2": 10.0}]
    hours = {f"2026-10-03T{10 + i:02d}:00": _hour(st if i < 2 else []) for i in range(6)}
    fetch._fill_gaps(hours)
    h = hours["2026-10-03T13:00"]
    assert h["pm10_city"] == pytest.approx(20.0)          # CAMS 40 × ostatnia korekta 0,5 (nie surowy CAMS)
    assert h["pm25_city"] == pytest.approx(30.0)          # brak pomiaru PM2.5 → korekta 1
    assert h["stations"] == st and h["stations_at"] == "2026-10-03T11:00"
    late = hours["2026-10-03T15:00"]
    assert late["stations"] == [] and late["pm10_city"] == pytest.approx(20.0)


def test_gios_archive_is_cet_and_paged(monkeypatch):
    calls = []

    def fake(path, params, tries=3):
        calls.append(params)
        rows = [[{"Data": "2025-07-03 13:00:00", "Wartość": 30.0}], [{"Data": "2025-07-03 14:00:00", "Wartość": None}]]
        return {"Lista archiwalnych wyników pomiarów": rows[params["page"]], "totalPages": 2}

    monkeypatch.setattr(fetch, "_gios_get", fake)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    assert fetch.gios_series(2750, "2025-07-03", "2025-07-03") == {"2025-07-03T14:00": 30.0}   # 13:00 CET = 14:00 CEST
    assert calls[0]["dateFrom"] == "2025-07-02 23:00" and len(calls) == 2


def test_weather_grid_is_relative_to_the_city_point(monkeypatch):
    """One multi-location call: the first location is REF_POINT, the rest GRID_POINTS (row-major)."""
    n = len(fetch.GRID_POINTS)

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            ref = {"hourly": {"time": ["2025-07-03T03:00"], "temperature_2m": [17.0], "wind_speed_10m": [2.0]}}
            cells = [{"hourly": {"time": ["2025-07-03T03:00"], "temperature_2m": [17.0 + i * 0.1], "wind_speed_10m": [1.0]}}
                     for i in range(n)]
            return [ref, *cells]

    calls = []
    monkeypatch.setattr(fetch.httpx, "get", lambda url, params, timeout: calls.append((url, params)) or Resp())
    grid = fetch.fetch_grid({"start_date": "2025-07-03", "end_date": "2025-07-03"}, fetch.HISTORICAL_FORECAST_URL)
    g = grid["2025-07-03T03:00"]
    assert g["dt"][0] == 0.0 and g["dt"][-1] == pytest.approx((n - 1) * 0.1) and g["wr"] == [0.5] * n
    assert calls[0][1]["latitude"].split(",")[0] == str(fetch.REF_POINT[0]) and len(calls[0][1]["latitude"].split(",")) == n + 1


def test_weather_grid_failure_means_uniform_weather(monkeypatch):
    def down(*a, **kw):
        raise fetch.httpx.ConnectError("offline")
    monkeypatch.setattr(fetch.httpx, "get", down)
    assert fetch.fetch_grid_safe({"past_days": 1}, fetch.FORECAST_URL) == {}


def test_context_carries_the_weather_grid(tmp_path):
    hours = _smog_hours()
    key = "2025-01-20T17:00"
    n = len(fetch.GRID_POINTS)
    hours[key] = {**hours[key], "grid": {"dt": [0.5] * n, "wr": [0.8] * n}}
    ctx = EnvironmentService._ctx_from_hours(hours, datetime(2025, 1, 20, 17, tzinfo=TZ), "scenario", 0.0)
    assert len(ctx.weather_grid) == n and ctx.weather_grid[0].dt_c == 0.5 and ctx.weather_grid[0].wind_ratio == 0.8
    assert "weather_grid" not in ctx.summary() and "stations" not in ctx.summary()
    old_file = {t: {k: v for k, v in h.items() if k != "grid"} for t, h in _smog_hours().items()}
    old = EnvironmentService._ctx_from_hours(old_file, datetime(2025, 1, 20, 17, tzinfo=TZ), "scenario", 0.0)
    assert old.weather_grid == ()          # scenario files without a grid: the same weather everywhere
