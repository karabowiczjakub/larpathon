# Rola 2 — Environment (Open-Meteo, GIOŚ, temperatura, UV, zanieczyszczenia, cache)

> **Twoja misja:** dostarczyć (1) `EnvironmentalContext` — warunki dla danej chwili i scenariusza, zawsze, nawet bez internetu; (2) `compute_edge_exposure()` — dla każdej krawędzi grafu: UTCI, smog, UV i **dyskomfort 0..1** z logiki rozmytej. To z Twoich liczb trasa ECO wie, czego unikać.
>
> Kontrakty (`EnvironmentalContext`, `EdgeExposure`, sygnatury) są w `04_backend_integration.md`, sekcja 4 — tam jest źródło prawdy.

---

## 1. Definition of Done

- [ ] `EnvironmentService.get("live", at)` zwraca kontekst z Open-Meteo + GIOŚ w < 5 ms (z cache), odświeżany w tle co 30 min.
- [ ] Gdy API nie działa: `source="fallback"` z `data/processed/last_live.json` albo domyślnego scenariusza — **nigdy wyjątek**.
- [ ] Scenariusze `heatwave_2025-07-03` i `smog_2025-01-20` jako JSON w `scenarios/` (cała doba godzinowo — suwak godziny działa).
- [ ] `compute_edge_exposure()` dla całego grafu w < 100 ms.
- [ ] Model fuzzy: 4 profile, tablice LUT, **testy monotoniczności zielone** (gorsze warunki nigdy nie obniżają dyskomfortu).
- [ ] Fakty do slajdu: porównanie CAMS vs GIOŚ, progi norm (UTCI/EAQI/WHO UV).

---

## 2. Co dostajesz i co oddajesz

| Dostajesz | Od kogo | Kiedy |
|---|---|---|
| `graph.edge_mid_lonlat`, `edge_highway`, `n_edges` | Rola 1 | graf v1 ~H3–H4 (do tego czasu: MockGraph) |
| `shade (E,)`, `tree_frac (E,)` jako argumenty | Rola 3 (przez Backend) | ~H8 (do tego czasu: MockShade) |

| Oddajesz | Komu | Kiedy |
|---|---|---|
| `app/env/service.py` (`EnvironmentService`) | Backend | v0 (scenariusze) H3, v1 (live) H6 |
| `app/env/exposure.py` (`compute_edge_exposure`) | Backend | v1 H6, v2 (fuzzy) H8 |
| `scenarios/*.json` | wszyscy | H4 |
| `data/processed/lut_*.npy` | Backend | H6 |

---

## 3. Źródła danych — ZWERYFIKOWANE (3.10.2026)

### 3.1 Open-Meteo (bez klucza, CC BY 4.0, 10 000 zapytań/dzień)

```bash
# Pogoda: prognoza godzinowa (live)
https://api.open-meteo.com/v1/forecast?latitude=50.06&longitude=19.94&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation,cloud_cover&wind_speed_unit=ms&forecast_days=2&past_days=1&timezone=Europe%2FWarsaw

# Pogoda: historia (scenariusze)
https://archive-api.open-meteo.com/v1/archive?latitude=50.06&longitude=19.94&start_date=2025-07-03&end_date=2025-07-03&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation,cloud_cover&wind_speed_unit=ms&timezone=Europe%2FWarsaw

# Jakość powietrza + UV (CAMS Europe ~11 km; działa też dla dat historycznych przez start_date/end_date)
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=50.06&longitude=19.94&hourly=pm10,pm2_5,nitrogen_dioxide,uv_index,european_aqi&forecast_days=2&past_days=1&timezone=Europe%2FWarsaw
```

Sprawdzone wartości: **3.07.2025 14:00** → 34,5 °C, RH 20%, wiatr 17,4 km/h, SW 862 W/m², DNI 853 W/m², chmury 0%. **20.01.2025 17:00** → CAMS PM10 161 µg/m³ (szczyt 290 o 22:00).

