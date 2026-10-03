import time, httpx, numpy as np
from .gios_sensors import GIOS_STATIONS

W_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation,cloud_cover"
A_VARS = "pm10,pm2_5,nitrogen_dioxide,uv_index"
G = "https://api.gios.gov.pl/pjp-api/v1/rest"

def _om(url, **params):
    r = httpx.get(url, params={"latitude": 50.06, "longitude": 19.94, "timezone": "Europe/Warsaw",
                               "wind_speed_unit": "ms", **params}, timeout=20)
    r.raise_for_status()
    return r.json()["hourly"]

def fetch_hours(past_days=1, forecast_days=2, start=None, end=None) -> dict:
    """Zwraca {ISO godzina: {pogoda..., pm*_cams, pm*_city, stations: [...]}}."""
    rng = dict(start_date=start, end_date=end) if start else dict(past_days=past_days, forecast_days=forecast_days)
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
    return hours

def _city_background(cams, stations):
    """Tło miejskie: mediana stacji GIOŚ (jeśli są), inaczej CAMS. Zapisujemy też współczynnik korekty."""
    out = {}
    for k in ("pm10", "pm25", "no2"):
        vals = [s[k] for s in stations if s.get(k) is not None]
        city = float(np.median(vals)) if vals else (cams[k] if cams[k] is not None else {"pm10": 20, "pm25": 12, "no2": 20}[k])
        out[f"{k}_city"] = city
        out[f"{k}_ratio"] = (city / cams[k]) if (vals and cams[k]) else 1.0
    return out

def fetch_gios(start=None, end=None) -> dict:
    by_hour: dict[str, dict[int, dict]] = {}
    for sid, name, lat, lon, sensors in GIOS_STATIONS:
        for pol, sensor in sensors.items():
            try:
                if start:
                    url = f"{G}/archivalData/getDataBySensor/{sensor}"
                    r = httpx.get(url, params={"dateFrom": f"{start} 00:00", "dateTo": f"{end} 23:00", "size": 200}, timeout=20)
                    rows = r.json().get("Lista archiwalnych wyników pomiarów", [])
                else:
                    r = httpx.get(f"{G}/data/getData/{sensor}", params={"size": 72}, timeout=20)
                    rows = r.json().get("Lista danych pomiarowych", [])
            except Exception:
                continue                                   # brak jednej stacji ≠ awaria
            for row in rows:
                if row.get("Wartość") is None:
                    continue
                iso = row["Data"][:13].replace(" ", "T") + ":00"          # "2026-10-03 15:00:00" → "2026-10-03T15:00"
                rec = by_hour.setdefault(iso, {}).setdefault(sid, dict(station_id=sid, name=name, lat=lat, lon=lon,
                                                                         pm10=None, pm25=None, no2=None))
                rec[pol] = float(row["Wartość"])
            time.sleep(0.3)                                # grzecznie wobec limitów
    return {h: list(v.values()) for h, v in by_hour.items()}
