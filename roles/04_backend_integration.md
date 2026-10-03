# Rola 4 — Backend + Integration (Flask, API, EnvironmentalContext, łączenie modułów)

> **Twoja misja:** w każdej minucie hackathonu istnieje *działająca* aplikacja end-to-end — najpierw na atrapach (mockach), potem moduł po module na prawdziwych danych. Jesteś właścicielem **kontraktów** (ten plik jest dla nich źródłem prawdy) i **integracji**. Nie piszesz algorytmów innych ról — składasz je.

---

## 1. Definition of Done (co musi działać na demo)

- [ ] `POST /api/route` zwraca trasy **FASTEST** i **ECO** dla punktów A→B (opcjonalnie przez punkty pośrednie) w **< 1 s** (p95, laptop demo).
- [ ] Odpowiedź zawiera geometrię, metryki obu tras i **porównanie** (Δ czasu, Δ dawki PM2.5, Δ cienia, Δ minut w upale).
- [ ] `GET /api/conditions`, `GET /api/scenarios`, `GET /api/health` działają.
- [ ] Scenariusze **Live / Heatwave 3.07.2025 14:00 / Smog 20.01.2025 17:00** + parametr godziny wyjazdu.
- [ ] Aplikacja **nigdy nie zwraca 500 przez zewnętrzne API** — środowisko ma fallback (sekcja 8).
- [ ] `USE_MOCKS=1` uruchamia całość bez żadnych danych (ratunek na demo i dla Frontendu).
- [ ] Testy kontraktowe zielone (`pytest -q`).

---

## 2. Strategia „100% szans": mock-first + kontrakty zamrożone w H1

1. **H0–H1:** ustalasz z zespołem kontrakty z sekcji 4 (15 min rozmowy, potem zamrożone; zmiana tylko przez Ciebie).
2. **H1–H2:** commitujesz szkielet repo + **mocki wszystkich modułów** + działające API na mockach. Od tej chwili Frontend pracuje na prawdziwym API, a nie na plikach.
3. Każda rola podmienia swój mock na prawdziwą implementację **za tym samym interfejsem**. Ty pilnujesz testów kontraktowych.
4. **M1 (H8–H10):** prawdziwy graf + prawdziwe środowisko + cień statyczny → FASTEST i ECO na żywo.
5. **H20: feature freeze.** Od tej chwili tylko bugfixy.

Jeśli którykolwiek moduł nie dowiezie — jego mock zostaje i demo nadal działa (z uczciwą informacją na slajdzie).

---

## 3. Struktura repozytorium (całość — zakładasz w H1)

```
airroute/
├── README.md
├── requirements.txt
├── Makefile
├── .env.example
├── app/
│   ├── __init__.py            # create_app() — TY
│   ├── api.py                 # blueprint /api — TY
│   ├── engine.py              # składanie modułów, koszty, metryki — TY
│   ├── contracts.py           # dataclassy wspólne — TY (źródło prawdy)
│   ├── mocks.py               # atrapy wszystkich modułów — TY
│   ├── schemas.py             # walidacja requestów (pydantic) — TY
│   ├── graph/                 # ROLA 1 (Graph + Routing)
│   │   └── routing.py         #   class RoutingGraph
│   ├── env/                   # ROLA 2 (Environment)
│   │   ├── service.py         #   class EnvironmentService
│   │   ├── exposure.py        #   compute_edge_exposure()
│   │   └── fuzzy.py           #   model dyskomfortu (LUT)
│   ├── shade/                 # ROLA 3 (Shade + Buildings + Sun)
│   │   ├── sun.py             #   sun_position()
│   │   └── model.py           #   class ShadeModel
│   └── static/                # ROLA 5 (Frontend)
│       ├── index.html  style.css  app.js
│       └── mock/route.json
├── pipeline/                  # skrypty offline (każda rola swoje)
│   ├── graph_build.py         #   ROLA 1
│   ├── shade_build.py         #   ROLA 3
│   ├── fuzzy_build.py         #   ROLA 2
│   └── scenarios_build.py     #   ROLA 2
├── scenarios/                 # JSON-y scenariuszy (commitowane)
├── data/processed/            # artefakty offline (.gitignore, udostępniane przez dysk)
└── tests/
    ├── test_contracts.py      # TY
    ├── test_api.py            # TY
    └── test_<moduł>.py        # każda rola
```

**Git:** gałąź per rola (`graph`, `env`, `shade`, `backend`, `frontend`), merge do `main` przez Ciebie w kamieniach milowych. `main` zawsze się uruchamia. Katalog `data/` nie trafia do gita — artefakty idą przez wspólny dysk (Google Drive / pendrive).

