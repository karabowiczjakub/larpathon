# Rola 1 — Graph + Routing (OSMnx, graf, Dijkstra/A*, FASTEST i ECO)

> **Twoja misja:** graf rowerowy Krakowa jako artefakt (`graph.npz`, `edges.parquet`, `edge_coords.npz`) + klasa `RoutingGraph`, która dla listy punktów i **dowolnego wektora kosztów krawędzi** zwraca trasę w < 100 ms. FASTEST i ECO to ten sam algorytm z innym wektorem kosztów (Backend go składa) — Ty dbasz, żeby był szybki, poprawny i zawsze coś zwracał.
>
> Kontrakt `RoutingGraphP` i format artefaktów: `04_backend_integration.md`, sekcja 4. **Jesteś właścicielem numeracji `eid` — wszyscy indeksują nią swoje tablice.**

---

## 1. Definition of Done

- [ ] Artefakty w `data/processed/` (sekcja 4.2 kontraktu), graf przycięty do Krakowa, **zamrożony w H4** i wrzucony na dysk zespołu.
- [ ] `RoutingGraph.route(points, cost)` dla 2–5 punktów: **p95 < 150 ms** na laptopie demo.
- [ ] Snap punktu do grafu ≤ 300 m, inaczej `PointOutsideArea` (z indeksem punktu).
- [ ] Każda trasa ciągła (test), geometria w kierunku jazdy, respektuje jednokierunkowe **z kontraruchem rowerowym**.
- [ ] Testy `tests/test_graph.py` zielone.

---

## 2. Fakty ZMIERZONE przed hackathonem (3.10.2026) — na nich opieramy plan

| Pomiar | Wynik | Wniosek |
|---|---|---|
| `ox.graph_from_place("Kraków", network_type="bike")` przez Overpass | **2 próby, obie timeout po ~330 s**; osobno 504 „server too busy" | Overpass to realne ryzyko (setki zespołów na hackathonie). **Nie opieramy się na nim.** |
| Geofabrik `malopolskie-latest.osm.pbf` | **193 MB, pobranie 150 s** | Źródło podstawowe |
| PBF → filtr pyosmium → `ox.graph_from_xml` | **~5 min** (26 s filtr dróg, 99 s węzły, 167 s budowa grafu) | Działa bez Overpass |
| Graf (bbox z zapasem, bez filtra rowerowego) | 231 636 węzłów, 585 639 krawędzi | Za duży i za „pieszy" |
| Mix `highway` | **footway 235 k (40%)**, service 171 k, residential 76 k, path 32 k, tertiary 21 k, **steps 12 k**, track 11 k | Trzeba odfiltrować chodniki bez `bicycle=yes`, schody, parkingi |
| **scipy `dijkstra`, cały graf, 1 źródło** | **48 ms** | Wystarczy bez żadnych sztuczek |
| scipy, 5 źródeł naraz | 226 ms | Punkty pośrednie OK |
| scipy, 1 źródło z `limit=8 km` | 15 ms | Optymalizacja w zapasie |
| networkx A* (heurystyka euklidesowa) | 504 ms | **10× wolniej** niż scipy |
| networkx Dijkstra | 1077 ms | 22× wolniej |

### 2.1 Pipeline z tego pliku — uruchomiony end-to-end (3.10.2026)

Kod z sekcji 4 i 5 został złożony 1:1 i uruchomiony na `malopolskie-latest.osm.pbf`:

| Etap | Wynik |
|---|---|
| Filtr rowerowy (krok 1) | 99 582 dróg, 450 012 węzłów; 129 s łącznie z zapisem węzłów |
| Graf po przycięciu do granicy + `largest_component(strongly=True)` | **76 152 węzłów, 175 621 krawędzi** (3,4× mniej niż bez filtra) |
| Po deduplikacji (u,v) → artefakty | **E = 174 115**; cały `graph_build.py`: **263 s** |
| `RoutingGraph.load` | 0,2 s |
| **Trasa A→B + geometria, 30 losowych par** | **p50 17 ms, p95 20 ms** |
| Trasa przez 5 punktów | 58 ms |
| `tests/test_graph.py` (sekcja 7) | **5/5 passed** |
| Mix `highway` po filtrze | service 67 k, residential 41 k, path 20 k, footway 19 k (tylko z `bicycle=yes/designated`), tertiary 9 k |

