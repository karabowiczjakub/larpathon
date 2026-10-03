import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import numpy as np

from .gios_sensors import GIOS_STATIONS

W_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation,cloud_cover"
A_VARS = "pm10,pm2_5,nitrogen_dioxide,uv_index"
G = "https://api.gios.gov.pl/pjp-api/v1/rest"
TZ = ZoneInfo("Europe/Warsaw")
CET = timezone(timedelta(hours=1))      # archiwum GIOŚ podaje godziny w CET (UTC+1) przez cały rok
POLLUTANTS = ("pm10", "pm25", "no2")
STATION_CARRY_H = 3                     # tyle godzin po ostatnim pomiarze pokazujemy odczyty stacji
RATIO_RANGE = (0.3, 3.0)                # granice przenoszonej korekty CAMS (jak r_s w PLAN 8.3)
log = logging.getLogger(__name__)


def _om(url, **params):
    r = httpx.get(url, params={"latitude": 50.06, "longitude": 19.94, "timezone": "Europe/Warsaw",
                               "wind_speed_unit": "ms", **params}, timeout=20)
    r.raise_for_status()
    return r.json()["hourly"]


def fetch_hours(past_days=1, forecast_days=2, start=None, end=None) -> dict:
    """Zwraca {ISO godzina: {pogoda..., pm*_cams, pm*_city, stations: [...]}}."""
    rng = {"start_date": start, "end_date": end} if start else {"past_days": past_days, "forecast_days": forecast_days}
    w_url = "https://archive-api.open-meteo.com/v1/archive" if start else "https://api.open-meteo.com/v1/forecast"
    w = _om(w_url, hourly=W_VARS, **rng)
    a = _om("https://air-quality-api.open-meteo.com/v1/air-quality", hourly=A_VARS, **rng)
    gios = fetch_gios(start, end)                        # {iso_hour: [StationReading-dict, ...]}
    hours = {}
    for i, t in enumerate(w["time"]):
        j = a["time"].index(t) if t in a["time"] else None
        cams = {k: (a[v][j] if j is not None else None) for k, v in
                (("pm10", "pm10"), ("pm25", "pm2_5"), ("no2", "nitrogen_dioxide"), ("uv", "uv_index"))}
        st = gios.get(t, [])
        h = {k: w[k][i] for k in W_VARS.split(",")}
        h.update(uv_index=cams["uv"], pm10_cams=cams["pm10"], pm25_cams=cams["pm25"], no2_cams=cams["no2"], stations=st)
        h.update(_city_background(cams, st))
        hours[t] = h
    _fill_gaps(hours)
    return hours


def _city_background(cams, stations):
    """Tło miejskie: mediana stacji GIOŚ (jeśli są), inaczej CAMS. Zapisujemy też współczynnik korekty."""
    out = {}
    for k in POLLUTANTS:
        vals = [s[k] for s in stations if s.get(k) is not None]
        city = float(np.median(vals)) if vals else (cams[k] if cams[k] is not None else {"pm10": 20, "pm25": 12, "no2": 20}[k])
        out[f"{k}_city"] = city
        out[f"{k}_ratio"] = (city / cams[k]) if (vals and cams[k]) else 1.0
    return out


def _fill_gaps(hours: dict) -> None:
    """GIOŚ publikuje z opóźnieniem 1–2 h, a prognoza nie ma pomiarów. Dla takich godzin korygujemy
    CAMS ostatnim zmierzonym współczynnikiem, a przez STATION_CARRY_H godzin zostawiamy ostatnie
    odczyty stacji (wzór przestrzenny dla IDW; `stations_at` mówi, z której godziny pochodzą)."""
    ratio, stations, measured_at, last_i = {}, [], None, 0
    for i, key in enumerate(sorted(hours)):
        h = hours[key]
        if h["stations"]:
            ratio = {k: h[f"{k}_ratio"] for k in POLLUTANTS}
            stations, measured_at, last_i = h["stations"], key, i
            continue
        if stations and i - last_i <= STATION_CARRY_H:
            h["stations"], h["stations_at"] = stations, measured_at
        for k, r in ratio.items():
            if h[f"{k}_cams"] is not None:
                r = float(np.clip(r, *RATIO_RANGE))
                h[f"{k}_city"], h[f"{k}_ratio"] = h[f"{k}_cams"] * r, r


def _gios_get(path: str, params: dict, tries: int = 3) -> dict:
    for attempt in range(tries):
        try:
            r = httpx.get(f"{G}/{path}", params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError):
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def gios_series(sensor: int, start: str | None = None, end: str | None = None) -> dict[str, float]:
    """{godzina lokalna ISO: wartość} dla jednego stanowiska. Bez `start`: bieżące 3 doby
    (czas lokalny); ze `start`/`end` (daty YYYY-MM-DD): archiwum w CET, przeliczane na czas lokalny."""
    if start is None:
        rows = _gios_get(f"data/getData/{sensor}", {"size": 72}).get("Lista danych pomiarowych", [])
        return {row["Data"][:13].replace(" ", "T") + ":00": float(row["Wartość"])
                for row in rows if row.get("Wartość") is not None}
    lo = datetime.fromisoformat(start).replace(tzinfo=TZ).astimezone(CET)
    hi = (datetime.fromisoformat(end) + timedelta(hours=23)).replace(tzinfo=TZ).astimezone(CET)
    params = {"dateFrom": lo.strftime("%Y-%m-%d %H:%M"), "dateTo": hi.strftime("%Y-%m-%d %H:%M"), "size": 500}
    out, page, pages = {}, 0, 1
    while page < pages:
        if page:
            time.sleep(0.3)
        data = _gios_get(f"archivalData/getDataBySensor/{sensor}", {**params, "page": page})
        pages = int(data.get("totalPages", 1))
        for row in data.get("Lista archiwalnych wyników pomiarów", []):
            if row.get("Wartość") is not None:
                t = datetime.fromisoformat(row["Data"]).replace(tzinfo=CET).astimezone(TZ)
                out[t.strftime("%Y-%m-%dT%H:00")] = float(row["Wartość"])
        page += 1
    return out


def fetch_gios(start=None, end=None) -> dict:
    by_hour: dict[str, dict[int, dict]] = {}
    for sid, name, lat, lon, sensors in GIOS_STATIONS:
        for pol, sensor in sensors.items():
            try:
                series = gios_series(sensor, start, end)
            except (httpx.HTTPError, ValueError, KeyError) as e:
                log.warning("GIOŚ sensor %s (%s) skipped: %s", sensor, name, e)
                continue                                   # brak jednej stacji ≠ awaria
            for iso, value in series.items():
                rec = by_hour.setdefault(iso, {}).setdefault(sid, {"station_id": sid, "name": name, "lat": lat, "lon": lon,
                                                                         "pm10": None, "pm25": None, "no2": None})
                rec[pol] = value
            time.sleep(0.3)                                # grzecznie wobec limitów
    return {h: list(v.values()) for h, v in by_hour.items()}