---

## 4. KONTRAKTY (źródło prawdy dla wszystkich ról)

### 4.1 Zasada nadrzędna: `eid`

**Każda tablica „per krawędź" w całym systemie ma długość `E` i kolejność `eid` z `data/processed/edges.parquet` (Rola 1).** Cień, ekspozycja, koszty — wszystko indeksowane tym samym `eid`. Rola 1 publikuje graf jako pierwsza; jeśli przebuduje graf, **wszyscy przeliczają swoje artefakty** (dlatego graf zamrażamy w H4).

### 4.2 Artefakty offline (`data/processed/`)

| Plik | Właściciel | Zawartość |
|---|---|---|
| `graph.npz` | Rola 1 | `indptr, indices, perm` (CSR, slot→eid), `node_x, node_y` (EPSG:2180), `node_lon, node_lat`, `edge_u, edge_v` (int32), `edge_length_m` (float32), `edge_mid_lon, edge_mid_lat` (float32) |
| `edges.parquet` | Rola 1 | `eid, u, v, length_m, highway, name, geometry` (EPSG:2180) |
| `edge_coords.npz` | Rola 1 | `coords` (M×2 float32, lon/lat), `offs` (E+1) — geometrie do odpowiedzi API |
| `shade.npy` + `shade_bins.json` | Rola 3 | `uint8 (E, 16, 8)` = udział cienia ×255 dla 16 azymutów × 8 elewacji |
| `edge_tree_frac.npy` | Rola 3 | `float32 (E,)` udział punktów krawędzi pod koronami drzew |
| `lut_<profile>.npy`, `lut_grid.npz` | Rola 2 | tablice dyskomfortu fuzzy |
| `scenarios/*.json` | Rola 2 | zamrożone warunki scenariuszy (w gicie) |

### 4.3 Interfejsy Pythona (`app/contracts.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
import numpy as np

# ---------- Rola 2: Environment ----------
@dataclass(frozen=True)
class StationReading:
    station_id: int
    name: str
    lat: float
    lon: float
    pm10: float | None
    pm25: float | None
    no2: float | None

@dataclass(frozen=True)
class EnvironmentalContext:
    timestamp: datetime                 # tz-aware, Europe/Warsaw — chwila, której dotyczą dane
    source: Literal["live", "scenario", "fallback", "mock"]
    temperature_c: float
    humidity_pct: float
    wind_ms: float                      # 10 m n.p.t.
    shortwave_wm2: float
    dni_wm2: float                      # direct normal irradiance
    uv_index: float
    pm25: float                         # tło miejskie po korekcie GIOŚ [µg/m³]
    pm10: float
    no2: float
    stations: tuple[StationReading, ...] = ()
    data_age_s: float = 0.0

    def summary(self) -> dict: ...      # płaski dict do JSON (implementuje Rola 2)

@dataclass
class EdgeExposure:                     # wszystkie tablice (E,)
    utci_c: np.ndarray
    air_index: np.ndarray               # ciągły EAQI 0..6
    pm25: np.ndarray                    # µg/m³ na krawędzi
    uv_eff: np.ndarray
    discomfort: np.ndarray              # 0..1 (fuzzy/10)
    reason: np.ndarray                  # int8: -1 ok, 0 heat, 1 air, 2 uv

class EnvironmentServiceP(Protocol):
    def get(self, scenario: str, at: datetime | None) -> EnvironmentalContext: ...
    def scenarios(self) -> list[dict]: ...

# compute_edge_exposure(ctx, shade (E,), graph: RoutingGraphP, tree_frac (E,), profile: str) -> EdgeExposure

# ---------- Rola 3: Shade + Sun ----------
@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float                  # od północy, zgodnie z zegarem
    elevation_deg: float                # < 0 = noc

class ShadeModelP(Protocol):
    edge_tree_frac: np.ndarray          # (E,)
    def sun(self, at: datetime) -> SunPosition: ...
    def edge_shade(self, at: datetime) -> np.ndarray: ...   # (E,) float32 0..1

# ---------- Rola 1: Graph + Routing ----------
@dataclass
class Route:
    eids: np.ndarray                    # int64, kolejne krawędzie trasy
    node_path: np.ndarray