Wniosek: FASTEST + ECO na żądanie to ~40 ms routingu — zapas na wszystko inne. `service` to wciąż 39% krawędzi (dojazdy, podwórka); jeśli trasy będą „kluczyć" po podwórkach, dodaj do `keep()` odrzucanie `service=driveway` albo karę kosztu dla `service` w Backendzie.

**Decyzja: Dijkstra ze `scipy.sparse.csgraph` (C), nie A* w Pythonie/networkx.** A* ma przewagę asymptotyczną, ale implementacja w czystym Pythonie przegrywa z Dijkstrą w C o rząd wielkości. Na slajdzie: „zmierzyliśmy: A* (networkx) 504 ms vs Dijkstra (scipy CSR) 48 ms".

---

## 3. Plan godzinowy

| H | Zadanie | Sprawdzian |
|---|---|---|
| 0–0:15 | **Start pobierania PBF** (150 s) — pierwsza rzecz na hackathonie | plik na dysku |
| 0–1 | Kontrakty z Backendem; `make setup` | |
| 1–2 | `pipeline/graph_build.py` krok 1–2 (filtr rowerowy, granica miasta) | `krk_bike.osm` |
| 2–3 | krok 3–4 (graf, CSR, artefakty) | `graph.npz` + `edges.parquet`; **kopiujesz na dysk zespołu** (Rola 3 i 2 czekają) |
| 3–4 | `app/graph/routing.py` (`RoutingGraph`) + testy | Backend podmienia `MockGraph`; trasa na prawdziwych ulicach |
| **4** | **Zamrożenie grafu** (zmiana = wszyscy przeliczają artefakty!) | ogłoszenie na czacie |
| 4–6 | Weryfikacja jakości: 10 znanych tras (sekcja 7), kontraruch, mosty, Planty, bulwary | lista poprawek filtra (tylko jeśli krytyczne) |
| 6–8 | Wydajność: benchmark 50 tras, p95; ew. `limit` | tabela czasów |
| **8–10** | **M1** z Backendem | FASTEST i ECO na żywo |
| 10–14 | **Stretch 1:** trasa BALANCED / sweep λ (sekcja 8) | 3 trasy |
| 14–17 | Sen zmianowy | |
| 17–20 | **Stretch 2 (tylko jeśli wszystko stabilne):** front Pareto / NSGA-II | wykres frontu |
| **20** | Feature freeze | |

---

## 4. `pipeline/graph_build.py` — budowa grafu z PBF

### 4.1 Krok 1: filtr rowerowy + kontraruch (pyosmium)

Reguły (prawo polskie: rower po chodniku tylko wyjątkowo → chodnik tylko z `bicycle=yes/designated`):

| Tagi | Decyzja |
|---|---|
| `highway` ∈ motorway, motorway_link, construction, proposed, abandoned, raceway, bus_guideway, platform, elevator, escalator, corridor, **steps** | ❌ |
| `motorroad=yes` (drogi ekspresowe) | ❌ |
| `highway=footway` / `pedestrian` bez `bicycle` ∈ {yes, designated, permissive} | ❌ |
| `highway=service` z `service` ∈ {parking_aisle, drive-through} | ❌ |
| `access` ∈ {private, no} bez `bicycle` ∈ {yes, designated} | ❌ |
| `bicycle` ∈ {no, dismount} | ❌ |
| `highway=trunk` bez `bicycle=no` | ✅ (ale ECO i tak go unika) |
| `oneway:bicycle=no` lub `cycleway=opposite*` | ✅ i **usuwamy `oneway`** (kontraruch) |
| reszta z kluczem `highway` | ✅ |

