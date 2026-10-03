# Rola 3 — Shade + Buildings + Sun (GUGiK/OSM, wysokości budynków, słońce, cień)

> **Twoja misja:** dla każdej krawędzi grafu i każdej chwili — **jaka część odcinka jest w cieniu** (budynki + drzewa), plus udział koron drzew. To jest najbardziej „wow" element demo: zmiana godziny z 14:00 na 18:30 zmienia trasę.
>
> Kontrakt `ShadeModelP`, format `shade.npy`, numeracja `eid`: `04_backend_integration.md`, sekcja 4.

---

## 1. Definition of Done

- [ ] `data/processed/shade.npy` `uint8 (E, 16, 8)` + `shade_bins.json` + `edge_tree_frac.npy` `float32 (E,)` dla **grafu zamrożonego przez Rolę 1 (H4)**.
- [ ] `ShadeModel.edge_shade(at)` w < 10 ms, `ShadeModel.sun(at)` (pvlib).
- [ ] Walidacja wizualna: mapa cienia 14:00 vs 18:30 dla centrum (PNG na slajd).
- [ ] Liczby na slajd: % cienia na ulicach centrum o różnych godzinach.

---

## 2. Fakty ZMIERZONE przed hackathonem (3.10.2026)

| Pomiar | Wynik | Wniosek |
|---|---|---|
| **GUGiK LoD1 2024, powiat Kraków (1261)** | link bezpośredni (niżej), **28,8 MB, pobranie 41 s**, 91 257 budynków | Źródło podstawowe wysokości |
| Parsowanie CityGML (lxml, kod niżej) | **35 s**, `measuredHeight` u **100%** budynków, 0 błędnych geometrii, wysokości: mediana 7,1 m, max 62,5 m | Działa od ręki |
| Budynki w OSM (bbox Krakowa, z PBF) | 201 360, ale **tylko 20%** ma `height` lub `building:levels` | OSM tylko jako zapas |
| MSIP „zieleń wysoka" (drzewa), zapytanie bbox | 1 644 poligony w centrum w **10,6 s** | Źródło drzew |
| OSM drzewa (z PBF) | 148 142 pojedyncze `natural=tree`, 1 152 szpalery | Uzupełnienie (opcjonalne) |
| Raster wysokości 2 m, centrum 2,5×2,5 km | **0,8 s**; budynki 26% pikseli, drzewa 18% | |
| Ray-marching, 33 156 punktów na ulicach, **pełna tablica 128 pozycji słońca** | **8,1 s** → ~**245 s na 1 mln punktów** | Cały Kraków w kilka minut |
| Cień 3.07.2025, centrum | **14:00 (az 215°, el 59°): 34%** punktów w cieniu; **18:30 (az 283°, el 20°): 70%**; pod koronami 14% | Zmiana godziny realnie zmienia trasę → slajd |
| pvlib `get_solarposition` | działa (0.16.1) | |

**Wniosek: „dokładne poligony cieni" są niepotrzebne** — promień po rastrze wysokości daje to samo prościej i szybciej.

---

## 3. Plan godzinowy

| H | Zadanie | Sprawdzian |
|---|---|---|
| 0–0:15 | **Start pobierania LoD1** (41 s) | `1261.zip` na dysku |
| 0–1 | Kontrakty; `make setup` | |
| 1–2 | Parsowanie LoD1 → `buildings.parquet`; drzewa MSIP → `trees.parquet` | liczby jak w tabeli wyżej |
| 2–3 | Raster wysokości 2 m dla całego Krakowa → `heights_2m.tif` | podgląd PNG |
| 3–4 | `ShadeModel` (lookup + pvlib) na **tymczasowych punktach** (siatka co 50 m) — żeby nie czekać | `edge_shade` zwraca sensowne wartości |
| **4–6** | Graf od Roli 1 (H4) → punkty co 15 m na krawędziach → **pełna tablica `shade.npy`** | plik na dysku zespołu |
| 6–8 | `edge_tree_frac`, walidacja wizualna (PNG 14:00 vs 18:30), testy | Backend podmienia `MockShade` |
| **8–10** | **M1** | ECO wybiera cień na Heatwave |
| 10–14 | (stretch) warstwa cienia na mapę dla Frontendu (`/api/layers/shade`), OSM drzewa, korekta wysokości drzew | |
| 14–17 | Sen zmianowy | |
| 17–20 | Grafiki na slajd: mapa cienia, animacja godzin (GIF), liczby | |
| **20** | Feature freeze | |