### 3.2 GIOŚ API v1 (bez klucza; stare endpointy bez `/v1/` wyłączone od 30.06.2025)

```
BASE = https://api.gios.gov.pl/pjp-api/v1/rest
GET {BASE}/data/getData/{sensorId}                               → bieżące (najnowsze pierwsze)
GET {BASE}/archivalData/getDataBySensor/{sensorId}?dateFrom=2025-01-20%2000:00&dateTo=2025-01-20%2023:00&size=100
```

Odpowiedź (sprawdzona): `{"Lista danych pomiarowych": [{"Kod stanowiska": "MpKrakAlKras-PM10-1g", "Data": "2026-10-03 15:00:00", "Wartość": 18.3}, ...]}` — **polskie klucze, najnowsze na początku, `Wartość` bywa `null`**. Archiwum: klucz `"Lista archiwalnych wyników pomiarów"`, te same pola. Seria 6 szybkich zapytań przeszła bez blokady, ale i tak pobieramy w tle, nie na żądanie.

**Stacje i sensory w Krakowie (pobrane z API — wklej do `app/env/gios_sensors.py`):**

```python
GIOS_STATIONS = [
    # id,   nazwa,                   lat,       lon,       {PM10, PM2.5, NO2}
    (400,   "Al. Krasińskiego",      50.057678, 19.926189, {"pm10": 2750,  "pm25": 2752, "no2": 2747}),   # komunikacyjna
    (401,   "ul. Bujaka",            50.010575, 19.949189, {"pm10": 2771,  "pm25": 2773, "no2": 2766}),   # tło
    (402,   "ul. Bulwarowa",         50.069308, 20.053492, {"pm10": 2793,  "pm25": 2794, "no2": 2788}),   # Nowa Huta
    (10123, "ul. Złoty Róg",         50.081197, 19.895358, {"pm10": 16786}),
    (10139, "Os. Piastów",           50.098508, 20.018269, {"pm10": 16784}),
    (10447, "Os. Wadów",             50.100569, 20.122561, {"pm10": 17310}),
    (11303, "Os. Swoszowice",        49.991442, 19.936792, {"pm10": 20321}),
    (16896, "ul. Kamieńskiego",      50.024605, 19.978460, {"pm10": 27841, "no2": 27843}),
    # 20367 ul. Półłanki — mierzy tylko O3, pomijamy
]
```

### 3.3 Fakt na slajd (zweryfikowany)

20.01.2025, 17:00: CAMS (Open-Meteo) **PM10 = 161 µg/m³** w centrum, stacja GIOŚ Al. Krasińskiego **63,2 µg/m³**. Model regionalny myli się nawet 2,5× → dlatego korygujemy CAMS stacjami.

---

## 4. Plan godzinowy

| H | Zadanie | Sprawdzian |
|---|---|---|
| 0–1 | Kontrakty z Backendem; `make setup` | |
| 1–3 | `pipeline/scenarios_build.py` → 2 pliki JSON (doba godzinowo, pogoda + CAMS + GIOŚ) | pliki w `scenarios/`, commit |
| 3–4 | `EnvironmentService` v0: tylko scenariusze | Backend przełącza `env` z mocka |
| 4–6 | v1: live (Open-Meteo + GIOŚ), cache TTL, wątek w tle, `last_live.json`, fallback | `/api/conditions?scenario=live` |
| 4–6 (równolegle) | `pipeline/fuzzy_build.py` — LUT dla 4 profili (kod sekcja 7, **już przetestowany**) | `pytest tests/test_fuzzy.py` |
| 6–8 | `compute_edge_exposure` v1: UTCI + PM (skalar × czynnik drogi) + UV + LUT | ECO różni się od FASTEST na mockowym cieniu |
| **8–10** | **M1** — integracja z prawdziwym cieniem; strojenie `alpha` z Backendem | ECO sensowne na Heatwave i Smog |
| 10–14 | v2 smogu: IDW stacji GIOŚ + kalibracja czynnika drogi z danych (sekcja 6.3); wyjaśnienia `reason` | mapa PM różni się przestrzennie |
| 14–17 | Sen zmianowy | |
| 17–20 | Testy, fakty na slajd (tabela norm, CAMS vs GIOŚ, wykres rozkładu dyskomfortu) | |
| **20** | Feature freeze | |