```python
# pipeline/graph_build.py
import time, numpy as np, osmium
PBF = "data/raw/malopolskie-latest.osm.pbf"
BBOX = (19.79, 49.96, 20.22, 50.13)          # lon_min, lat_min, lon_max, lat_max (Kraków + zapas)

DROP_HW = {"motorway", "motorway_link", "construction", "proposed", "abandoned", "raceway", "bus_guideway",
           "platform", "elevator", "escalator", "corridor", "steps"}
BIKE_OK = {"yes", "designated", "permissive"}

def keep(t) -> bool:
    hw = t.get("highway")
    if hw is None or hw in DROP_HW or t.get("motorroad") == "yes":
        return False
    bike = t.get("bicycle")
    if bike in ("no", "dismount"):
        return False
    if hw in ("footway", "pedestrian") and bike not in BIKE_OK:
        return False
    if hw == "service" and t.get("service") in ("parking_aisle", "drive-through"):
        return False
    if t.get("access") in ("private", "no") and bike not in BIKE_OK:
        return False
    return True

def contraflow(t) -> dict:
    tags = dict(t)
    if tags.get("oneway:bicycle") == "no" or str(tags.get("cycleway", "")).startswith("opposite"):
        tags.pop("oneway", None)
    return tags

def step1_filter(out="data/interim/krk_bike_ways.osm"):
    t0 = time.time(); need = set(); n = 0
    w = osmium.SimpleWriter(out, overwrite=True)
    fp = osmium.FileProcessor(PBF).with_filter(osmium.filter.KeyFilter("highway")).with_locations()
    for o in fp:
        if not o.is_way() or not keep(o.tags):
            continue
        if not any(n_.location.valid() and BBOX[0] <= n_.lon <= BBOX[2] and BBOX[1] <= n_.lat <= BBOX[3]
                   for n_ in o.nodes):
            continue
        w.add_way(o.replace(tags=contraflow(o.tags)))
        need.update(n_.ref for n_ in o.nodes); n += 1
    w.close()
    print(f"ways={n:,} nodes={len(need):,} {time.time()-t0:.0f}s")
    # węzły + drogi w jednym pliku (OSM XML: najpierw węzły)
    w = osmium.SimpleWriter("data/interim/krk_bike.osm", overwrite=True)
    for o in osmium.FileProcessor(PBF, osmium.osm.NODE):
        if o.id in need:
            w.add_node(o)
    for o in osmium.FileProcessor(out, osmium.osm.WAY):
        w.add_way(o)
    w.close()
```

> Zmierzone na wersji bez filtra rowerowego: 26 s + 99 s. Z filtrem będzie podobnie lub szybciej.
> **Sprawdzone:** `o.replace(tags=…)` + `add_way` działa, ale **tylko wewnątrz pętli** (poza nią: `RuntimeError: Illegal access to removed OSM object`). Reguła kontraruchu poprawia **935 ulic** w Krakowie.

### 4.2 Krok 2: granica Krakowa (3 poziomy zabezpieczeń)

```python
import geopandas as gpd, shapely

def kraków_boundary() -> shapely.Polygon:
    # A) z PBF: relacja boundary=administrative, admin_level=8, name=Kraków (bez internetu)
    try:
        wkb = osmium.geom.WKBFactory()
        fp = (osmium.FileProcessor(PBF).with_areas()
              .with_filter(osmium.filter.TagFilter(("boundary", "administrative"))))
        for o in fp:
            if o.is_area() and o.tags.get("admin_level") == "8" and o.tags.get("name") == "Kraków":
                return shapely.from_wkb(wkb.create_multipolygon(o))
    except Exception as e:
        print("boundary from PBF failed:", e)
    # B) Nominatim (inny serwer niż Overpass)
    try:
        import osmnx as ox
        return ox.geocode_to_gdf("Kraków, Poland").geometry.iloc[0]
    except Exception as e:
        print("boundary from Nominatim failed:", e)
    # C) prostokąt
    return shapely.box(19.79, 49.97, 20.22, 50.13)
```

**Sprawdzone:** wariant A znajduje granicę Krakowa w **17 s** (bounds 19.792, 49.968 – 20.217, 50.126), bez internetu. Sygnatury `truncate_graph_polygon(G, polygon, *, truncate_by_edge)` i `largest_component(G, *, strongly)` potwierdzone w OSMnx 2.1.1.

Zapisz granicę też jako `app/static/krakow_boundary.geojson` (uproszczoną `simplify(0.0005)`) — Frontend pokaże zasięg usługi.

### 4.3 Krok 3: graf (OSMnx z pliku, bez Overpass)

```python
import osmnx as ox

G = ox.graph_from_xml("data/interim/krk_bike.osm", bidirectional=False, simplify=True, retain_all=True)
G = ox.truncate.truncate_graph_polygon(G, kraków_boundary(), truncate_by_edge=True)
G = ox.truncate.largest_component(G, strongly=True)    # silnie spójna: z każdego węzła da się wrócić → mniej NoRoute
G = ox.project_graph(G, to_crs="EPSG:2180")
print(f"nodes={G.number_of_nodes():,} edges={G.number_of_edges():,}")
```

`strongly=True` jest ważne w grafie skierowanym — bez tego punkt na ślepej jednokierunkowej uliczce daje `NoRoute`.