---

## 4. Budynki — GUGiK LoD1 2024 (ZWERYFIKOWANE)

```bash
# Link uzyskany z usługi WMS GUGiK (GetFeatureInfo, warstwa Modele_3D_budynkow_LoD1_2024, TERYT 1261)
curl -L -o data/raw/lod1_1261.zip https://opendata.geoportal.gov.pl/InneDane/Budynki3D/LOD1/2024/12/1261.zip
unzip -q data/raw/lod1_1261.zip -d data/raw/lod1        # 546 MB plików .gml (arkusze 1:10000)
```

Jak zdobyć link do innego powiatu (gdyby trzeba było „i okolice"): `https://mapy.geoportal.gov.pl/wss/service/PZGIK/FOTO/WMS/ModeleBudynkow3D?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS=Modele_3D_budynkow_LoD1_2024&QUERY_LAYERS=Modele_3D_budynkow_LoD1_2024&CRS=EPSG:2180&BBOX=243000,566000,245000,568000&WIDTH=101&HEIGHT=101&I=50&J=50&INFO_FORMAT=text/plain&STYLES=` → pole `LOD1_2024_LINK` (sprawdzone). W WMS 1.3.0 dla EPSG:2180 kolejność BBOX to **northing, easting** (przykład = centrum Krakowa); przesuń okno nad inny powiat.

`edge_points()` zakłada, że wiersze `edges.parquet` są w kolejności `eid` (tak zapisuje Rola 1).

```python
# pipeline/shade_build.py — krok 1: LoD1 → footprinty + wysokości (PRZETESTOWANE: 35 s, 91 257 budynków)
import glob, numpy as np, shapely, geopandas as gpd
from lxml import etree

NS = {"bldg": "http://www.opengis.net/citygml/building/2.0", "gml": "http://www.opengis.net/gml"}
B = "{http://www.opengis.net/citygml/building/2.0}Building"

def parse_lod1(pattern="data/raw/lod1/*.gml") -> gpd.GeoDataFrame:
    rows = []
    for f in glob.glob(pattern):
        for _, el in etree.iterparse(f, tag=B):
            h = el.findtext("bldg:measuredHeight", namespaces=NS)
            base = None
            for pl in el.iterfind(".//gml:posList", NS):
                a = np.array(pl.text.split(), float).reshape(-1, 3)
                if np.ptp(a[:, 2]) < 1e-6 and (base is None or a[0, 2] < base[0, 2]):
                    base = a                       # pozioma ściana o najniższym z = podstawa budynku
            if base is not None:
                rows.append((float(h) if h else np.nan, shapely.Polygon(base[:, :2])))
            el.clear()
    return gpd.GeoDataFrame({"height": [r[0] for r in rows]}, geometry=[r[1] for r in rows], crs=2180)

bld = parse_lod1()
bld.to_parquet("data/interim/buildings.parquet")
```

Współrzędne w plikach są już w **EPSG:2180** (PUWG 1992) — tym samym co graf. Bez reprojekcji.

**Plan B (gdyby LoD1 był niedostępny):** OSM z PBF (`building=*`), wysokość = `height` → `building:levels × 3,2 + 1` → domyślna wg typu (`house` 7 m, `apartments` 15 m, `commercial`/`retail` 12 m, inne 9 m). Uwaga: tylko 20% ma tagi wysokości — opisać uczciwie.

---

## 5. Drzewa — MSIP Kraków (ZWERYFIKOWANE)

```python
# krok 2: zieleń wysoka z MSIP (ArcGIS REST, paginacja po 1000)
import httpx, geopandas as gpd, pandas as pd

URL = ("https://msip.um.krakow.pl/arcgis/rest/services/MONIT-AIR/"
       "WS_MA_Mapa_Zieleni_2015/MapServer/0/query")

def fetch_tall_green(bbox=(19.79, 49.96, 20.22, 50.13)) -> gpd.GeoDataFrame:
    parts, off = [], 0
    with httpx.Client(timeout=60) as c:
        while True:
            r = c.get(URL, params={
                "where": "class_name LIKE '200%'",               # 200 = Zieleń wysoka
                "geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope",
                "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
                "outFields": "class_name", "outSR": 2180, "f": "geojson",
                "resultOffset": off, "resultRecordCount": 1000})
            fs = r.json()["features"]
            if not fs:
                break
            parts.append(gpd.GeoDataFrame.from_features(fs, crs=2180)); off += 1000
    return pd.concat(parts, ignore_index=True)

trees = fetch_tall_green()
trees.to_parquet("data/interim/trees.parquet")
```

- Klasy w warstwie (sprawdzone): `200 Zieleń wysoka`, `300 Zieleń niska`, `400 Zieleń sportowa, ogródki działkowe`. Cały zbiór: 128 221 poligonów.
- Dane z 2015 r. — opisać na slajdzie. **Wysokość drzew: 12 m (założenie).**
- (opcjonalnie) OSM `natural=tree` (148 tys. punktów) → bufor 3 m jako korona, wysokość 10 m — uzupełnia drzewa przyuliczne.
- (stretch) Geoportal: modele 3D drzew (CityGML) lub nDSM = NMPT − NMT dają realne wysokości — tylko jeśli zostanie czas.

---

## 6. Raster wysokości 2 m

```python
# krok 3
import numpy as np, rasterio, rasterio.features as rf
from rasterio.transform import from_origin

RES = 2.0
def build_height_raster(bld, trees, bounds, out="data/processed/heights_2m.tif"):
    x0, y0, x1, y1 = bounds                         # EPSG:2180, np. z granicy Krakowa + 150 m bufora
    W, H = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
    tr = from_origin(x0, y1, RES, RES)
    bld = bld.sort_values("height")                 # wyższe nadpisują niższe
    hb = rf.rasterize(zip(bld.geometry, bld.height), out_shape=(H, W), transform=tr, fill=0, dtype="float32")
    ht = rf.rasterize(((g, 12.0) for g in trees.geometry), out_shape=(H, W), transform=tr, fill=0, dtype="float32")
    hmax = np.clip(np.maximum(hb, ht), 0, 255).astype(np.uint8)
    with rasterio.open(out, "w", driver="GTiff", width=W, height=H, count=1, dtype="uint8",
                       crs="EPSG:2180", transform=tr, compress="deflate") as dst:
        dst.write(hmax, 1)
    return hmax, tr
```

Rozmiar dla całego Krakowa (granica ~30 × 18 km): ~15 200 × 8 800 px uint8 ≈ **135 MB RAM** — OK. Rasteryzacja całości szacunkowo < 1 min (centrum: 0,8 s).

---

## 7. Cień — ray-marching (PRZETESTOWANE)

Punkt jest w cieniu, jeśli w kierunku słońca jakaś przeszkoda jest wyższa niż promień:

```
przeszkoda wysokości h w odległości d zacienia punkt  ⇔  h > 1,5 m + d · tan(elewacja)
punkt pod koroną drzewa (h ≥ 3 m w samym punkcie)    ⇒  cień zawsze (gdy słońce nad horyzontem)
```

```python
# krok 4
import json, numpy as np, shapely, geopandas as gpd

AZ = np.arange(0, 360, 22.5)                         # 16 azymutów (od N, zgodnie z zegarem)
EL = np.array([5, 10, 15, 20, 30, 40, 50, 65])       # 8 elewacji [°] (w Krakowie max ~63°)
STEP, MAXD, EYE = 2.0, 120.0, 1.5
D = np.arange(STEP, MAXD + STEP, STEP, dtype=np.float32)

def make_sampler(H, tr):
    x0, y1, res = tr.c, tr.f, tr.a
    def sample(xs, ys):
        col = ((xs - x0) / res).astype(np.int32); row = ((y1 - ys) / res).astype(np.int32)
        ok = (row >= 0) & (row < H.shape[0]) & (col >= 0) & (col < H.shape[1])
        out = np.zeros(xs.shape, np.uint8); out[ok] = H[row[ok], col[ok]]
        return out
    return sample

def edge_points(edges, step=15.0):
    """Punkty co ~15 m; krawędzie u→v i v→u mają tę samą geometrię → liczymy raz."""
    key = np.minimum(edges.u, edges.v).astype(np.int64) * 10**7 + np.maximum(edges.u, edges.v)
    first = ~key.duplicated()
    uniq = edges[first]
    pts, own = [], []
    for i, g in zip(np.flatnonzero(first), uniq.geometry):
        n = max(2, int(g.length / step))
        pts.append(shapely.line_interpolate_point(g, np.linspace(0, 1, n), normalized=True)); own.append(np.full(n, i))
    pts = np.concatenate(pts); own = np.concatenate(own)
    # mapowanie: każdy eid → reprezentant pary (u,v)/(v,u)
    rep = dict(zip(key[first], np.flatnonzero(first)))
    eid_to_rep = np.array([rep[k] for k in key])
    return shapely.get_x(pts), shapely.get_y(pts), own, eid_to_rep

def compute_shade_table(edges, H, tr, chunk=20_000):
    sample = make_sampler(H, tr)
    px, py, own, eid_to_rep = edge_points(edges)
    under = sample(px, py) >= 3
    cnt = np.bincount(own, minlength=len(edges)).astype(np.float32)
    table = np.zeros((len(edges), len(AZ), len(EL)), np.uint8)
    for i, az in enumerate(AZ):
        dx, dy = np.sin(np.radians(az)), np.cos(np.radians(az))
        for j, el in enumerate(EL):
            need = EYE + D * np.tan(np.radians(el))
            s = np.empty(len(px), bool)
            for k in range(0, len(px), chunk):
                xs = px[k:k+chunk, None] + D * dx; ys = py[k:k+chunk, None] + D * dy
                s[k:k+chunk] = (sample(xs, ys) > need).any(1)
            s |= under
            frac = np.bincount(own, weights=s, minlength=len(edges)) / np.maximum(cnt, 1)
            table[:, i, j] = np.round(frac * 255).astype(np.uint8)
        print(f"az {az:5.1f} done", flush=True)
    table = table[eid_to_rep]                       # rozkopiuj na obie strony krawędzi
    tree = (np.bincount(own, weights=under, minlength=len(edges)) / np.maximum(cnt, 1))[eid_to_rep]
    np.save("data/processed/shade.npy", table)
    np.save("data/processed/edge_tree_frac.npy", tree.astype(np.float32))
    json.dump({"az": AZ.tolist(), "el": EL.tolist()}, open("data/processed/shade_bins.json", "w"))
```

**Czas:** ~245 s na 1 mln punktów (zmierzone). Dla grafu Krakowa po filtrze spodziewaj się 0,3–1 mln punktów → **1–5 min**. Jeśli dłużej: `multiprocessing.Pool(len(AZ))` po azymutach, albo krok 20 m zamiast 15 m.

---

## 8. `app/shade/model.py` — runtime

```python
from __future__ import annotations
import json
from functools import lru_cache
import numpy as np, pandas as pd, pvlib
from ..contracts import SunPosition

LAT, LON = 50.06, 19.94

class ShadeModel:
    @classmethod
    def load(cls, data_dir: str, n_edges: int) -> "ShadeModel":
        table = np.load(f"{data_dir}/shade.npy")
        tree = np.load(f"{data_dir}/edge_tree_frac.npy")
        bins = json.load(open(f"{data_dir}/shade_bins.json"))
        assert table.shape[0] == n_edges == tree.shape[0], "cień policzony dla innego grafu — przelicz po zmianie grafu!"
        return cls(table, tree, np.array(bins["az"]), np.array(bins["el"]))

    def __init__(self, table, tree, az, el):
        self.table, self.edge_tree_frac, self.az, self.el = table, tree.astype(np.float32), az, el
        self._ones = np.ones(table.shape[0], np.float32)

    def sun(self, at) -> SunPosition:
        sp = pvlib.solarposition.get_solarposition(pd.DatetimeIndex([at]), LAT, LON)
        return SunPosition(float(sp["azimuth"].iloc[0]), float(sp["apparent_elevation"].iloc[0]))

    def edge_shade(self, at) -> np.ndarray:
        s = self.sun(at)
        if s.elevation_deg <= 0:
            return self._ones                                     # noc: brak słońca = „cień"
        i = int(round(s.azimuth_deg / (360 / len(self.az)))) % len(self.az)
        e = float(np.clip(s.elevation_deg, self.el[0], self.el[-1]))
        j1 = int(np.searchsorted(self.el, e)); j0 = max(j1 - 1, 0); j1 = min(j1, len(self.el) - 1)
        w = 0.0 if j0 == j1 else (e - self.el[j0]) / (self.el[j1] - self.el[j0])
        return self._mix(i, j0, j1, round(w, 2))

    @lru_cache(maxsize=64)
    def _mix(self, i, j0, j1, w):
        a = self.table[:, i, j0].astype(np.float32); b = self.table[:, i, j1].astype(np.float32)
        return ((1 - w) * a + w * b) / 255.0
```

`at` musi być **tz-aware** (Europe/Warsaw) — pvlib inaczej założy UTC i cień przesunie się o 2 h. Test to wyłapie.

---

## 9. Testy i walidacja

```python
# tests/test_shade.py
import numpy as np, pytest, os
from datetime import datetime
from zoneinfo import ZoneInfo
pytestmark = pytest.mark.skipif(not os.path.exists("data/processed/shade.npy"), reason="brak cienia")
from app.shade.model import ShadeModel
TZ = ZoneInfo("Europe/Warsaw")

@pytest.fixture(scope="module")
def m():
    n = np.load("data/processed/shade.npy", mmap_mode="r").shape[0]
    return ShadeModel.load("data/processed", n)

def test_sun_krakow_noon(m):
    s = m.sun(datetime(2025, 7, 3, 14, tzinfo=TZ))
    assert 200 < s.azimuth_deg < 230 and 55 < s.elevation_deg < 63       # zmierzone: 215°, 59°

def test_evening_more_shade(m):
    a = m.edge_shade(datetime(2025, 7, 3, 14, tzinfo=TZ)).mean()
    b = m.edge_shade(datetime(2025, 7, 3, 18, 30, tzinfo=TZ)).mean()
    assert b > a                                                           # centrum: 34% → 70%

def test_night(m):
    assert m.edge_shade(datetime(2025, 7, 3, 23, tzinfo=TZ)).min() == 1.0

def test_range(m):
    s = m.edge_shade(datetime(2025, 7, 3, 10, tzinfo=TZ))
    assert s.min() >= 0 and s.max() <= 1 and s.dtype == np.float32
```

**Walidacja wizualna (H6–8, też materiał na slajd):** matplotlib — krawędzie centrum pokolorowane cieniem o 14:00 i 18:30 obok siebie; sprawdź na oko: Planty i Park Jordana ciemne (drzewa), wąskie ulice Kazimierza wieczorem w cieniu, szerokie aleje w południe w słońcu.

---

## 10. Ryzyka i plan B

| Ryzyko | Plan B |
|---|---|
| Graf od Roli 1 się spóźnia | ShadeModel na siatce punktów co 50 m + przypisanie najbliższego punktu do środka krawędzi (gorsza jakość, ten sam interfejs) |
| Liczenie tablicy za wolne | krok 20 m, `EL` bez 65°, Pool po azymutach; ostatecznie tylko 4 azymuty × 4 elewacje |
| LoD1 niedostępny | OSM + wysokości domyślne (sekcja 4) |
| MSIP niedostępny | OSM drzewa (PBF) + `landuse=forest/park` |
| Graf przebudowany po H4 | przelicz (~kilka min) — dlatego skrypt ma być jednym poleceniem `make shade` |
| Wszystko zawodzi | `MOCK_MODULES=shade`: ECO działa na samym smogu/UV, cień = `edge_tree_frac` lub stała |

## 11. Czego NIE robić

- Nie licz poligonów cieni (shapely `project`/`union`) — raster + promień jest szybszy i wystarczający.
- Nie używaj Google Earth Engine (wymaga rejestracji projektu) ani Sentinel do cienia.
- Nie licz cienia online per żądanie — tylko lookup w tablicy.
- Nie zapominaj o strefie czasowej (`tz-aware`).