---

## 5. `EnvironmentService` — kod

```python
# app/env/service.py
from __future__ import annotations
import json, logging, threading, time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from ..contracts import EnvironmentalContext, StationReading
from .fetch import fetch_hours

TZ = ZoneInfo("Europe/Warsaw")
log = logging.getLogger(__name__)
LAT, LON = 50.06, 19.94
TTL_S = 30 * 60
DEFAULT_SCENARIO = "heatwave_2025-07-03"

class EnvironmentService:
    def __init__(self, scenario_dir: str, data_dir: str):
        self.scen = {s["id"]: s for s in (json.loads(p.read_text()) for p in Path(scenario_dir).glob("*.json"))}
        self.live_path = Path(data_dir) / "last_live.json"
        self.live: dict | None = json.loads(self.live_path.read_text()) if self.live_path.exists() else None
        self._fetched_at = 0.0
        self._lock = threading.Lock()
        self._refreshing = False
        threading.Thread(target=self._refresh, daemon=True).start()     # pierwsze pobranie w tle

    # ---------- API dla Backendu ----------
    def scenarios(self) -> list[dict]:
        out = [{"id": "live", "label": "Live now"}]
        out += [{"id": s["id"], "label": s["label"], "default_at": s["default_at"]} for s in self.scen.values()]
        return out

    def get(self, scenario: str, at: datetime | None) -> EnvironmentalContext:
        if scenario != "live" and scenario in self.scen:
            s = self.scen[scenario]
            at = at or datetime.fromisoformat(s["default_at"])
            return self._ctx_from_hours(s["hours"], at, "scenario", 0.0)
        # live
        if time.time() - self._fetched_at > TTL_S and not self._refreshing:
            threading.Thread(target=self._refresh, daemon=True).start()   # stale-while-revalidate
        live = self.live
        if live is None:                                                  # nic nie mamy → scenariusz
            s = self.scen[DEFAULT_SCENARIO]
            return self._ctx_from_hours(s["hours"], datetime.fromisoformat(s["default_at"]), "fallback", 0.0)
        age = time.time() - live["fetched_at"]
        return self._ctx_from_hours(live["hours"], at or datetime.now(TZ), "live" if age < 3 * TTL_S else "fallback", age)

    # ---------- pobieranie ----------
    def _refresh(self):
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        try:
            hours = fetch_hours(past_days=1, forecast_days=2)
            data = {"fetched_at": time.time(), "hours": hours}
            self.live = data
            self.live_path.write_text(json.dumps(data))
            self._fetched_at = time.time()
            log.info("live env refreshed: %d hours", len(hours))
        except Exception:
            log.exception("live env refresh failed — using last known / fallback")
            self._fetched_at = time.time() - TTL_S + 120      # spróbuj znów za 2 min
        finally:
            self._refreshing = False

    @staticmethod
    def _ctx_from_hours(hours: dict, at: datetime, source: str, age: float) -> EnvironmentalContext:
        at = at.astimezone(TZ)
        key = min(hours, key=lambda k: abs(datetime.fromisoformat(k).replace(tzinfo=TZ) - at))
        h = hours[key]
        st = tuple(StationReading(**x) for x in h.get("stations", []))
        return EnvironmentalContext(
            timestamp=datetime.fromisoformat(key).replace(tzinfo=TZ), source=source,
            temperature_c=h["temperature_2m"], humidity_pct=h["relative_humidity_2m"],
            wind_ms=h["wind_speed_10m"], shortwave_wm2=h["shortwave_radiation"],
            dni_wm2=h["direct_normal_irradiance"], uv_index=h["uv_index"] or 0.0,
            pm25=h["pm25_city"], pm10=h["pm10_city"], no2=h["no2_city"],
            stations=st, data_age_s=age)
```