### 4.4 Krok 4: CSR + artefakty (format = kontrakt)

```python
import numpy as np, scipy.sparse as sp
from pyproj import Transformer

nodes, edges = ox.graph_to_gdfs(G)
first = lambda x: x[0] if isinstance(x, list) else x
for col in ("highway", "name"):
    edges[col] = edges[col].apply(first) if col in edges else None

# KRYTYCZNE: scipy.sparse SUMUJE duplikaty (u,v). Multigraf ma krawędzie równoległe → zostaw najkrótszą.
edges = edges.sort_values("length")
edges = edges[~edges.index.droplevel("key").duplicated(keep="first")].reset_index()

node_id = {osm: i for i, osm in enumerate(nodes.index)}
edges["u_i"] = edges["u"].map(node_id).astype(np.int32)
edges["v_i"] = edges["v"].map(node_id).astype(np.int32)
edges["eid"] = np.arange(len(edges), dtype=np.int32)
N, E = len(nodes), len(edges)

base = sp.csr_matrix((np.arange(1, E + 1), (edges["u_i"], edges["v_i"])), shape=(N, N))
perm = (base.data - 1).astype(np.int32)          # slot CSR → eid

to_wgs = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
nlon, nlat = to_wgs.transform(nodes["x"].to_numpy(), nodes["y"].to_numpy())
mid = edges.geometry.interpolate(0.5, normalized=True)
mlon, mlat = to_wgs.transform(mid.x.to_numpy(), mid.y.to_numpy())

np.savez_compressed("data/processed/graph.npz",
    indptr=base.indptr, indices=base.indices, perm=perm,
    node_x=nodes["x"].to_numpy(), node_y=nodes["y"].to_numpy(), node_lon=nlon, node_lat=nlat,
    edge_u=edges["u_i"].to_numpy(), edge_v=edges["v_i"].to_numpy(),
    edge_length_m=edges["length"].to_numpy(np.float32),
    edge_mid_lon=np.float32(mlon), edge_mid_lat=np.float32(mlat))

# geometrie WGS84, ZAWSZE w kierunku u→v
geo = edges.set_geometry("geometry").to_crs("EPSG:4326").geometry
coords, ux, uy = [], nlon[edges["u_i"]], nlat[edges["u_i"]]
for g, x0, y0 in zip(geo, ux, uy):
    c = np.asarray(g.coords, dtype=np.float32)
    if np.hypot(*(c[0] - (x0, y0))) > np.hypot(*(c[-1] - (x0, y0))):
        c = c[::-1]                              # odwróć, jeśli zaczyna się przy v
    coords.append(c)
offs = np.cumsum([0] + [len(c) for c in coords])
np.savez_compressed("data/processed/edge_coords.npz", coords=np.vstack(coords), offs=offs)

edges[["eid", "u_i", "v_i", "length", "highway", "name", "geometry"]] \
    .rename(columns={"u_i": "u", "v_i": "v", "length": "length_m"}) \
    .to_parquet("data/processed/edges.parquet")
print(f"saved: N={N:,} E={E:,}")
```

---

## 5. `app/graph/routing.py` — `RoutingGraph`