class RoutingGraphP(Protocol):
    n_edges: int
    edge_length_m: np.ndarray           # (E,)
    edge_mid_lonlat: np.ndarray         # (E, 2)
    edge_highway: np.ndarray            # (E,) object/str
    edge_name: np.ndarray               # (E,) object/str|None
    def snap(self, lat: float, lon: float) -> int: ...                     # raises PointOutsideArea
    def route(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> Route: ...  # raises NoRoute
    def geometry(self, eids: np.ndarray) -> list[list[float]]: ...         # [[lon, lat], ...]

class PointOutsideArea(Exception): ...
class NoRoute(Exception): ...
```

### 4.4 API HTTP (dla Frontendu)

**`POST /api/route`**

```json
{
  "points": [{"lat": 50.0614, "lon": 19.9366}, {"lat": 50.0675, "lon": 19.9128}],
  "scenario": "heatwave_2025-07-03",
  "depart_at": "2025-07-03T14:00:00+02:00",
  "profile": "standard"
}
```

- `points`: 2–5 punktów (A, opcjonalne via, B). `scenario`: `live` | id z `/api/scenarios`. `depart_at`: opcjonalny (domyślnie: teraz / domyślna chwila scenariusza). `profile`: `standard | asthma | senior | athlete`.

```json
{
  "routes": [
    {
      "id": "fastest", "label": "Fastest", "color": "#6b7280",
      "geometry": {"type": "LineString", "coordinates": [[19.9366, 50.0614], "..."]},
      "metrics": {"distance_m": 2310, "time_min": 9.2, "avg_discomfort": 6.1,
                  "shade_pct": 22.0, "pm25_dose_ug": 4.1, "heat_stress_min": 5.5},
      "segments": [{"from": 0, "to": 14, "discomfort": 0.71, "reason": "heat"}],
      "avoids": []
    },
    {
      "id": "eco", "label": "Healthier", "color": "#16a34a",
      "geometry": {"type": "LineString", "coordinates": ["..."]},
      "metrics": {"distance_m": 2780, "time_min": 11.1, "avg_discomfort": 3.4,
                  "shade_pct": 58.0, "pm25_dose_ug": 3.0, "heat_stress_min": 1.5},
      "segments": ["..."],
      "avoids": ["Al. Mickiewicza (heat, no shade)"]
    }
  ],
  "comparison": {"time_delta_min": 1.9, "time_delta_pct": 20.7, "pm25_dose_delta_pct": -26.8,
                 "shade_delta_pp": 36.0, "heat_stress_delta_min": -4.0},
  "conditions": {"source": "scenario", "temperature_c": 34.5, "uv_index": 8.1, "pm10": 21.0, "...": "..."},
  "sun": {"azimuth_deg": 215.0, "elevation_deg": 59.0},
  "timing_ms": {"env": 0.4, "shade": 3.1, "exposure": 41.0, "routing": 290.0, "total": 342.0}
}
```

- `segments[].from/to` = indeksy w `geometry.coordinates` (do kolorowania odcinków).
- Gdy ECO == FASTEST (identyczne krawędzie) → zwracamy obie, `comparison` z zerami i flagą `"same_route": true` (Frontend pokazuje „Fastest is already the healthiest").

**Błędy** (zawsze JSON, nigdy HTML):

| Kod | `error` | Kiedy |
|---|---|---|
| 400 | `validation` | zły JSON / brak pól / > 5 punktów |
| 422 | `point_outside_area` | punkt > 300 m od grafu lub poza Krakowem (`detail.index` = który punkt) |
| 404 | `no_route` | brak połączenia w grafie |
| 500 | `internal` | tylko błąd programisty (logujemy traceback) |

**`GET /api/scenarios`** → `[{"id":"live","label":"Live now"},{"id":"heatwave_2025-07-03","label":"Heatwave · 3 Jul 2025","default_at":"2025-07-03T14:00:00+02:00"},{"id":"smog_2025-01-20","label":"Smog · 20 Jan 2025","default_at":"2025-01-20T17:00:00+01:00"}]`

**`GET /api/conditions?scenario=…&at=…`** → `EnvironmentalContext.summary()` + `sun`.

**`GET /api/health`** → `{"ok": true, "mocks": false, "modules": {"graph": "real", "env": "real", "shade": "mock"}, "edges": 412345, "live_data_age_s": 812}`

**(stretch) `GET /api/layers/shade?bbox=w,s,e,n&at=…`** → GeoJSON FeatureCollection krawędzi w bbox (max 5000) z `shade`, `discomfort`.

---

## 5. Implementacja — kod

### 5.1 `requirements.txt` (całość projektu)

```text
flask>=3.0
waitress>=3.0          # serwer na demo (czysty Python, działa też na Windows)
pydantic>=2.7
httpx>=0.27
cachetools>=5.3
numpy>=1.26
scipy>=1.13
pandas>=2.2
pyarrow>=16
geopandas>=1.0
shapely>=2.0
pyproj>=3.6
rasterio>=1.3
osmnx>=2.0
osmium>=4.0            # PBF z Geofabrik (plan B dla Overpass — zweryfikowany)
lxml>=5.0              # parsowanie CityGML LoD1
pvlib>=0.11
pythermalcomfort>=2.10
scikit-fuzzy>=0.5
packaging              # skfuzzy jej wymaga, a nie deklaruje (sprawdzone)
pytest>=8
```

### 5.2 Fabryka aplikacji (`app/__init__.py`)

```python
import logging, os
from flask import Flask
from .engine import Engine

def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config.update(
        DATA_DIR=os.getenv("DATA_DIR", "data/processed"),
        SCENARIO_DIR=os.getenv("SCENARIO_DIR", "scenarios"),
        USE_MOCKS=os.getenv("USE_MOCKS", "0") == "1",
        MOCK_MODULES=set(filter(None, os.getenv("MOCK_MODULES", "").split(","))),  # np. "shade,env"
    )
    if overrides:
        app.config.update(overrides)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    app.extensions["engine"] = Engine.create(app.config)   # ładowanie RAZ, przy starcie

    from .api import bp
    app.register_blueprint(bp, url_prefix="/api")

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    return app
```

`MOCK_MODULES=shade` pozwala uruchomić prawdziwy graf i środowisko z atrapą cienia — **integracja moduł po module**.

### 5.3 Walidacja (`app/schemas.py`)

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

class Point(BaseModel):
    lat: float = Field(ge=49.95, le=50.15)
    lon: float = Field(ge=19.75, le=20.25)

class RouteRequest(BaseModel):
    points: list[Point] = Field(min_length=2, max_length=5)
    scenario: str = "live"
    depart_at: datetime | None = None
    profile: Literal["standard", "asthma", "senior", "athlete"] = "standard"
```

### 5.4 Blueprint (`app/api.py`)

```python
import time, logging
from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError
from .schemas import RouteRequest
from .contracts import PointOutsideArea, NoRoute

bp = Blueprint("api", __name__)
log = logging.getLogger(__name__)

def engine():
    return current_app.extensions["engine"]

@bp.post("/route")
def route():
    try:
        req = RouteRequest.model_validate(request.get_json(force=True, silent=False))
    except ValidationError as e:
        return jsonify(error="validation", detail=e.errors(include_url=False)), 400
    except Exception:
        return jsonify(error="validation", detail="invalid JSON"), 400
    try:
        return jsonify(engine().route(req))
    except PointOutsideArea as e:
        return jsonify(error="point_outside_area", detail={"index": getattr(e, "index", None)}), 422
    except NoRoute:
        return jsonify(error="no_route"), 404
    except Exception:
        log.exception("route failed")
        return jsonify(error="internal"), 500

@bp.get("/scenarios")
def scenarios():
    return jsonify(engine().env.scenarios())

@bp.get("/conditions")
def conditions():
    from datetime import datetime
    at = request.args.get("at")
    ctx = engine().env.get(request.args.get("scenario", "live"), datetime.fromisoformat(at) if at else None)
    sun = engine().shade.sun(ctx.timestamp if not at else datetime.fromisoformat(at))
    return jsonify({**ctx.summary(), "sun": sun.__dict__})

@bp.get("/health")
def health():
    return jsonify(engine().health())
```

### 5.5 Silnik integracji (`app/engine.py`)

```python
from __future__ import annotations
import threading, time
from dataclasses import dataclass
import numpy as np
from cachetools import LRUCache

PROFILE = {   # prędkość [km/h], wentylacja minutowa [m³/h], waga ECO
    "standard": dict(speed=15, ve=1.9, alpha=3.0),
    "asthma":   dict(speed=14, ve=1.9, alpha=5.0),
    "senior":   dict(speed=12, ve=1.6, alpha=5.0),
    "athlete":  dict(speed=22, ve=3.2, alpha=2.0),
}
REASONS = {-1: "ok", 0: "heat", 1: "air", 2: "uv"}

@dataclass
class EdgeCosts:
    t: np.ndarray            # czas przejazdu [s]
    shade: np.ndarray        # 0..1
    exp: "EdgeExposure"

class Engine:
    def __init__(self, graph, env, shade, modules: dict):
        self.graph, self.env, self.shade, self.modules = graph, env, shade, modules
        self._cache = LRUCache(maxsize=32)
        self._lock = threading.Lock()

    @classmethod
    def create(cls, cfg) -> "Engine":
        from . import mocks
        mock_all, mock_some = cfg["USE_MOCKS"], cfg["MOCK_MODULES"]
        use_mock = lambda name: mock_all or name in mock_some
        modules = {}
        if use_mock("graph"):
            graph = mocks.MockGraph(); modules["graph"] = "mock"
        else:
            from .graph.routing import RoutingGraph
            graph = RoutingGraph.load(cfg["DATA_DIR"]); modules["graph"] = "real"
        if use_mock("shade"):
            shade = mocks.MockShade(graph.n_edges); modules["shade"] = "mock"
        else:
            from .shade.model import ShadeModel
            shade = ShadeModel.load(cfg["DATA_DIR"], n_edges=graph.n_edges); modules["shade"] = "real"
        if use_mock("env"):
            env = mocks.MockEnv(); modules["env"] = "mock"
        else:
            from .env.service import EnvironmentService
            env = EnvironmentService(cfg["SCENARIO_DIR"], cfg["DATA_DIR"]); modules["env"] = "real"
        eng = cls(graph, env, shade, modules)
        eng.warmup()
        return eng

    # ---------- koszty krawędzi (cache: ta sama godzina/scenariusz/profil = 0 ms) ----------
    def edge_costs(self, ctx, at, profile) -> EdgeCosts:
        key = (ctx.source, ctx.timestamp.isoformat(), _bucket(at), profile)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit
        p = PROFILE[profile]
        shade = self.shade.edge_shade(at)
        if self.modules["env"] == "mock":
            from .mocks import mock_exposure as compute
        else:
            from .env.exposure import compute_edge_exposure as compute
        exp = compute(ctx, shade, self.graph, self.shade.edge_tree_frac, profile)
        t = self.graph.edge_length_m / (p["speed"] / 3.6)
        costs = EdgeCosts(t=t.astype(np.float64), shade=shade, exp=exp)
        with self._lock:
            self._cache[key] = costs
        return costs

    # ---------- główny przepływ ----------
    def route(self, req) -> dict:
        T = {}; t0 = time.perf_counter()
        ctx = self.env.get(req.scenario, req.depart_at)
        at = req.depart_at or ctx.timestamp
        T["env"] = _ms(t0)

        t1 = time.perf_counter()
        c = self.edge_costs(ctx, at, req.profile)
        T["exposure"] = _ms(t1)

        pts = [(p.lat, p.lon) for p in req.points]
        alpha = PROFILE[req.profile]["alpha"]
        t2 = time.perf_counter()
        fastest = self.graph.route(pts, c.t)
        eco = self.graph.route(pts, c.t * (1.0 + alpha * c.exp.discomfort))
        T["routing"] = _ms(t2)

        ve = PROFILE[req.profile]["ve"]
        routes = [self._describe("fastest", "Fastest", "#6b7280", fastest, c, ve, None),
                  self._describe("eco", "Healthier", "#16a34a", eco, c, ve, fastest)]
        same = np.array_equal(fastest.eids, eco.eids)
        T["total"] = _ms(t0)
        sun = self.shade.sun(at)
        return {
            "routes": routes,
            "comparison": _compare(routes[0]["metrics"], routes[1]["metrics"], same),
            "conditions": ctx.summary(),
            "sun": {"azimuth_deg": sun.azimuth_deg, "elevation_deg": sun.elevation_deg},
            "timing_ms": T,
        }

    def _describe(self, rid, label, color, r, c, ve, ref):
        e = r.eids; t = c.t[e]; tt = max(t.sum(), 1e-9)
        m = {
            "distance_m": round(float(self.graph.edge_length_m[e].sum())),
            "time_min": round(float(tt / 60), 1),
            "avg_discomfort": round(float((t * c.exp.discomfort[e]).sum() / tt * 10), 1),
            "shade_pct": round(float((t * c.shade[e]).sum() / tt * 100), 1),
            "pm25_dose_ug": round(float((c.exp.pm25[e] * ve * t / 3600).sum()), 2),
            "heat_stress_min": round(float(t[c.exp.utci_c[e] > 32].sum() / 60), 1),
        }
        coords = self.graph.geometry(e)
        return {"id": rid, "label": label, "color": color,
                "geometry": {"type": "LineString", "coordinates": coords},
                "metrics": m,
                "segments": self._segments(e, c),
                "avoids": self._avoids(ref, r, c) if ref is not None else []}

    def _segments(self, e, c):
        """Sklej kolejne krawędzie o tym samym powodzie; indeksy w geometrii."""
        out, start, idx = [], 0, 0
        reasons = c.exp.reason[e]; disc = c.exp.discomfort[e]
        lens = self.graph.coord_counts(e)          # liczba punktów geometrii per krawędź (Rola 1)
        cur = reasons[0]; acc = [disc[0]]
        for i in range(1, len(e) + 1):
            if i == len(e) or reasons[i] != cur:
                end = int(lens[:i].sum()) - (i - 1)    # łączenia krawędzi nie dublują punktów
                out.append({"from": start, "to": max(end - 1, start), "discomfort": round(float(np.mean(acc)), 2),
                            "reason": REASONS[int(cur)]})
                if i < len(e):
                    start, cur, acc = max(end - 1, 0), reasons[i], [disc[i]]
            else:
                acc.append(disc[i])
        return out

    def _avoids(self, ref, r, c, top=3):
        """Ulice z FASTEST o wysokim dyskomforcie, których ECO unika."""
        avoided = np.setdiff1d(ref.eids, r.eids)
        if avoided.size == 0:
            return []
        bad = avoided[c.exp.discomfort[avoided] > 0.5]
        names = self.graph.edge_name[bad]
        score = {}
        for eid, n in zip(bad, names):
            if n:
                score.setdefault(n, [0.0, []])
                score[n][0] += self.graph.edge_length_m[eid]
                score[n][1].append(REASONS[int(c.exp.reason[eid])])
        best = sorted(score.items(), key=lambda kv: -kv[1][0])[:top]
        return [f"{n} ({max(set(rs), key=rs.count)})" for n, (_, rs) in best]

    def health(self):
        return {"ok": True, "modules": self.modules, "edges": int(self.graph.n_edges)}

    def warmup(self):
        from .schemas import RouteRequest
        try:
            self.route(RouteRequest(points=[{"lat": 50.0614, "lon": 19.9366}, {"lat": 50.0540, "lon": 19.9350}]))
        except Exception:
            pass

def _bucket(at):                      # 30-minutowe koszyki czasu dla cache
    return at.replace(minute=(at.minute // 30) * 30, second=0, microsecond=0).isoformat()

def _ms(t):
    return round((time.perf_counter() - t) * 1000, 1)

def _compare(f, e, same):
    pct = lambda a, b: round((b - a) / a * 100, 1) if a else 0.0
    return {"same_route": bool(same),
            "time_delta_min": round(e["time_min"] - f["time_min"], 1),
            "time_delta_pct": pct(f["time_min"], e["time_min"]),
            "pm25_dose_delta_pct": pct(f["pm25_dose_ug"], e["pm25_dose_ug"]),
            "shade_delta_pp": round(e["shade_pct"] - f["shade_pct"], 1),
            "heat_stress_delta_min": round(e["heat_stress_min"] - f["heat_stress_min"], 1)}
```

> `graph.coord_counts(eids)` — dopisz do kontraktu Roli 1 (liczba punktów geometrii każdej krawędzi; `offs[e+1]-offs[e]`). Jeśli segmenty sprawią kłopot — zwracaj jeden segment na krawędź (prościej, Frontend i tak to narysuje).

### 5.6 Atrapy (`app/mocks.py`) — commit w H1–H2

```python
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from .contracts import EnvironmentalContext, EdgeExposure, Route, SunPosition, PointOutsideArea

TZ = ZoneInfo("Europe/Warsaw")

class MockGraph:
    """Graf-zabawka: każda 'krawędź' to odcinek prostej A→B; ECO dostaje objazd."""
    n_edges = 200
    def __init__(self):
        self.edge_length_m = np.full(self.n_edges, 25.0)
        self.edge_mid_lonlat = np.zeros((self.n_edges, 2))
        self.edge_highway = np.array(["residential"] * self.n_edges, dtype=object)
        self.edge_name = np.array(["ul. Testowa"] * self.n_edges, dtype=object)
    def snap(self, lat, lon):
        if not (49.95 <= lat <= 50.15 and 19.75 <= lon <= 20.25):
            raise PointOutsideArea()
        return 0
    def route(self, points, edge_cost):
        detour = not np.allclose(edge_cost, edge_cost[0])   # FASTEST: koszty równe; ECO: zróżnicowane przez D_e
        self._last = (points, detour)
        n = 100 if not detour else 120
        return Route(eids=np.arange(n), node_path=np.arange(n + 1))
    def geometry(self, eids):
        (a, b), detour = self._last[0][:2], self._last[1]
        k = np.linspace(0, 1, len(eids) + 1)
        lat = a[0] + (b[0] - a[0]) * k + (0.004 * np.sin(np.pi * k) if detour else 0)
        lon = a[1] + (b[1] - a[1]) * k
        return np.column_stack([lon, lat]).round(6).tolist()
    def coord_counts(self, eids):
        return np.full(len(eids), 2)

class MockShade:
    def __init__(self, n_edges):
        self.edge_tree_frac = np.linspace(0, 0.6, n_edges)
    def sun(self, at):
        return SunPosition(azimuth_deg=215.0, elevation_deg=59.0)
    def edge_shade(self, at):
        return np.linspace(0.1, 0.7, len(self.edge_tree_frac)).astype(np.float32)

class MockEnv:
    def get(self, scenario, at):
        return EnvironmentalContext(
            timestamp=at or datetime(2025, 7, 3, 14, tzinfo=TZ), source="mock",
            temperature_c=34.5, humidity_pct=20, wind_ms=4.8, shortwave_wm2=862, dni_wm2=853,
            uv_index=8.1, pm25=12.0, pm10=21.0, no2=18.0)
    def scenarios(self):
        return [{"id": "live", "label": "Live now"},
                {"id": "heatwave_2025-07-03", "label": "Heatwave · 3 Jul 2025", "default_at": "2025-07-03T14:00:00+02:00"},
                {"id": "smog_2025-01-20", "label": "Smog · 20 Jan 2025", "default_at": "2025-01-20T17:00:00+01:00"}]

def mock_exposure(ctx, shade, graph, tree_frac, profile):
    n = graph.n_edges
    disc = np.clip(0.8 - shade, 0, 1)
    return EdgeExposure(utci_c=np.full(n, 34.0) - 6 * shade, air_index=np.full(n, 1.5),
                        pm25=np.full(n, ctx.pm25), uv_eff=ctx.uv_index * (1 - 0.6 * shade),
                        discomfort=disc, reason=np.where(disc > 0.3, 0, -1).astype(np.int8))
```

`EnvironmentalContext.summary()` w mocku: dopisz do dataclassy domyślną implementację `{k: v for k, v in asdict(self).items() if k != "stations"} | {"timestamp": self.timestamp.isoformat()}` — Rola 2 może ją nadpisać.

---

## 6. Plan godzinowy

| H | Zadanie | Wynik / sprawdzian |
|---|---|---|
| 0–1 | Spotkanie kontraktowe (ten plik, sekcja 4) — 15 min; repo, gałęzie, `requirements.txt`, `make setup` u wszystkich | każdy ma działające `.venv` |
| 1–2 | `contracts.py`, `mocks.py`, `create_app`, `api.py`, `engine.py`; `USE_MOCKS=1 make dev` | `curl POST /api/route` zwraca 2 trasy z mocków; Frontend dostaje URL |
| 2–4 | `test_contracts.py` (każdy moduł spełnia Protocol, długości `E`), `test_api.py`; `Makefile`; README | `pytest` zielony na mockach |
| 4–6 | Integracja **Roli 1** (prawdziwy graf, `MOCK_MODULES=env,shade`) | trasa na prawdziwych ulicach Krakowa |
| 6–8 | Integracja **Roli 2** (środowisko, `MOCK_MODULES=shade`) | scenariusze i live w `/api/conditions` |
| **8–10** | **M1:** integracja **Roli 3** (cień); profilowanie czasu (`timing_ms`) | FASTEST ≠ ECO na Heatwave; p95 < 1 s |
| 10–14 | Segmenty, „avoids", porównanie; `/api/layers/shade` (stretch); strojenie `alpha` z Rolą 2 | Frontend pokazuje wyjaśnienia |
| 14–17 | Sen zmianowy (uzgodniony z zespołem) | |
| 17–20 | Benchmark 50 tras, testy brzegowe (punkt w Wiśle, punkty identyczne, 5 punktów), logowanie | tabela czasów na slajd |
| **20** | **Feature freeze** | |
| 20–23 | Stabilność na laptopie demo, `make demo`, pomoc przy wideo i slajdzie „Architecture" | |

---

## 7. Strojenie ECO (z Rolą 2)

- `cost_eco = t_e · (1 + α · D_e)`, `D_e ∈ [0,1]`. `α = 3` oznacza: odcinek o maksymalnym dyskomforcie „kosztuje" 4× dłużej.
- **Cel demo:** ECO dłuższa o 5–25% czasu i wyraźnie lepsza (≥ 20%) w dawce/cieniu. Jeśli ECO == FASTEST zbyt często → zwiększ `α`; jeśli objazdy absurdalne (> +50%) → zmniejsz.
- Skrypt `scripts/tune_alpha.py`: 30 losowych par punktów × α ∈ {1, 2, 3, 5, 8} → tabela Δczas vs Δdyskomfort → wybór.
- (stretch) trzecia trasa **Balanced** z `α/3` — tylko jeśli FASTEST i ECO stabilne.

---

## 8. Odporność (to daje „100%")

| Sytuacja | Zachowanie |
|---|---|
| Open-Meteo / GIOŚ nie odpowiada | Rola 2 zwraca `source="fallback"` z ostatniego `last_live.json` lub domyślnego scenariusza; UI pokazuje wiek danych |
| Artefakt cienia nie gotowy | `MOCK_MODULES=shade` — ECO działa na samej ekspozycji smog/UV |
| Graf się nie zbudował | graf z dysku zespołu (zbudowany w H2–H4 przez Rolę 1 i skopiowany) |
| Brak internetu na sali | scenariusze są w gicie; tylko kafle mapy wymagają sieci → wideo jako backup |
| Wyjątek w module | 500 z `error: internal` + log; UI pokazuje komunikat, nie biały ekran |
| Wolne zapytanie | cache kosztów (`_bucket` 30 min); Rola 1 ma tryb korytarza |

---

## 9. Testy

```python
# tests/test_api.py
import pytest
from app import create_app

@pytest.fixture
def client():
    return create_app({"USE_MOCKS": True, "MOCK_MODULES": set()}).test_client()

def test_route_ok(client):
    r = client.post("/api/route", json={"points": [{"lat": 50.06, "lon": 19.93}, {"lat": 50.05, "lon": 19.94}]})
    assert r.status_code == 200
    d = r.get_json()
    assert [x["id"] for x in d["routes"]] == ["fastest", "eco"]
    for x in d["routes"]:
        assert x["geometry"]["type"] == "LineString" and len(x["geometry"]["coordinates"]) >= 2
        assert set(x["metrics"]) >= {"distance_m", "time_min", "avg_discomfort", "shade_pct", "pm25_dose_ug", "heat_stress_min"}
    assert "comparison" in d and "timing_ms" in d

def test_validation(client):
    assert client.post("/api/route", json={"points": []}).status_code == 400

def test_outside(client):
    r = client.post("/api/route", json={"points": [{"lat": 52.2, "lon": 21.0}, {"lat": 50.05, "lon": 19.94}]})
    assert r.status_code == 400   # poza bbox łapie już walidacja pydantic
```

```python
# tests/test_contracts.py — uruchamiany na PRAWDZIWYCH modułach, gdy artefakty są
import numpy as np, pytest, os
from datetime import datetime
from zoneinfo import ZoneInfo
pytestmark = pytest.mark.skipif(not os.path.exists("data/processed/graph.npz"), reason="brak artefaktów")

def test_lengths_match():
    from app.graph.routing import RoutingGraph
    from app.shade.model import ShadeModel
    g = RoutingGraph.load("data/processed")
    s = ShadeModel.load("data/processed", n_edges=g.n_edges)
    sh = s.edge_shade(datetime(2025, 7, 3, 14, tzinfo=ZoneInfo("Europe/Warsaw")))
    assert sh.shape == (g.n_edges,) and 0 <= sh.min() and sh.max() <= 1
    assert s.edge_tree_frac.shape == (g.n_edges,)
```

---

## 10. Uruchomienie na demo

```makefile
dev:   ; FLASK_APP=app:create_app flask run --debug --port 8000
mock:  ; USE_MOCKS=1 FLASK_APP=app:create_app flask run --debug --port 8000
demo:  ; waitress-serve --host 127.0.0.1 --port 8000 --threads 8 --call app:create_app
test:  ; pytest -q
```

- **Jeden proces** (graf i cień w RAM ~1–2 GB) — nie używaj kilku workerów (każdy ładowałby dane osobno). `waitress` z wątkami wystarczy.
- Po starcie w logu: czasy ładowania modułów + `warmup ok`; pierwsze zapytanie ma być tak samo szybkie jak kolejne.

---

## 11. Czego NIE robić

- Nie zmieniaj kontraktu bez ogłoszenia całemu zespołowi (Discord/czat) i bez podbicia testów.
- Nie dodawaj bazy danych, kolejek, Dockera „na wszelki wypadek" — wszystko w RAM, pliki na dysku.
- Nie optymalizuj przed M1 — najpierw działa end-to-end, potem szybko.
- Nie pisz algorytmów za inne role — jeśli moduł się spóźnia, zostaje mock, a Ty pomagasz w debugowaniu.