```python
# app/env/fetch.py — wspólne dla live i scenariuszy
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
```

> Uwaga na strefy czasowe: Open-Meteo z `timezone=Europe/Warsaw` zwraca czas lokalny bez offsetu (`"2025-07-03T14:00"`), GIOŚ też czas lokalny. Wszędzie traktujemy klucze jako **czas lokalny Warszawy**. Przejście DST w październiku/marcu — ignorujemy (1 h niejednoznaczności).

### 5.1 Scenariusze (`pipeline/scenarios_build.py`)

```python
import json
from pathlib import Path
from app.env.fetch import fetch_hours

SCEN = [
    dict(id="heatwave_2025-07-03", label="Heatwave · 3 Jul 2025", day="2025-07-03", default_at="2025-07-03T14:00:00+02:00"),
    dict(id="smog_2025-01-20",     label="Smog · 20 Jan 2025",    day="2025-01-20", default_at="2025-01-20T17:00:00+01:00"),
]
Path("scenarios").mkdir(exist_ok=True)
for s in SCEN:
    hours = fetch_hours(start=s["day"], end=s["day"])
    Path(f"scenarios/{s['id']}.json").write_text(json.dumps({**s, "hours": hours}, ensure_ascii=False, indent=1))
    h = hours[s["default_at"][:16]]
    print(s["id"], "→", {k: h[k] for k in ("temperature_2m", "uv_index", "pm10_cams", "pm10_city", "pm10_ratio")})
```

Pliki commitujemy — demo nie zależy od API.

---

## 6. `compute_edge_exposure` — model krawędzi

### 6.1 Stres cieplny (UTCI) z cieniem

```
T_a,e   = T_2m − 1.0 °C · tree_frac_e · min(1, SW/600)                 # chłodzenie pod drzewami (założenie)
ΔTmrt_e = (1 − s_e) · 0.03 · DNI  +  2 °C · [SW > 100]                  # promieniowanie: słońce vs cień (aproksymacja)
Tmrt_e  = T_a,e + ΔTmrt_e
v_e     = clip(v_10m · (1 − 0.3 · tree_frac_e), 0.5, 17)               # m/s
UTCI_e  = utci(T_a,e, Tmrt_e, v_e, RH)                                   # pythermalcomfort
```

- Aproksymacja ΔTmrt: przy DNI 850 W/m² w pełnym słońcu daje ~25 °C ponad T_a — zgodne z typowymi pomiarami letnimi (Tmrt w słońcu 20–30 K powyżej powietrza). **Opisujemy jako założenie na slajdzie.**
- **Trik wydajności:** UTCI to wielomian ~200 wyrazów; liczymy go tylko dla unikalnych skwantowanych kombinacji wejść.

```python
from pythermalcomfort.models import utci as _utci

def utci_fast(ta, tmrt, v, rh):
    q = np.column_stack([np.round(ta * 2) / 2, np.round(tmrt - ta), np.round(v * 2) / 2])
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    try:
        res = _utci(tdb=uniq[:, 0], tr=uniq[:, 0] + uniq[:, 1], v=uniq[:, 2], rh=rh, limit_inputs=False)
        vals = np.asarray(getattr(res, "utci", res), dtype=np.float32)       # pythermalcomfort 2.x vs 3.x
    except Exception:
        # PLAN B (gdyby biblioteka sprawiała kłopot): uproszczony odczuwalny upał
        vals = (uniq[:, 0] + 0.33 * uniq[:, 1] - 0.7 * uniq[:, 2]).astype(np.float32)
    return vals[inv.ravel()]
```

### 6.2 Zanieczyszczenia na krawędzi

**v1 (MVP, H6):** `C_e = C_city · f_road(highway_e) · f_green(tree_frac_e)`

| highway | f_road PM | f_road NO2 |
|---|---|---|
| trunk, primary (+ _link) | 1.35 | 1.8 |
| secondary | 1.20 | 1.4 |
| tertiary | 1.10 | 1.2 |
| residential, living_street, service | 1.00 | 1.0 |
| cycleway, path, track, footway | 0.95 | 0.9 |