```python
from __future__ import annotations
import numpy as np, pandas as pd, scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from pyproj import Transformer
from ..contracts import Route, PointOutsideArea, NoRoute

SNAP_MAX_M = 300.0
_to2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)

class RoutingGraph:
    @classmethod
    def load(cls, data_dir: str) -> "RoutingGraph":
        return cls(np.load(f"{data_dir}/graph.npz"), np.load(f"{data_dir}/edge_coords.npz"),
                   pd.read_parquet(f"{data_dir}/edges.parquet", columns=["eid", "highway", "name"]))

    def __init__(self, z, gc, meta):
        self.indptr, self.indices, self.perm = z["indptr"], z["indices"], z["perm"]
        self.N = len(self.indptr) - 1
        self.n_edges = len(z["edge_length_m"])
        self.edge_length_m = z["edge_length_m"].astype(np.float64)
        self.edge_u, self.edge_v = z["edge_u"], z["edge_v"]
        self.edge_mid_lonlat = np.column_stack([z["edge_mid_lon"], z["edge_mid_lat"]])
        self.edge_highway = meta["highway"].astype(object).to_numpy()
        self.edge_name = meta["name"].astype(object).where(meta["name"].notna(), None).to_numpy()
        self.coords, self.offs = gc["coords"], gc["offs"]
        self.kd = cKDTree(np.column_stack([z["node_x"], z["node_y"]]))
        assert len(self.perm) == self.n_edges, "CSR ma inną liczbę krawędzi niż artefakty — duplikaty (u,v)?"

    # --- snap ---
    def snap(self, lat: float, lon: float, index: int | None = None) -> int:
        x, y = _to2180.transform(lon, lat)
        d, i = self.kd.query((x, y))
        if d > SNAP_MAX_M:
            e = PointOutsideArea(f"point {index} is {d:.0f} m from the bike network"); e.index = index
            raise e
        return int(i)

    # --- macierz kosztów: tylko podmiana wektora data (struktura CSR stała) ---
    def _matrix(self, edge_cost: np.ndarray) -> sp.csr_matrix:
        w = np.maximum(edge_cost[self.perm], 1e-3)                 # wagi > 0 (zero = brak krawędzi)
        return sp.csr_matrix((w, self.indices, self.indptr), shape=(self.N, self.N))

    def _edge_id(self, a: int, b: int) -> int:
        lo, hi = self.indptr[a], self.indptr[a + 1]
        k = np.flatnonzero(self.indices[lo:hi] == b)[0]
        return int(self.perm[lo + k])

    # --- trasa przez punkty (A, via..., B) jednym wywołaniem Dijkstry ---
    def route(self, points: list[tuple[float, float]], edge_cost: np.ndarray) -> Route:
        nodes = [self.snap(lat, lon, i) for i, (lat, lon) in enumerate(points)]
        M = self._matrix(edge_cost)
        _, pred = dijkstra(M, directed=True, indices=nodes[:-1], return_predecessors=True)
        pred = np.atleast_2d(pred)
        path = [nodes[0]]
        for k in range(len(nodes) - 1):
            s, t = nodes[k], nodes[k + 1]
            if s == t:
                continue
            seg = [t]
            while seg[-1] != s:
                p = pred[k, seg[-1]]
                if p < 0:
                    raise NoRoute(f"no path between point {k} and {k+1}")
                seg.append(p)
            path += seg[::-1][1:]
        path = np.asarray(path)
        eids = np.array([self._edge_id(a, b) for a, b in zip(path[:-1], path[1:])], dtype=np.int64)
        return Route(eids=eids, node_path=path)

    # --- geometria do API ---
    def geometry(self, eids: np.ndarray) -> list[list[float]]:
        if len(eids) == 0:
            return []
        parts = [self.coords[self.offs[e]:self.offs[e + 1]] for e in eids]
        out = np.vstack([parts[0]] + [p[1:] for p in parts[1:]])      # bez dublowania węzłów
        return np.round(out.astype(np.float64), 6).tolist()

    def coord_counts(self, eids: np.ndarray) -> np.ndarray:
        return (self.offs[np.asarray(eids) + 1] - self.offs[np.asarray(eids)]).astype(np.int64)
```

**Wydajność:** jedno wywołanie `dijkstra` z `indices=[A, via…]` liczy wszystkie odcinki naraz (zmierzone: 226 ms dla 5 źródeł; dla A→B 48 ms). FASTEST + ECO = 2 wywołania ≈ 100 ms. Jeśli na laptopie demo będzie wolniej: `limit=` (maks. koszt) — zmierzone 15 ms przy limicie 8 km.

---

## 6. FASTEST i ECO — podział odpowiedzialności

| | Kto liczy wektor kosztów | Wzór |
|---|---|---|
| FASTEST | Backend | `t_e = length_e / v_profil` |
| ECO | Backend (z danych Roli 2 i 3) | `t_e · (1 + α · D_e)`, `D_e ∈ [0,1]` |

