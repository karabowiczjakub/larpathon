# Shade — przekazanie Roli 03

Implementacja obejmuje wyłącznie budynki, drzewa jako przeszkody, Słońce,
preprocessing cienia i odczyt przygotowanych wartości. Nie zawiera routingu,
pogody, API Flask ani frontendu.

## Decyzje i zgodność

Obowiązuje hierarchia z zadania: `PLAN.md > shade.md > AGENTS.md`.
`shade.md` odsyła do `roles/03_shade_buildings_sun.md`; kontrakt pochodzi z
`roles/04_backend_integration.md` §4. Zachowano pliki p03/p04/p05 z PLAN oraz
`app/shade/model.py` i `make shade` z opisu roli.

PLAN §7.3 przewiduje T1 z OSM oraz T2 z LoD1 nadpisujący T1. Dostarczony LoD1
ma więc pierwszeństwo; brakujące wysokości uzupełnia OSM dopasowany największym
polem przecięcia obrysów. Pozostają również budynki OSM niepokryte LoD1.

Hierarchia wysokości:

1. GUGiK `measuredHeight` — `gugik_measuredHeight`.
2. OSM `height` — `osm_height` (metry; jawnie oznaczone stopy przeliczane).
3. `building:levels * 3.2 + 1` — `osm_levels_estimate`.
4. `house=7`, `apartments=15`, `commercial=12`, pozostałe `9 m` — `default_*`.

`retail` otrzymuje **9 m**: PLAN przypisuje go do „inne”, mimo że dokument roli
rozszerza `commercial` o `retail=12`. Brak, NaN, inf, wartości niedodatnie,
niejednoznaczne tagi i wysokości ponad zakres rastra 255 m uruchamiają fallback.
`height_source` i `footprint_source` zostają w `buildings.parquet` oraz w metadanych
LUT. Tagi OSM nie są deklarowane jako pomiar geodezyjny; kondygnacje i wartości
domyślne są przybliżeniem.

## Kontrakt integracyjny

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from app.shade.model import ShadeModel

shade = ShadeModel.load("data/processed", n_edges=graph.n_edges)  # raz przy starcie
at = datetime(2025, 7, 3, 14, tzinfo=ZoneInfo("Europe/Warsaw"))
sun = shade.sun(at)                 # SunPosition(azimuth_deg, elevation_deg)
values = shade.edge_shade(at)        # (E,), float32, skończone 0..1
trees = shade.edge_tree_frac         # (E,), float32, rzeczywista maska koron
segment_fraction = float(values[eid])
```

Wszystkie tablice mają kolejność `eid` z `edges.parquet`; wymagane `eid=0..E-1`
w kolejności wierszy. Nie ma zależności od nazw kolumn węzłów (`u/v`, `u_i/v_i`,
`u_idx/v_idx`). Żaden graf nie jest modyfikowany. Zwracane tablice są tylko do
odczytu; jeśli konsument potrzebuje je zmienić, używa `.copy()`.

Każdy `datetime` musi zawierać strefę/offset. Równoważne chwile z Warszawy i UTC
dają te same wartości. Cache Słońca używa pełnej chwili UTC (łącznie z datą),
co rozróżnia także dwa wystąpienia tej samej godziny przy zmianie czasu zimowego.
Cache interpolacji należy do konkretnej instancji modelu i obejmuje azymut,
oba biny elewacji i dokładną wagę. Nie zaokrągla czasu do całej godziny.
Backend może osobno stosować swoje koszyki czasowe.

`SunPosition` i `ShadeModelP` są jedynymi dodanymi kontraktami w `app/contracts.py`.
Pakiet `app/` musi istnieć, aby ten import działał obok starego `app.py`.
`app/__init__.py` nie implementuje fabryki Flask; pozostaje to zadaniem Backend.
Dotychczasowy skrypt nadal można uruchamiać przez `streamlit run app.py`.

Brak artefaktów jest jawnym błędem. Backend może **jawnie** wybrać:

```python
from app.shade.mock import MockShade
shade = MockShade(graph.n_edges)                 # stała 0.3 za dnia
# albo MockShade(graph.n_edges, tree_frac=prepared_tree_fractions)
```

Mock jest deterministyczny; nocą zwraca 1. Przełącznik `MOCK_MODULES=shade` ma
obsługiwać Backend — moduł shade nie czyta konfiguracji API ani nie ukrywa błędów
ładowania przez automatyczny mock.

## Przygotowanie danych

W katalogu projektu aktywuj istniejące środowisko:

```bash
source .venv/bin/activate
python -m pipeline.shade_build --help
```

Po otrzymaniu `data/processed/edges.parquet` od Roli 1:

```bash
# Jawne pobranie GUGiK LoD1 2024 (1261) i MSIP 2015:
make shade SHADE_ARGS='--download'