`f_green = 1 − 0.1 · tree_frac` (zieleń lekko obniża stężenie — założenie, opisane). Wartości f_road to **punkt startowy** — kalibrujemy w v2.

**v2 (H10–14):** przestrzenne tło z 8 stacji GIOŚ (IDW, potęga 2) — `C_bg,e = IDW(stacje → środek krawędzi)`; wagi `(E × 8)` liczymy raz przy pierwszym wywołaniu i trzymamy w pamięci. Stacje bez wartości w danej godzinie pomijamy (renormalizacja wag).

### 6.3 Kalibracja czynnika drogi z danych (argument dla jury)

Stosunek stacji **komunikacyjnej** (Al. Krasińskiego, 400) do **tła** (Bujaka, 401) z ostatnich miesięcy = empiryczny przyrost przy arterii. Skrypt `pipeline/calibrate_road.py`: pobierz `archivalData` PM10/PM2.5/NO2 z obu stacji za 90 dni, policz medianę ilorazu godzinowego → podstaw jako `f_road` dla `primary`, proporcjonalnie mniejsze dla niższych klas. Liczba „z danych, nie z sufitu" idzie na slajd.

### 6.4 Indeks powietrza (ciągły EAQI 0..6)

```python
# UWAGA: EEA zrewidowała progi EAQI — przed implementacją sprawdźcie aktualną tabelę na
# https://airindex.eea.europa.eu i podmieńcie BANDS. Poniżej klasyczne pasma (wartość tymczasowa).
BANDS = {"pm25": [0, 10, 20, 25, 50, 75, 800],
         "pm10": [0, 20, 40, 50, 100, 150, 1200],
         "no2":  [0, 40, 90, 120, 230, 340, 1000]}

def air_index(c: dict, ve_ratio: float = 1.0) -> np.ndarray:
    return np.maximum.reduce([np.interp(c[k] * ve_ratio, b, np.arange(7)) for k, b in BANDS.items()])
```

`ve_ratio` = wentylacja profilu / standard (sportowiec ~1,7): ta sama ulica „waży" dla niego więcej — fizjologia, nie arbitralna waga.

### 6.5 UV efektywne

`UV_e = UV · (1 − 0.6 · s_e)` — cień zabiera składową bezpośrednią, rozproszone UV zostaje (założenie 0,6).

### 6.6 Całość

```python
# app/env/exposure.py
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from ..contracts import EdgeExposure
from .fuzzy_profiles import PROFILES

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
        g = np.load("data/processed/lut_grid.npz")
        lut = np.load(f"data/processed/lut_{profile}.npy")
        _cache[profile] = RegularGridInterpolator((g["heat"], g["air"], g["uv"]), lut, bounds_error=False, fill_value=None)
    return _cache[profile]

def compute_edge_exposure(ctx, shade, graph, tree_frac, profile) -> EdgeExposure:
    p = PROFILES[profile]
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

    D = _lut(profile)(np.column_stack([np.clip(utci, -30, 50), np.clip(air, 0, 6), np.clip(uv, 0, 12)])) / 10.0
    sev = np.column_stack([np.clip((utci - 26) / 12, 0, 1), np.clip((air - 1) / 4, 0, 1), np.clip((uv - 3) / 6, 0, 1)])
    reason = np.where(sev.max(1) < 0.15, -1, sev.argmax(1)).astype(np.int8)
    return EdgeExposure(utci_c=utci, air_index=air, pm25=pm25, uv_eff=uv,
                        discomfort=np.clip(D, 0, 1).astype(np.float32), reason=reason)
```

**PLAN B dla fuzzy** (gdyby LUT nie był gotowy w H8): `D = clip(max((utci−26)/12, (air−1)/4, (uv−3)/6), 0, 1)` — ta sama semantyka „najgorszy czynnik decyduje", bez skfuzzy. Podmieniasz później bez zmiany interfejsu.