Ty nie wiesz nic o smogu — dostajesz tablicę `(E,)` i zwracasz najtańszą trasę. Dzięki temu **każdy nowy wariant trasy (BALANCED, „max cień") kosztuje 0 linii Twojego kodu**.

---

## 7. Testy i weryfikacja jakości

```python
# tests/test_graph.py
import numpy as np, pytest, os
pytestmark = pytest.mark.skipif(not os.path.exists("data/processed/graph.npz"), reason="brak grafu")
from app.graph.routing import RoutingGraph
from app.contracts import PointOutsideArea

@pytest.fixture(scope="module")
def g():
    return RoutingGraph.load("data/processed")

def test_continuity(g):
    r = g.route([(50.0614, 19.9366), (50.0540, 19.9350)], g.edge_length_m)
    assert (g.edge_v[r.eids[:-1]] == g.edge_u[r.eids[1:]]).all()            # kolejne krawędzie się stykają

def test_shortest_beats_any_cost(g):
    pts = [(50.0614, 19.9366), (50.0675, 19.9128)]
    f = g.route(pts, g.edge_length_m)
    e = g.route(pts, g.edge_length_m * np.random.default_rng(0).uniform(1, 3, g.n_edges))
    assert g.edge_length_m[f.eids].sum() <= g.edge_length_m[e.eids].sum() + 1e-6

def test_via_points(g):
    r = g.route([(50.0614, 19.9366), (50.0647, 19.9450), (50.0540, 19.9350)], g.edge_length_m)
    assert len(r.eids) > 0

def test_outside(g):
    with pytest.raises(PointOutsideArea):
        g.snap(50.20, 19.50)

def test_geometry_starts_at_start(g):
    r = g.route([(50.0614, 19.9366), (50.0540, 19.9350)], g.edge_length_m)
    c = np.array(g.geometry(r.eids))
    assert np.hypot(*(c[0] - (19.9366, 50.0614))) < 0.005                  # < ~400 m od klikniętego punktu
```

**Weryfikacja ręczna (H4–6) — 10 tras referencyjnych** porównaj z Google Maps (tryb rower) lub mapą rowerową: Rynek→AGH, Kazimierz→Nowa Huta (Plac Centralny), Dworzec Główny→Wawel, bulwary Wisły (Most Grunwaldzki→Most Dębnicki), Planty dookoła, Bronowice→Czyżyny, kładka Bernatka, Ruczaj→Rynek Podgórski, Krowodrza→Kampus UJ, Prądnik→Galeria Krakowska. Kryterium: długość ±25% i brak absurdów (schody, autostrada, przejazd przez budynek).

---

## 8. Stretch (dopiero po M1 i stabilnych testach)

### 8.1 BALANCED / sweep λ — 30 min pracy, duży efekt na UI

Backend woła `route()` dla `α ∈ {0, 0.5, 1, 2, 3, 5}`, zbiera unikalne trasy, odrzuca zdominowane (czas, ekspozycja) → 2–4 alternatywy + wykres Pareto. Zero zmian w `RoutingGraph`.

### 8.2 NSGA-II „Route Morphing" — tylko jeśli H17 i wszystko zielone

Genotyp = mnożniki kosztów dla komórek siatki 400 m (nie lista ulic), dekoder = Twoja `route()`. Przy 48 ms na Dijkstrę: populacja 20 × 10 generacji ≈ 10 s — **za wolno na pełnym grafie**; potrzebny korytarz (podgraf w elipsie wokół A–B, ~10× mniejszy). Uzasadnienie dla jury: suma ważona nie znajduje punktów na niewypukłej części frontu Pareto. **Jeśli nie zdążysz — to idzie na slajd „Next steps", nie do demo.**

---

## 9. Ryzyka i plan B

| Ryzyko | Plan B |
|---|---|
| Geofabrik wolny/niedostępny | mirror `https://download.openstreetmap.fr/extracts/europe/poland/malopolskie.osm.pbf`; ostatecznie Overpass w nocy (mniejszy ruch) |
| Overpass (jeśli ktoś chce go używać) | **nie używać w ścieżce krytycznej** — 2/2 timeouty w teście |
| `graph_from_xml` za wolny / brak RAM | zmniejsz BBOX do granic miasta przed budową; zamknij przeglądarkę; ostatecznie budowa na najmocniejszym laptopie zespołu |
| `NoRoute` przy jednokierunkowych | `largest_component(strongly=True)` + kontraruch; ostatecznie graf nieskierowany dla rowerów (uczciwie opisane) |
| Graf trzeba przebudować po H4 | tylko krytyczne błędy; ogłoś — Rola 3 przelicza cień (~10 min), Rola 2 nic (liczy online) |
| Trasy przez chodniki/parkingi | dopisz regułę w `keep()`, przebuduj przed H4 |

## 10. Czego NIE robić

- Nie pisz własnego A* w Pythonie „bo jest szybszy" — zmierzone: scipy Dijkstra 48 ms vs networkx A* 504 ms.
- Nie używaj networkx w ścieżce zapytania (tylko do budowy/analizy offline).
- Nie zmieniaj numeracji `eid` po H4.
- Nie zaczynaj NSGA-II przed M1.