# Praca bez internetu, lokalny LoD1 + drzewa przygotowane wcześniej:
make shade SHADE_ARGS='--lod1 "data/raw/lod1/**/*.gml" --trees data/interim/trees.parquet'

# OSM jako źródło zapasowe budynków i drzew, bez przetwarzania grafu:
make shade SHADE_ARGS='--osm-pbf data/raw/krakow.osm.pbf'

# Ponowne przeliczenie po zmianie grafu; używa lokalnych budynków i drzew:
make shade
```

`make` domyślnie używa `.venv/bin/python`; można podać `PYTHON=python`.
`--osm-buildings` przyjmuje GeoParquet z tagami OSM, `--buildings` gotowy
GeoParquet z poprawną kolumną `height` w metrach. Lokalny `--trees` wymaga
zadeklarowanego CRS; brak kolumny `height` oznacza jawne założenie 12 m.
OSM PBF jest filtrowany do bbox Krakowa z PLAN; nie jest pobierany automatycznie.
LoD1 pobiera się wyłącznie przy `--download`; ZIP jest zachowywany w `data/raw/`.

Jeśli LoD1/MSIP zawiedzie, program korzysta z podanego OSM/PBF. Brak wszystkich
danych danego typu domyślnie zatrzymuje preprocessing z komunikatem. Świadomie
uboższy model wymaga `--allow-missing-buildings` lub `--allow-missing-trees`;
braki są zapisywane w metadanych i logowane. Dopuszczenie obu braków daje zero
cienia za dnia. Puste/błędne geometrie są pomijane z ostrzeżeniem.

Artefakty:

| Plik | Zawartość |
|---|---|
| `buildings.parquet` | Obrysy EPSG:2180, wysokości i pochodzenie |
| `trees.parquet` | Korony EPSG:2180, wysokości i pochodzenie |
| `heights_2m.tif` | Maksymalna wysokość przeszkód, uint8, metry |
| `trees_2m.tif` | Osobny raster drzew, bez budynków |
| `shade.npy` | uint8 `(E,16,8)`; udział cienia ×255 |
| `edge_tree_frac.npy` | float32 `(E,)`; wyłącznie udział koron |
| `shade_bins.json` | Biny, parametry, źródła, braki, fingerprint grafu i cache |

Cache preprocessingu obejmuje dokładny plik krawędzi, geometrie i wysokości
przeszkód, pochodzenie, CRS, bounds, rozdzielczość, krok próbkowania, parametry
promieni i biny. `--force` wymusza przeliczenie. LUT pokrywa wszystkie biny,
więc jej klucz nie wymaga czasu konkretnego żądania. Nie przebudowuj artefaktów
w trakcie pracy serwera; po zakończeniu załaduj nową instancję `ShadeModel`.

`load()` sprawdza liczbę krawędzi oraz SHA-256 pliku `edges.parquet`, także gdy
graf zmienił się bez zmiany E. Starszy plik `shade_bins.json` zawierający tylko
`az/el` jest obsługiwany zgodnie z kontraktem roli, ale wtedy sprawdzane jest
jedynie E. Nowy pipeline zawsze zapisuje fingerprint.

## Model i granice dokładności

- Geometria i długości: wyłącznie **EPSG:2180**, x=easting, y=northing.
  GeoParquet z EPSG:4326 jest przeliczany na wejściu; brak CRS to błąd.
  LoD1 jest źródłem EPSG:2180, z trójkami x/y/z; jawny inny CRS jest odrzucany.
- pvlib `get_solarposition`, `apparent_elevation`, punkt `(50.06, 19.94)`.
  Azymut zgodnie z biblioteką: N=0°, E=90°, S=180°, W=270°.
- Ray-marching w kierunku Słońca: `h > 1.5 + d*tan(elevation)`;
  `d=2,4,...,120 m`. Cień obiektu rozciąga się w przeciwnym kierunku.
  Uwzględniając wysokość oka, granica to `(h-1.5)/tan(elevation)`.
- Elewacja `<=0`: wynik 1 („brak bezpośredniego słońca” zgodnie z PLAN).
  Elewacja `0..5°`: bin 5°. Powyżej 65°: ostatni bin. Promień nigdy nie
  przekracza 120 m. Brak dzielenia przez `tan(0)`.
- Najbliższy kołowo bin azymutu, interpolacja liniowa elewacji;
  remis azymutu rozstrzyga pierwszy bin. Kwantyzacja LUT wynosi 1/255.
- Próbki ze środków równych części odcinka, co najwyżej co 15 m, minimum 2;
  średnia jest przybliżeniem udziału długości. Identyczne odwrócone geometrie
  liczone są raz. Równoległe krawędzie o różnych geometriach pozostają osobne.
- Wadliwe/puste/zerowe geometrie krawędzi zachowują swoje eid z wynikiem 0
  za dnia i ostrzeżeniem. Oczekiwany typ krawędzi: LineString.
- Budynki Polygon/MultiPolygon są naprawiane przez `make_valid`;
  niepoligonowe resztki są odrzucane. CityGML wybiera najniższe poziome
  powierzchnie, zachowując otwory i rozłączne części na tej samej wysokości.
- MSIP to **2015 r.**, wysokość drzew **12 m jest założeniem**. OSM tree:
  korona o promieniu 3 m, wysokość 10 m. Fallback forest/park: 12 m,
  przybliżenie pełnej korony na poligonie.
- Raster obcina ułamki metra; płaski teren, brak nDSM i sezonowości liści.
  Północ geograficzna jest przybliżana północą siatki EPSG:2180 zgodnie
  z modelem z PLAN. Dopasowanie OSM/LoD1 jest przestrzenne, bez wspólnego ID.
- Bez NDVI/Sentinel, BDOT jako drugiego adaptera, poligonów cieni i ray tracingu 3D.
  PLAN pozwala wybrać LoD1 **albo** BDOT jako T2; nDSM jest poza Must/Should.

Konwencje sprawdzono w [dokumentacji pvlib solarposition](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.solarposition.get_solarposition.html)
i [kodzie pvlib shading](https://github.com/pvlib/pvlib-python/blob/main/pvlib/shading.py).

## Ryzyka z dokumentów

PLAN nie ma sekcji nazwanej `03_shade_buildings_sun`; właściwe wymagania są w
§4.1, §7.3–7.5, §8.1, §15.3, §17 i §19. Dokument roli uzupełnia je w §10.

| Ryzyko / przyczyna | Zabezpieczenie | Weryfikacja |
|---|---|---|
| PLAN §17: koszt obliczeń cienia | LUT offline, porcje, deduplikacja geometrii, cache; `--sample-step 20`, awaryjne `--coarse` 4×4 | deterministyczność różnych porcji; test coarse/cache; benchmark runtime |
| PLAN §17/19: długie parsowanie CityGML/BDOT | iterparse z usuwaniem przetworzonych elementów, OSM T1 i domyślne wysokości | lokalne GML/OSM, błędna geometria, brak wysokości i symulowana awaria |
| PLAN §17: MSIP z 2015 | rocznik/założenia w danych i dokumentacji; aktualizacja satelitarna poza rolą | test metadanych źródła i wysokości 12 m |
| PLAN §17: brak internetu | preprocessing uruchamiany jawnie, odczyt lokalnej LUT, brak HTTP w runtime | lokalne fixture i mockowany transport HTTP |
| Rola §10: graf spóźniony | siatka 50 m do prób, niezależny MockShade dla integracji | test siatki i mocka |
| Rola §10: LoD1/MSIP niedostępne | dostarczony OSM/PBF, korony/forest/park; jawne tryby brakujących warstw | test awarii obu źródeł |
| Rola §10: graf przebudowany | numeracja eid + SHA-256, ponownie `make shade` | test zmiany geometrii przy tym samym E |
| Rola §10: wszystko zawodzi | jawny MockShade ze stałą lub dostarczonym tree_frac | zakres, deterministyczność, noc |

Nie wdrażano dodatkowo multiprocessing: porcje i zredukowane biny zapewniają
prostszy plan B. Standardowym artefaktem pozostaje 16×8.

## Walidacja i raport

```bash
python -m pytest -q
python -m pip check
python -m ruff check app pipeline scripts/shade_report.py tests
python -m ruff format --check app pipeline scripts/shade_report.py tests