---

## 7. Logika rozmyta — kod PRZETESTOWANY (skfuzzy 0.5.0, 3.10.2026)

> Test wykazał pułapkę: naiwne reguły (np. `air=fair → low` obok `heat=hot → high`) dawały **spadek dyskomfortu o 2,9 pkt przy gorszym powietrzu** (centroid Mamdaniego ściągany w dół). Poniższe reguły mają **strażników** (łagodna konsekwencja tylko, gdy pozostałe czynniki też są łagodne) + projekcję monotoniczną. Wynik: 0 luk w regułach, resztkowe korekty ≤ 0,4 pkt.

```python
# app/env/fuzzy_model.py
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

HEAT_U = np.arange(-30, 50.01, 0.5); AIR_U = np.arange(0, 6.001, 0.02)
UV_U = np.arange(0, 12.001, 0.05);   OUT_U = np.arange(0, 10.001, 0.05)

def build_system(p: dict) -> ctrl.ControlSystem:
    heat = ctrl.Antecedent(HEAT_U, "heat"); air = ctrl.Antecedent(AIR_U, "air")
    uv = ctrl.Antecedent(UV_U, "uv"); out = ctrl.Consequent(OUT_U, "discomfort", defuzzify_method="centroid")
    hs, ak, uk = p["heat_shift"], p["air_scale"], p["uv_scale"]
    heat["cold"] = fuzz.trapmf(HEAT_U, [-30, -30, 0 + hs, 9 + hs])
    heat["comfortable"] = fuzz.trapmf(HEAT_U, [0 + hs, 9 + hs, 22 + hs, 26 + hs])
    heat["warm"] = fuzz.trapmf(HEAT_U, [22 + hs, 26 + hs, 30 + hs, 32 + hs])
    heat["hot"] = fuzz.trapmf(HEAT_U, [28 + hs, 32 + hs, 36 + hs, 38 + hs])
    heat["very_hot"] = fuzz.trapmf(HEAT_U, [36 + hs, 38 + hs, 50, 50])
    air["good"] = fuzz.trapmf(AIR_U, [0, 0, 1 * ak, 1.8 * ak])
    air["fair"] = fuzz.trimf(AIR_U, [1 * ak, 2 * ak, 3 * ak])
    air["poor"] = fuzz.trapmf(AIR_U, [2.5 * ak, 3.5 * ak, 4.5 * ak, 5 * ak])
    air["very_poor"] = fuzz.trapmf(AIR_U, [4.5 * ak, 5.5 * ak, 6, 6])
    uv["low"] = fuzz.trapmf(UV_U, [0, 0, 2 * uk, 3 * uk])
    uv["moderate"] = fuzz.trimf(UV_U, [2 * uk, 4 * uk, 6 * uk])
    uv["high"] = fuzz.trapmf(UV_U, [5 * uk, 6 * uk, 7 * uk, 8 * uk])
    uv["very_high"] = fuzz.trapmf(UV_U, [7 * uk, 8.5 * uk, 12, 12])
    out["none"] = fuzz.trapmf(OUT_U, [0, 0, 1, 2]); out["low"] = fuzz.trimf(OUT_U, [1, 2.5, 4])
    out["medium"] = fuzz.trimf(OUT_U, [3, 5, 7]);  out["high"] = fuzz.trimf(OUT_U, [6, 7.5, 9])
    out["extreme"] = fuzz.trapmf(OUT_U, [8, 9, 10, 10])

    heat_ok = heat["comfortable"]; heat_mild = heat["warm"] | heat["cold"]
    heat_le_mild = heat["comfortable"] | heat["warm"] | heat["cold"]
    air_le_fair = air["good"] | air["fair"]
    uv_ok = uv["low"] | uv["moderate"]; uv_le_high = uv["low"] | uv["moderate"] | uv["high"]
    c = p["consequents"]
    return ctrl.ControlSystem([
        ctrl.Rule(air["very_poor"] | heat["very_hot"], out["extreme"]),                     # R1
        ctrl.Rule(air["poor"] & (heat["hot"] | uv["very_high"]), out["extreme"]),           # R2
        ctrl.Rule(heat["hot"] & uv["very_high"], out["extreme"]),                           # R3
        ctrl.Rule(heat["hot"] & air_le_fair & uv_le_high, out["high"]),                     # R4
        ctrl.Rule(air["poor"] & heat_le_mild & uv_le_high, out[c.get("R5", "high")]),       # R5
        ctrl.Rule(uv["very_high"] & heat_le_mild & air_le_fair, out["high"]),               # R6
        ctrl.Rule(uv["high"] & heat_le_mild & air_le_fair, out["medium"]),                  # R7
        ctrl.Rule(heat_mild & air["fair"] & uv_ok, out["medium"]),                          # R8
        ctrl.Rule(heat_mild & air["good"] & uv_ok, out[c.get("R9", "low")]),                # R9
        ctrl.Rule(air["fair"] & heat_ok & uv_ok, out[c.get("R10", "low")]),                 # R10
        ctrl.Rule(air["good"] & heat_ok & uv_ok, out["none"]),                              # R11
    ])
```

```python
# app/env/fuzzy_profiles.py
PROFILES = {
    "standard": dict(heat_shift=0,  air_scale=1.0, uv_scale=1.0, ve_ratio=1.0,  consequents={}),
    "asthma":   dict(heat_shift=0,  air_scale=0.7, uv_scale=1.0, ve_ratio=1.0,  consequents={"R10": "medium", "R5": "extreme"}),
    "senior":   dict(heat_shift=-3, air_scale=1.0, uv_scale=0.8, ve_ratio=0.85, consequents={"R9": "medium"}),
    "athlete":  dict(heat_shift=-2, air_scale=1.0, uv_scale=1.0, ve_ratio=1.7,  consequents={}),
}
```

```python
# pipeline/fuzzy_build.py
import numpy as np
from joblib import Parallel, delayed
from skfuzzy import control as ctrl
from app.env.fuzzy_model import build_system
from app.env.fuzzy_profiles import PROFILES

G_HEAT = np.arange(-30, 50.01, 2.0); G_AIR = np.arange(0, 6.001, 0.2); G_UV = np.arange(0, 12.001, 1.0)

def monotone(lut, heat_grid, comfort_hi=22.0):
    out = np.maximum.accumulate(lut, axis=1)                       # air ↑
    out = np.maximum.accumulate(out, axis=2)                       # uv ↑
    hot = heat_grid >= comfort_hi
    out[hot] = np.maximum.accumulate(out[hot], axis=0)             # upał ↑
    out[~hot] = np.maximum.accumulate(out[~hot][::-1], axis=0)[::-1]   # mróz ↓
    return out

def slab(p, h):
    sim = ctrl.ControlSystemSimulation(build_system(p), cache=False)
    row = np.full((len(G_AIR), len(G_UV)), np.nan, np.float32)
    for j, a in enumerate(G_AIR):
        for k, u in enumerate(G_UV):
            sim.input["heat"], sim.input["air"], sim.input["uv"] = h, a, u
            try:
                sim.compute(); row[j, k] = sim.output["discomfort"]
            except (ValueError, KeyError):
                pass
    return row

for name, p in PROFILES.items():
    lut = np.stack(Parallel(n_jobs=-1)(delayed(slab)(p, h) for h in G_HEAT))
    assert not np.isnan(lut).any(), f"{name}: luka w regułach"
    np.save(f"data/processed/lut_{name}.npy", monotone(lut, G_HEAT, 22 + p["heat_shift"]))
    print(name, "ok")
np.savez("data/processed/lut_grid.npz", heat=G_HEAT, air=G_AIR, uv=G_UV)
```

**Zmierzone:** ~11–17 ms na komórkę skfuzzy → ~3–4 min na profil na 1 rdzeniu; z `joblib` ~2 min dla wszystkich na 8 rdzeniach. Przy iterowaniu nad regułami używaj grubszej siatki.