python -m scripts.shade_report --bbox 19.91 50.04 19.96 50.08 --label 'Krakow centre'
```

Raport zapisuje `shade_comparison.png` oraz JSON z procentami cienia ważonymi
długością odcinków, udziałem koron i pozycją Słońca dla 14:00 i 18:30 w Warszawie.
Nie weryfikuje automatycznie, że wieczorem każda konkretna ulica ma więcej cienia;
takie założenie byłoby nieprawdziwe dla części geometrii.

Bez grafu można przygotować siatkę do kontroli modelu:

```bash
make shade SHADE_ARGS='--preview-grid 566000 243000 568000 245000 --output data/shade_preview --download'
python -m scripts.shade_report --data-dir data/shade_preview --output data/shade_preview/grid.png --label 'Temporary 50 m grid'
```

Siatka jest oznaczona `preview_grid=true` i ma własne eid — nie należy jej
podłączać do routingu. Po otrzymaniu grafu przelicz pełną LUT; do tego czasu
Backend korzysta z MockShade.

Nie ma jeszcze zamrożonego grafu Roli 1 ani danych Krakowa w tym repozytorium.
Testy wykonują mały preprocessing lokalnie i nie pobierają GIS. Mapa rzeczywistego
centrum i procenty na slajd wymagają uruchomienia powyższych poleceń na tych danych.
Wygenerowane rastry, tablice i raporty są ignorowane przez Git.

## Uwagi dla zespołu

- Routing: przekaż EPSG:2180 LineString i kolejność `eid`; po przebudowie grafu
  powiadom o konieczności ponownego `make shade`.
- Backend: zachowaj dwa kontrakty shade przy rozszerzaniu `app/contracts.py`,
  ładuj model raz, przekaż tz-aware `at`, wybieraj mock jawnie. Nie zaokrąglaj
  suwaka 18:30 do 18:00 w cache kosztów.
- Environment: `edge_tree_frac` nie obejmuje budynków. Cień nocą równy 1
  oznacza wyłącznie brak bezpośredniego światła; to nie pełna eliminacja UV.
- Frontend/pitch: podaj źródła © OpenStreetMap contributors (ODbL), GUGiK/PZGiK,
  MSIP Kraków 2015 oraz przybliżone wysokości drzew. Nie używaj syntetycznych
  procentów jako pomiaru Krakowa.