**Zmierzone wartości (Standard):** UTCI 20/air 0,5/UV 1 → **0,8** · UTCI 20/air 4 → **7,5** · UTCI 28/air 2/UV 4 → **5,0** · UTCI 34/UV 9 → **9,2** · zima UTCI 4/air 4 → **7,5**. Senior przy UTCI 28: **6,2** vs 2,5 (Standard). Astma przy air 2,5: **9,2** vs 2,5 — agresywne, do strojenia (np. R5 zostawić `high`).

---

## 8. Testy

```python
# tests/test_fuzzy.py
import numpy as np, pytest
from app.env.fuzzy_profiles import PROFILES

@pytest.mark.parametrize("name", list(PROFILES))
def test_lut_complete_and_monotone(name):
    lut = np.load(f"data/processed/lut_{name}.npy"); g = np.load("data/processed/lut_grid.npz")
    assert not np.isnan(lut).any()
    assert (np.diff(lut, axis=1) >= -1e-6).all()          # gorsze powietrze → nie mniej
    assert (np.diff(lut, axis=2) >= -1e-6).all()          # wyższe UV → nie mniej
    hot = g["heat"] >= 22 + PROFILES[name]["heat_shift"]
    assert (np.diff(lut[hot], axis=0) >= -1e-6).all()     # większy upał → nie mniej

def test_profiles_order():
    s, a, sen = (np.load(f"data/processed/lut_{n}.npy") for n in ("standard", "asthma", "senior"))
    assert (a >= s - 0.5).all()        # astma nigdy wyraźnie łagodniejsza
    assert sen.mean() >= s.mean()
```

```python
# tests/test_env.py
from datetime import datetime
from zoneinfo import ZoneInfo
from app.env.service import EnvironmentService

def test_scenarios_offline():
    env = EnvironmentService("scenarios", "/tmp")
    ctx = env.get("heatwave_2025-07-03", None)
    assert ctx.source == "scenario" and 30 < ctx.temperature_c < 40 and ctx.dni_wm2 > 500
    ctx = env.get("smog_2025-01-20", datetime(2025, 1, 20, 21, tzinfo=ZoneInfo("Europe/Warsaw")))
    assert ctx.pm10 > 50

def test_live_never_raises(monkeypatch):
    import app.env.service as s
    monkeypatch.setattr(s, "fetch_hours", lambda **k: (_ for _ in ()).throw(RuntimeError("offline")))
    ctx = EnvironmentService("scenarios", "/tmp/nonexistent_dir_ok").get("live", None)
    assert ctx.source in ("fallback", "live")
```

---

## 9. Ryzyka i plan B

| Ryzyko | Plan B |
|---|---|
| Open-Meteo/GIOŚ nie odpowiada | `last_live.json` → scenariusz domyślny; UI pokazuje „data age" |
| GIOŚ zwraca `null` / brak stacji | `_city_background` bierze CAMS; brak jednej stacji nie przerywa pobierania |
| pythermalcomfort zmienia API | `getattr(res, "utci", res)` + formuła awaryjna w `utci_fast` |
| LUT fuzzy nie gotowy | wzór „najgorszy czynnik" (sekcja 6.6), ten sam interfejs |
| ECO == FASTEST w październiku (live: zimno, czysto) | demo na scenariuszach; to też uczciwy komunikat „dziś najszybsza = najzdrowsza" |
| Progi EAQI nieaktualne | sprawdzić na stronie EEA na starcie (5 min), podmienić `BANDS` |

## 10. Czego NIE robić

- Nie wołaj API przy każdym żądaniu użytkownika — tylko wątek w tle / skrypty offline.
- Nie rób Sentinel-5P (piksel ~5,5 × 3,5 km, nie mierzy PM10) ani Google Earth Engine (rejestracja projektu).
- Nie strój 30 parametrów — ustal założenia, opisz je na slajdzie, przejdź dalej.
- Nie zmieniaj sygnatur z `contracts.py` bez Backendu.
