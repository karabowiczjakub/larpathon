# AirRoute Kraków — plan projektu (HackYeah 2026)

> **Aktualizacja 3.10.2026:** backend to **Flask** (nie FastAPI). Szczegółowe plany ról, kontrakty i zweryfikowane dane są w katalogu `roles/` — **mają pierwszeństwo** przed tym dokumentem. Ten plik traktuj jako tło koncepcyjne.

> **Nazwa robocza.** Aplikacja webowa wyznaczająca trasy rowerowe po Krakowie, które chronią przed smogiem, upałem i UV (preferuje cień i zieleń). Zamiast jednej „najlepszej" trasy pokazuje **front Pareto**: kilka tras o różnym kompromisie *czas ↔ zdrowie*, z wyjaśnieniem, *dlaczego* każda z nich tak biegnie.

---

## Spis treści

0. [TL;DR i podjęte decyzje](#0-tldr-i-podjęte-decyzje)
1. [Regulamin, kryteria i co z nich wynika](#1-regulamin-kryteria-i-co-z-nich-wynika)
2. [Produkt: co widzi użytkownik](#2-produkt-co-widzi-użytkownik)
3. [Źródła danych (zweryfikowane, z linkami)](#3-źródła-danych-zweryfikowane-z-linkami)
4. [Architektura systemu](#4-architektura-systemu)
5. [Struktura repozytorium](#5-struktura-repozytorium)
6. [Getting started: środowisko → pierwsze uruchomienie](#6-getting-started-środowisko--pierwsze-uruchomienie)
7. [Pipeline offline (przygotowanie danych)](#7-pipeline-offline-przygotowanie-danych)
8. [Model środowiskowy krawędzi (smog, upał, cień, UV)](#8-model-środowiskowy-krawędzi-smog-upał-cień-uv)
9. [Logika rozmyta: model dyskomfortu](#9-logika-rozmyta-model-dyskomfortu)
10. [Silnik tras: Dijkstra-sweep + NSGA-II „Route Morphing"](#10-silnik-tras-dijkstra-sweep--nsga-ii-route-morphing)
11. [Backend: FastAPI](#11-backend-fastapi)
12. [Frontend: HTML + CSS + vanilla JS + Leaflet](#12-frontend-html--css--vanilla-js--leaflet)
13. [Testy i wydajność](#13-testy-i-wydajność)
14. [Uruchomienie na demo (lokalnie)](#14-uruchomienie-na-demo-lokalnie)
15. [Plan 24 h, role i kamienie milowe](#15-plan-24-h-role-i-kamienie-milowe)
16. [Pitch: 10 slajdów pod kryteria oceny](#16-pitch-10-slajdów-pod-kryteria-oceny)
17. [Ryzyka i plan B](#17-ryzyka-i-plan-b)
18. [Licencje i atrybucje](#18-licencje-i-atrybucje)
19. [Otwarte kwestie do sprawdzenia na miejscu](#19-otwarte-kwestie-do-sprawdzenia-na-miejscu)

---

## 0. TL;DR i podjęte decyzje

| Obszar | Decyzja |
|---|---|
| Kategoria | **Decyzja po briefie** (Smart City vs Sport & Healthcare). Plan pasuje do obu, w pitchu przesuwamy akcent (sekcja 16). |
| Backend | **Python 3.12 + FastAPI** (Swagger `/docs` gratis, walidacja Pydantic). |
| Frontend | **Czysty HTML + CSS + vanilla JS**, mapa **Leaflet** z CDN, wykres **Chart.js** z CDN. Bez npm i bez build stepu, serwowane statycznie przez FastAPI. |
| Silnik | **Etap 1 (MVP):** Dijkstra-sweep po wagach na `scipy.sparse.csgraph`, cel < 0,5 s. **Etap 2:** NSGA-II (DEAP) z mutacją „Route Morphing" jako tryb *Deep search* ze streamingiem frontu na żywo. |
| Model dyskomfortu | **Logika rozmyta (scikit-fuzzy)**, policzona offline do tablic LUT i interpolowana wektorowo online. 4 profile: *Standard, Asthma/Allergy, Senior/Child, Athlete*. |
| ML | Uczciwa heurystyka mikroklimatu: model (HistGradientBoosting, opcjonalnie MLP do porównania) uczony na **temperaturze powierzchni z Landsata** (etykieta) z cechami zieleni/zabudowy. Wynik: anomalia cieplna dla każdej krawędzi. |
| Obszar | **Kraków w granicach miasta.** |
| Punkty | A→B→…→N jak podał użytkownik + checkbox **„Optimize order"** (start i koniec stałe, środek permutowany, maks. 7 punktów). |
| Dane | **Live** (Open-Meteo + GIOŚ) + **scenariusze historyczne**: *Heatwave 3.07.2025 14:00* (34,5°C, bezchmurnie) i *Smog 20.01.2025 wieczór*. Oba zweryfikowane w API. |
| Język | **UI i slajdy po angielsku**, ten plan po polsku. |
| Deploy | **Lokalnie, za darmo**: `make run` lub `docker compose up` na laptopie. Do zgłoszenia nagrywamy demo wideo. |
| Klucze API | **MVP nie wymaga żadnego klucza.** OSM, Open-Meteo, GIOŚ, MSIP i Planetary Computer są bezkluczowe. Airly opcjonalnie. |

> ⚠️ **Zasady konkursu (pkt 5 regulaminu):** liczy się praca rozpoczęta od startu konkursu. Ten dokument to **plan koncepcyjny**. Kod (w tym fragmenty z tego planu) piszemy i commitujemy **po starcie**. Przed startem: tylko lektura dokumentacji i ewentualnie zakładanie kont. Czy wolno wcześniej pobrać publiczne dane, warto potwierdzić u organizatorów na Discordzie.

---

## 1. Regulamin, kryteria i co z nich wynika

Oba regulaminy (Smart City i Sport & Healthcare) są identyczne co do zasad:

- **Termin:** praca od **3.10, 11:00 PM**, zgłoszenie do **4.10, 11:00 PM** na HackTribe. Godzinę startu warto potwierdzić, bo „11:00 PM" może być literówką.
- **Zgłoszenie:** tytuł, nazwa zespołu, członkowie (1–6), opis, **PDF max 10 slajdów** (zrzuty, repo, link do demo/wideo).
- **Szczegóły zadania będą podane na starcie.** Plan trzeba będzie dopasować do briefu.
- **Ocena:** faza 1 to mentorzy oceniający zgłoszenie (PDF), faza 2 to pitch finalistów. Żeby dostać nagrodę, potrzeba min. 50% punktów w fazie 1.

| Kryterium | Waga | Czym je zdobywamy |
|---|---|---|
| Idea & Innovation | 30% | Front Pareto zamiast jednej trasy, **cień zależny od godziny** (pozycja słońca + wysokości budynków i drzew), fuzzy + EA z uczciwym uzasadnieniem (punkty niewypukłe frontu), wyjaśnialność tras. |
| Relation to Category | 20% | Smart City: dane miejskie (MSIP), korekta modelu CAMS stacjami GIOŚ, warstwy dla urzędu. S&H: **dawka wdychana** PM2.5, profile zdrowotne, stres cieplny UTCI. |
| Practical Applicability | 20% | Działa na żywych danych, odpowiedź < 1 s, prosty UI, realne trasy po Krakowie, zrozumiałe liczby („−38% wdychanego PM2.5 za +4 min"). |
| Design | 20% | Czytelna mapa, 3 karty tras, wykres Pareto, kolorowanie odcinków, wyjaśnienia „Avoids: Al. Krasińskiego (high PM, no shade)". |
| Completeness | 10% | Działający end-to-end, testy, benchmark czasu, README, wideo. |

**Wniosek:** algorytmika ma wartość tylko wtedy, gdy *widać ją na demo i slajdach*. Stąd streaming frontu NSGA-II na żywo i licznik „computed in 412 ms".

---

## 2. Produkt: co widzi użytkownik

**Scenariusz demo (90 s):**

1. Użytkownik wybiera scenariusz *Heatwave — 3 Jul 2025, 14:00* i profil *Senior*.
2. Klika na mapie: **A** Rynek Główny → **B** Kampus AGH → **C** Bulwary Wiślane.
3. Klika **Find routes**. W ~0,4 s pojawiają się 3 trasy:
   - **Fastest** (szara): 6,1 km, 24 min, cień 18%, 9 min w silnym stresie cieplnym.
   - **Balanced** (fioletowa): +3 min, cień 47%, −52% minut w stresie cieplnym.
   - **Coolest/Cleanest** (zielona): +7 min, cień 71%, prowadzi przez Planty i Park Jordana.
4. Każda karta pokazuje „Avoids: Al. Mickiewicza (heat stress, no shade)".
5. Suwak **Depart at** przesuwa godzinę z 14:00 na 18:30. Cienie się wydłużają i trasa *Coolest* zmienia przebieg. **To jest moment „wow".**
6. Przełączenie na *Smog — Jan 2025* i profil *Asthma*: trasy omijają główne arterie, karta pokazuje „PM2.5 inhaled: 41 µg → 23 µg".
7. **Deep search (NSGA-II):** wykres Pareto animuje się na żywo, a pomarańczowe punkty oznaczone ★ to trasy, *których sweep Dijkstry nie potrafi znaleźć* (niewypukła część frontu).

(Liczby powyżej są ilustracyjne. Na slajdy idą wyniki z prawdziwych przebiegów.)

---

## 3. Źródła danych (zweryfikowane, z linkami)

Legenda statusu: ✅ przetestowane na żywo 3.10.2026 (zapytanie zwróciło dane) · 📄 potwierdzone w dokumentacji · ⚠️ do sprawdzenia na miejscu.

### 3.1 Tabela zbiorcza

| # | Źródło | Co bierzemy | Rozdzielczość | Dostęp | Status |
|---|---|---|---|---|---|
| 1 | **OpenStreetMap** przez [OSMnx](https://osmnx.readthedocs.io) / [Overpass](https://overpass-api.de) | Graf rowerowy (`network_type="bike"`), klasy dróg, nazwy ulic, nawierzchnia, oświetlenie, obrysy budynków + `building:levels`/`height` | wektor | bez klucza, ODbL | 📄 (Overpass niedostępny z mojego środowiska testowego, sprawdzić u siebie) |
| 2 | [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | `temperature_2m, relative_humidity_2m, wind_speed_10m, shortwave_radiation, direct_normal_irradiance, diffuse_radiation, cloud_cover` | model ~2–11 km | bez klucza, CC BY 4.0 | ✅ |
| 3 | [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | To samo dla scenariuszy (np. 3.07.2025 14:00: 34,5°C, DNI 853 W/m², 0% chmur) | ERA5 / reanaliza | bez klucza | ✅ |
| 4 | [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api) | `pm10, pm2_5, nitrogen_dioxide, uv_index, uv_index_clear_sky, european_aqi` (CAMS) | **CAMS Europe 0,1° ≈ 11 km**, godzinowe, prognoza do 7 dni, `past_days` do 92, `start_date/end_date` dla historii | bez klucza | ✅ (także historia: 20.01.2025) |
| 5 | **GIOŚ API v1**: [Swagger](https://api.gios.gov.pl/pjp-api/swagger-ui/), [opis](https://powietrze.gios.gov.pl/pjp/content/api) | Pomiary PM10/PM2.5/NO2 z 9 stacji w Krakowie (bieżące + archiwalne), indeks jakości powietrza | punktowe | bez klucza, limity per endpoint | ✅ |
| 6 | **Airly API** ([developer hub](https://developer.airly.org/en)) | Gęsta sieć czujników w Krakowie, `measurements/point` interpoluje z czujników do 1,5 km | punktowe, gęste | **wymaga klucza** (nagłówek `apikey`) | ⚠️ opcjonalnie, limity planu darmowego do sprawdzenia |
| 7 | **MSIP Kraków, Monit-Air** (ArcGIS REST): [katalog](https://msip.krakow.pl/228340,artykul,katalog-danych.html), [dane wektorowe](https://msip.krakow.pl/dataset/1113), [rastrowe](https://msip.krakow.pl/dataset/2601) | **Mapa zieleni 2015** (zieleń wysoka/niska/sportowa), korytarze przewietrzania, mapa dyspersji zanieczyszczeń | wektor (wysoka szczegółowość) | bez klucza, `f=geojson`, paginacja po 1000 | ✅ |
| 8 | [Geoportal: Modele 3D budynków](https://www.geoportal.gov.pl/pl/dane/inne-dane/modele-3d-budynkow/) | Wysokości budynków (LoD1 2024 z LiDAR, LoD2 2018), CityGML | budynek | bez klucza | 📄 ⚠️ format do sprawdzenia |
| 9 | Geoportal: [NMPT](https://www.geoportal.gov.pl/pl/dane/numeryczny-model-pokrycia-terenu-nmpt/), [NMT](https://www.geoportal.gov.pl/pl/dane/numeryczny-model-terenu-nmt/), [LiDAR](https://www.geoportal.gov.pl/dane/dane-pomiarowe-lidar) | nDSM = NMPT − NMT, czyli realne wysokości drzew i budynków (upgrade cienia) | ~0,5–1 m | bez klucza, pobieranie arkuszami | 📄 |
| 10 | Landsat 8/9 C2 L2 (temp. powierzchni): [Planetary Computer](https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2) (bez konta) lub [GEE](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1_L2) | LST: etykieta dla modelu mikroklimatu (wyspy ciepła) | 30 m (termalne natywnie 100 m) | bez klucza (PC) | 📄 |
| 11 | Sentinel-2 L2A: [Copernicus Data Space](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S2L2A.html) lub Planetary Computer `sentinel-2-l2a` | NDVI (aktualizacja zieleni, bo MSIP jest z 2015) | 10 m | PC bez klucza; CDSE: darmowe konto | 📄 |
| 12 | Copernicus Land: [Street Tree Layer](https://land.copernicus.eu/en/products/urban-atlas), HRL Tree Cover Density 10 m, [ESA WorldCover](https://doi.org/10.5281/zenodo.7254221) | Zapasowe źródła zieleni/drzew | 10 m / wektor | darmowe konto | 📄 (fallback) |
| 13 | MSIP: [NMT 2023](https://msip.krakow.pl/dataset/2921), [Mesh 2023](https://msip.krakow.pl/dataset/2861), [Budynki](https://msip.krakow.pl/dataset/1308), [Mapy hałasu](https://msip.krakow.pl/dataset/1361), [ZTP rowery](https://msip.krakow.pl/dataset/2963) | Rozszerzenia (hałas jako 4. wejście fuzzy, infrastruktura rowerowa) | różna | regulamin MSIP | 📄 stretch |

### 3.2 Czego świadomie NIE używamy

- **Sentinel-5P.** Piksel ma ok. 5,5 × 3,5 km (pół Krakowa) i satelita nie mierzy PM10, tylko m.in. NO₂ i indeks aerozoli. Na poziomie ulicy nie ma z niego żadnej wartości. Jeśli juror zapyta: „rozważaliśmy, odrzuciliśmy, bo rozdzielczość".
- **Google Earth Engine jako wymóg.** GEE wymaga rejestracji projektu. Ten sam Landsat jest bez konta w Planetary Computer, więc GEE zostaje jako alternatywa.

### 3.3 Szczegóły i przykładowe zapytania

#### Open-Meteo: pogoda (live)

```bash
curl "https://api.open-meteo.com/v1/forecast?latitude=50.06&longitude=19.94\
&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation,cloud_cover\
&wind_speed_unit=ms&forecast_days=2&timezone=Europe%2FWarsaw"
```

- Wiele punktów w jednym zapytaniu: `latitude=50.03,50.06,50.09&longitude=19.88,19.94,20.02` (✅ przetestowane, zwraca listę).
- **Limity darmowe** ([terms](https://open-meteo.com/en/terms)): 600/min, 5 000/h, 10 000/dzień, 300 000/mies. Tylko użycie niekomercyjne, wymagana atrybucja CC BY 4.0.

#### Open-Meteo: historia (scenariusze)

```bash
# Heatwave: 3.07.2025 14:00 → 34.5°C, RH 20%, wiatr 17.4 km/h, SW 862 W/m², DNI 853 W/m², chmury 0%
curl "https://archive-api.open-meteo.com/v1/archive?latitude=50.06&longitude=19.94\
&start_date=2025-07-03&end_date=2025-07-03\
&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_normal_irradiance,diffuse_radiation,cloud_cover\
&timezone=Europe%2FWarsaw"
```

#### Open-Meteo: jakość powietrza i UV

```bash
curl "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=50.06&longitude=19.94\
&hourly=pm10,pm2_5,nitrogen_dioxide,uv_index,european_aqi&forecast_days=2&timezone=Europe%2FWarsaw"

# Historia (scenariusz smogowy): szczyt zimy 2024/25 w Krakowie wg CAMS to 20–23.01.2025
# (PM10 do ~290 µg/m³ o 22:00 20.01). Zweryfikowane zapytaniem start_date/end_date.
curl "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=50.06&longitude=19.94\
&hourly=pm10,pm2_5,nitrogen_dioxide,uv_index&start_date=2025-01-20&end_date=2025-01-20&timezone=Europe%2FWarsaw"
```

> 💡 **Fakt na slajd (zweryfikowany):** 20.01.2025 o 17:00 CAMS (Open-Meteo) podawał w centrum Krakowa **PM10 = 161 µg/m³**, a stacja GIOŚ Al. Krasińskiego zmierzyła **63,2 µg/m³**. Model regionalny potrafi się mylić **2,5 raza**. Dlatego korygujemy go stacjami (sekcja 8.3). To mocny argument za „data fusion".

#### GIOŚ API v1

Stare endpointy bez `/v1/` wyłączono 30.06.2025. Odpowiedzi mają **polskie klucze JSON** (np. `"Lista stacji pomiarowych"`, `"Wartość"`, `"Data"`).

```bash
BASE=https://api.gios.gov.pl/pjp-api/v1/rest
curl "$BASE/station/findAll?size=500"                    # lista stacji
curl "$BASE/station/sensors/400"                         # stanowiska stacji Al. Krasińskiego
curl "$BASE/data/getData/2750"                           # bieżące PM10 (Krasińskiego)
curl "$BASE/aqindex/getIndex/400"                        # indeks jakości powietrza
curl "$BASE/archivalData/getDataBySensor/2750?dateFrom=2025-01-20%2016:00&dateTo=2025-01-20%2020:00&size=50"
```

**Stacje GIOŚ w Krakowie (✅ pobrane z API):**

| ID | Stacja | Lat | Lon | Uwagi |
|---|---|---|---|---|
| 400 | Al. Krasińskiego | 50.057678 | 19.926189 | **komunikacyjna**; sensory: PM10=`2750`, PM2.5=`2752`, NO2=`2747` |
| 401 | ul. Bujaka | 50.010575 | 19.949189 | tło miejskie |
| 402 | ul. Bulwarowa | 50.069308 | 20.053492 | Nowa Huta |
| 10123 | ul. Złoty Róg | 50.081197 | 19.895358 | |
| 10139 | Os. Piastów | 50.098508 | 20.018269 | |
| 10447 | Os. Wadów | 50.100569 | 20.122561 | |
| 11303 | Os. Swoszowice | 49.991442 | 19.936792 | |
| 16896 | ul. Kamieńskiego | 50.024605 | 19.978460 | |
| 20367 | ul. Półłanki | 50.034702 | 20.044386 | |

Sensory pozostałych stacji pobieramy raz skryptem (`station/sensors/{id}`) i zapisujemy do `data/raw/gios_sensors.json`.
**Limity:** strona GIOŚ podaje limity per endpoint (część ~2 zapytania/min, część znacznie więcej, zob. Swagger). Projektujemy więc pobieranie **w tle co 60 min z cache**, nigdy na żądanie użytkownika.

#### MSIP Kraków: ArcGIS REST (✅ przetestowane)

Baza: `https://msip.um.krakow.pl/arcgis/rest/services/MONIT-AIR/`

| Usługa | Warstwy | Do czego |
|---|---|---|
| `WS_MA_Mapa_Zieleni_2015/MapServer/0` | 128 221 poligonów, `class_name` ∈ {`200 Zieleń wysoka`, `300 Zieleń niska`, `400 Zieleń sportowa, ogródki działkowe`} | **drzewa (cień)**, zieleń (efekt chłodzący, filtracja) |
| `WS_MA_Atlas_02_mapa_zieleni_przewietrzania_Krakowa/MapServer` | 1: główne obszary przewietrzania 4 m, 2: obszary II rzędu, 3: przewietrzanie 10 m, 4–5: dachy zielone, 6: potencjał solarny | korytarze przewietrzania → lepsza dyspersja smogu |
| `WS_MA_Atlas_06_mapa_dyspersji_zanieczyszczen/MapServer/3` | raster „Warunki dyspersji zanieczyszczeń" | nakładka wizualna / cecha jakościowa |

```bash
# Pobranie strony 1000 obiektów jako GeoJSON (WGS84)
curl "https://msip.um.krakow.pl/arcgis/rest/services/MONIT-AIR/WS_MA_Mapa_Zieleni_2015/MapServer/0/query\
?where=1%3D1&outFields=class_name&resultOffset=0&resultRecordCount=1000&outSR=4326&f=geojson"
```

#### Airly (opcjonalnie)

```bash
curl -H "apikey: $AIRLY_API_KEY" -H "Accept: application/json" \
  "https://airapi.airly.eu/v2/measurements/point?lat=50.0614&lng=19.9366"
```

Gęsta sieć w Krakowie znacząco poprawiłaby pole PM. Wpinamy jako dodatkowe punkty do korekty z sekcji 8.3, **jeśli** zdobędziemy klucz i limity na to pozwolą.

#### Landsat (LST) przez Planetary Computer: bez konta

Skala Collection 2 ST: `LST[K] = DN × 0.00341802 + 149.0`. Przelot ok. 10:00–10:30 czasu słonecznego, tylko dzień. Kod w sekcji 7.6.

---

## 4. Architektura systemu

### 4.1 Zasada: ciężko offline, lekko online

Cała geometria, cień i ML liczone są **raz, offline**. Online robimy tylko: pobranie warunków (z cache), wektorową arytmetykę na ~150 tys. krawędzi (milisekundy) i Dijkstrę na **zawężonym korytarzu** grafu.

```
                         ┌────────────────────── OFFLINE (make data, ~30–60 min) ──────────────────────┐
 OSM (OSMnx) ───────────►│ p01 graph ──► graph.npz (CSR), edges.parquet, edge_coords.npz               │
 MSIP zieleń ───────────►│ p02 greenery ─┐                                                              │
 OSM/BDOT/LoD1 budynki ─►│ p03 buildings ┴► p04 height raster (2 m) ─► p05 shade LUT (E×16 az×8 el)     │
 Landsat LST + S2 NDVI ─►│ p06 rasters ─► p07 ML mikroklimatu ─► lst_anom per edge                     │
 GIOŚ (rok danych) ─────►│ p08 edge features: f_pm, f_no2, wind_factor, wagi IDW/bilinear              │
 skfuzzy ───────────────►│ p09 fuzzy LUT × 4 profile (.npy)                                            │
 Open-Meteo/GIOŚ hist. ─►│ p10 scenarios/*.json                                                        │
                         └───────────────────────────────┬──────────────────────────────────────────────┘
                                                         │ data/processed/*
                         ┌───────────────────────────────▼──────── ONLINE (FastAPI, 1 proces) ──────────┐
 Open-Meteo, GIOŚ ──────►│ ConditionsService (refresh w tle co 30–60 min, cache, fallback na plik)     │
                         │        │                                                                    │
                         │        ▼                                                                    │
 POST /api/routes ──────►│ ExposureModel: shade(t) → Tmrt → UTCI; PM tło×korekta×f_road; UV×(1−cień)   │
                         │        │   → fuzzy LUT (interp. wektorowa) → D_e ∈ [0,1], t_e [s]           │
                         │        ▼                                                                    │
                         │ Router: snap (KD-tree) → korytarz → Dijkstra-sweep → Pareto → 3 trasy      │
                         │        └─ mode=deep: NSGA-II (DEAP) na korytarzu, streaming NDJSON          │
                         │        ▼                                                                    │
                         │ Explainer: metryki, „Avoids: …", powody per odcinek                         │
                         └───────────────────────────────┬──────────────────────────────────────────────┘
                                                         ▼
                         static/ index.html + style.css + app.js (Leaflet, Chart.js z CDN)
```

### 4.2 Budżet czasu odpowiedzi (cel: p95 < 1 s dla `fast`, ≤ 3–5 s dla `deep`)

| Krok | Szacunek | Jak |
|---|---|---|
| Walidacja + snap punktów | < 1 ms | `scipy.spatial.cKDTree` na węzłach (EPSG:2180) |
| Warunki | 0 ms | cache w pamięci, odświeżany w tle |
| Koszty krawędzi (cień, UTCI, PM, UV, fuzzy) | 20–60 ms | numpy na ~150 tys. elementów; UTCI liczone na unikalnych skwantowanych kombinacjach; **LRU cache** per (scenariusz, godzina, profil) |
| Wycięcie korytarza | 5–15 ms | maska węzłów w elipsach wokół odcinków, slicing CSR |
| Sweep: 9 λ × Dijkstra (k źródeł) | 50–250 ms | `csgraph.dijkstra` na ~5–20 tys. węzłach |
| Pareto + wybór 3 tras + wyjaśnienia | < 10 ms | numpy |
| **NSGA-II** (deep) | budżet 3 s | ~40 osobników × ~20 generacji, Dijkstra ~2–3 ms na korytarzu, algorytm „anytime" |

---

## 5. Struktura repozytorium

```
airroute/
├── README.md
├── PLAN.md                      # ten dokument
├── Makefile
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── Dockerfile                   # opcjonalnie (identyczne środowisko w zespole)
├── docker-compose.yml
├── pipeline/                    # OFFLINE: uruchamiane raz, w kolejności
│   ├── common.py                #   ścieżki, CRS, bbox Krakowa, helpery
│   ├── p01_graph.py             #   OSMnx → CSR + edges.parquet + geometrie
│   ├── p02_greenery.py          #   MSIP ArcGIS → greenery.parquet
│   ├── p03_buildings.py         #   OSM (+BDOT/LoD1) → buildings.parquet z wysokościami
│   ├── p04_height_raster.py     #   rasteryzacja budynków + drzew → heights_2m.tif (uint8)
│   ├── p05_shade.py             #   ray-marching → shade.npy (E,16,8) uint8
│   ├── p06_rasters.py           #   Landsat LST + NDVI (Planetary Computer) → tif
│   ├── p07_microclimate.py      #   ML: LST anomaly ← cechy; predykcja per krawędź
│   ├── p08_edge_features.py     #   f_pm, f_no2, wind_factor, wagi interpolacji, nazwy ulic
│   ├── p09_fuzzy_luts.py        #   skfuzzy → lut_{profile}.npy
│   └── p10_scenarios.py         #   Open-Meteo/GIOŚ historia → scenarios/*.json
├── app/                         # ONLINE
│   ├── main.py                  #   FastAPI, lifespan, montaż static
│   ├── config.py                #   Settings (pydantic-settings)
│   ├── schemas.py               #   modele Pydantic (request/response)
│   ├── state.py                 #   ładowanie artefaktów do pamięci
│   ├── fuzzy/
│   │   ├── model.py             #   definicje zbiorów i reguł (używane przez p09 i testy)
│   │   └── profiles.py          #   parametry profili
│   └── services/
│       ├── conditions.py        #   Open-Meteo + GIOŚ + korekta CAMS + scenariusze
│       ├── sun.py               #   pvlib: pozycja słońca
│       ├── exposure.py          #   koszty krawędzi: t_e, D_e, metryki pomocnicze
│       ├── graph.py             #   CSR, snap, korytarz, rekonstrukcja ścieżek
│       ├── pareto.py            #   dominacja, knee, otoczka wypukła, hypervolume
│       ├── router_fast.py       #   sweep λ + optymalizacja kolejności
│       ├── router_evo.py        #   NSGA-II (DEAP), Route Morphing, streaming
│       └── explain.py           #   „Avoids: …", powody, porównania
├── app/static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── scenarios/                   # COMMITOWANE (małe JSON-y), demo działa bez internetu do danych
│   ├── heatwave_2025-07-03T14.json
│   └── smog_2025-01-20T17.json
├── data/                        # .gitignore
│   ├── raw/  interim/  processed/
├── scripts/
│   ├── bench.py                 #   p50/p95 czasu dla losowych tras
│   └── fetch_artifacts.sh       #   (opcjonalnie) pobranie gotowych artefaktów z dysku zespołu
├── tests/
│   ├── test_fuzzy.py  test_pareto.py  test_graph.py  test_api.py
└── docs/
    ├── slides.pdf  demo.mp4  screenshots/
```

---

## 6. Getting started: środowisko → pierwsze uruchomienie

### 6.1 Wymagania

- **Python 3.12** (Linux/macOS/WSL2; na Windows natywnie też zadziała, bo wszystkie geo-paczki mają wheele).
- ~8 GB RAM do pipeline'u offline (raster wysokości), ~2 GB do działania API.
- ~3–5 GB miejsca na dane surowe.
- Nie trzeba systemowego GDAL: `geopandas` (pyogrio) i `rasterio` mają GDAL w wheelach.

### 6.2 Instalacja

Zalecany jest [uv](https://docs.astral.sh/uv/), bo jest szybki. Klasyczne `venv + pip` działa tak samo.

```bash
git clone <repo> airroute && cd airroute

# wariant A: uv
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt

# wariant B: venv + pip
python3.12 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
```

### 6.3 `requirements.txt`

```text
# API
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.7
pydantic-settings>=2.3
httpx>=0.27
orjson>=3.10
cachetools>=5.3

# numeryka / grafy
numpy>=1.26
scipy>=1.13
pandas>=2.2
pyarrow>=16

# GIS
osmnx>=2.0
networkx>=3.3
geopandas>=1.0
shapely>=2.0
pyproj>=3.6
rasterio>=1.3

# AI
scikit-fuzzy>=0.5
packaging              # skfuzzy 0.5.0 importuje ją, ale nie deklaruje (sprawdzone: bez niej ImportError)
joblib                 # równoległe liczenie LUT
scikit-learn>=1.5
deap>=1.4

# fizyka środowiska
pvlib>=0.11
pythermalcomfort>=2.10

# satelity (tylko pipeline)
pystac-client>=0.8
planetary-computer>=1.0
odc-stac>=0.3
```

`requirements-dev.txt`: `pytest`, `ruff`, `ipykernel`, `matplotlib`, `folium` (szybkie podglądy w notebooku).

> ⚠️ `pythermalcomfort` w wersji 3.x zmienił zwracane typy (dataclassy zamiast dict/float). W kodzie obsługujemy oba warianty (`getattr(res, "utci", res)`). Po instalacji sprawdźcie `pip show pythermalcomfort`.

### 6.4 `.env.example`

```dotenv
DATA_DIR=data/processed
SCENARIO_DIR=scenarios
DEFAULT_SCENARIO=live
CONDITIONS_REFRESH_MIN=30
AIRLY_API_KEY=            # opcjonalnie
LOG_LEVEL=INFO
```

### 6.5 `Makefile`

```makefile
PY := PYTHONPATH=. python

.PHONY: setup data run dev test bench scenarios clean-data

setup:
	uv venv --python 3.12 && uv pip install -r requirements.txt -r requirements-dev.txt

data:                       ## cały pipeline offline (kolejność ma znaczenie)
	$(PY) pipeline/p01_graph.py
	$(PY) pipeline/p02_greenery.py
	$(PY) pipeline/p03_buildings.py
	$(PY) pipeline/p04_height_raster.py
	$(PY) pipeline/p05_shade.py
	$(PY) pipeline/p06_rasters.py
	$(PY) pipeline/p07_microclimate.py
	$(PY) pipeline/p08_edge_features.py
	$(PY) pipeline/p09_fuzzy_luts.py

scenarios:
	$(PY) pipeline/p10_scenarios.py

dev:                        ## autoreload podczas pracy
	uvicorn app.main:app --reload --port 8000

run:                        ## tryb demo: 1 worker (graf w pamięci), bez reload
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

test:
	pytest -q

bench:
	$(PY) scripts/bench.py --n 50
```

### 6.6 Pierwsze uruchomienie (checklista)

1. `make setup`
2. `make data`. Szacunkowo: graf 2–5 min, zieleń MSIP ~3 min (129 stron), budynki 2–5 min, raster 2–5 min, cień 10–20 min, Landsat 5–15 min, reszta < 5 min.
   **Podział pracy:** `p01` i `p02` mogą iść równolegle na dwóch laptopach. Gotowe `data/processed/` udostępniamy reszcie przez dysk zespołu (`scripts/fetch_artifacts.sh`), żeby nie liczyć 4 razy.
3. `make scenarios`
4. `make dev` → http://localhost:8000 (UI) i http://localhost:8000/docs (Swagger).
5. `make test && make bench`

### 6.7 Docker (opcjonalnie)

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY scenarios/ scenarios/
ENV DATA_DIR=/app/data/processed
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports: ["8000:8000"]
    volumes:
      - ./data/processed:/app/data/processed:ro
    env_file: .env
```

Pipeline offline uruchamiamy poza kontenerem (lub w osobnym), a kontener API dostaje tylko gotowe artefakty.

---

## 7. Pipeline offline (przygotowanie danych)

Wspólne stałe (`pipeline/common.py`):

```python
from pathlib import Path

RAW, INTERIM, PROC = (Path("data") / p for p in ("raw", "interim", "processed"))
for p in (RAW, INTERIM, PROC):
    p.mkdir(parents=True, exist_ok=True)

PLACE = "Kraków, Poland"
CRS_METRIC = "EPSG:2180"          # PUWG 1992, metry
CRS_WGS = "EPSG:4326"
BBOX_WGS = (19.79, 49.96, 20.22, 50.13)  # lon_min, lat_min, lon_max, lat_max (z zapasem)
```

### 7.1 `p01_graph.py`: graf rowerowy → CSR

Kluczowe niuanse:

- `scipy.sparse` przy budowie macierzy **sumuje duplikaty** (u,v). Multigraf OSM ma krawędzie równoległe, więc zostawiamy najkrótszą na parę (u,v), bo inaczej wagi się zsumują.
- Trzymamy **mapę slot CSR → id krawędzi** (`perm`). Wtedy zmiana wag to tylko podmiana wektora `data`, bez przebudowy struktury.

```python
import numpy as np
import osmnx as ox
import scipy.sparse as sp
from pyproj import Transformer

from pipeline.common import PLACE, CRS_METRIC, PROC

ox.settings.use_cache = True
ox.settings.useful_tags_way = list(ox.settings.useful_tags_way) + [
    "surface", "lit", "cycleway", "segregated", "smoothness", "oneway:bicycle",
]

G = ox.graph_from_place(PLACE, network_type="bike", simplify=True, retain_all=False)
G = ox.project_graph(G, to_crs=CRS_METRIC)
nodes, edges = ox.graph_to_gdfs(G)

# jedna krawędź na parę (u, v): najkrótsza
edges = edges.sort_values("length")
edges = edges[~edges.index.droplevel("key").duplicated(keep="first")].reset_index()

first = lambda x: x[0] if isinstance(x, list) else x
for col in ("highway", "name", "surface", "lit"):
    if col in edges:
        edges[col] = edges[col].apply(first)

node_idx = {osmid: i for i, osmid in enumerate(nodes.index)}
edges["u_idx"] = edges["u"].map(node_idx).astype(np.int32)
edges["v_idx"] = edges["v"].map(node_idx).astype(np.int32)
edges["eid"] = np.arange(len(edges), dtype=np.int32)

N, E = len(nodes), len(edges)
base = sp.csr_matrix(
    (np.arange(1, E + 1), (edges["u_idx"].to_numpy(), edges["v_idx"].to_numpy())),
    shape=(N, N),
)
perm = (base.data - 1).astype(np.int32)  # perm[slot] = eid

to_wgs = Transformer.from_crs(CRS_METRIC, "EPSG:4326", always_xy=True)
lon, lat = to_wgs.transform(nodes["x"].to_numpy(), nodes["y"].to_numpy())

np.savez_compressed(
    PROC / "graph.npz",
    indptr=base.indptr, indices=base.indices, perm=perm,
    x=nodes["x"].to_numpy(), y=nodes["y"].to_numpy(), lon=lon, lat=lat,
    u=edges["u_idx"].to_numpy(), v=edges["v_idx"].to_numpy(),
    length=edges["length"].to_numpy(np.float32),
)

# geometrie w WGS84 jako płaska tablica + offsety (szybkie składanie trasy w API)
geo = edges.set_geometry("geometry").to_crs("EPSG:4326").geometry
coords = [np.asarray(g.coords, dtype=np.float32) for g in geo]
offs = np.cumsum([0] + [len(c) for c in coords])
np.savez_compressed(PROC / "edge_coords.npz", coords=np.vstack(coords), offs=offs)

edges[["eid", "u_idx", "v_idx", "length", "highway", "name", "surface", "lit", "geometry"]] \
    .to_parquet(PROC / "edges.parquet")
print(f"nodes={N:,} edges={E:,}")
```

> ⚠️ **Do sprawdzenia:** czy geometria krawędzi biegnie zawsze od `u` do `v` (jeśli pierwszy punkt jest dalej od `u` niż od `v`, to odwracamy). Trzeba też zweryfikować kontraruch rowerowy (`oneway:bicycle=no`) w kilku znanych ulicach jednokierunkowych w centrum.

### 7.2 `p02_greenery.py`: zieleń z MSIP (ArcGIS REST, paginacja)

```python
import httpx, geopandas as gpd, pandas as pd
from pipeline.common import RAW, CRS_METRIC

URL = ("https://msip.um.krakow.pl/arcgis/rest/services/MONIT-AIR/"
       "WS_MA_Mapa_Zieleni_2015/MapServer/0/query")

def fetch_all(url: str, page: int = 1000) -> gpd.GeoDataFrame:
    parts, offset = [], 0
    with httpx.Client(timeout=60) as c:
        while True:
            r = c.get(url, params={
                "where": "1=1", "outFields": "class_name", "outSR": 4326, "f": "geojson",
                "resultOffset": offset, "resultRecordCount": page,
            })
            r.raise_for_status()
            feats = r.json()["features"]
            if not feats:
                break
            parts.append(gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326"))
            offset += page
    return pd.concat(parts, ignore_index=True)

g = fetch_all(URL).to_crs(CRS_METRIC)
g["kind"] = g["class_name"].str[:3].map({"200": "tall", "300": "low", "400": "sport"})
g.to_parquet(RAW / "msip_greenery.parquet")
```

Analogicznie pobieramy warstwy 1–3 z `WS_MA_Atlas_02_mapa_zieleni_przewietrzania_Krakowa` (korytarze przewietrzania).

### 7.3 `p03_buildings.py`: budynki z wysokościami (warstwowo, od najprostszego)

| Poziom | Źródło | Wysokość | Kiedy |
|---|---|---|---|
| **T1** (MVP) | OSM `features_from_place(PLACE, {"building": True})` | `height`, a jeśli brak: `building:levels × 3.2 + 1`, a jeśli brak: domyślna wg typu (`house` 7 m, `apartments` 15 m, `commercial` 12 m, inne 9 m) | od razu |
| **T2** | BDOT10k (Geoportal, paczka powiatowa), atrybut liczby kondygnacji, albo **LoD1 2024** (wysokości z LiDAR) | join przestrzenny po obrysie, nadpisuje T1 | jeśli parsowanie zajmie < 1 h |
| **T3** | nDSM = NMPT − NMT (Geoportal) | realna wysokość wszystkiego, też drzew | stretch, np. tylko dla centrum |

### 7.4 `p04_height_raster.py`: raster wysokości przeszkód (2 m)

- Budynki: `rasterio.features.rasterize` z wartością = wysokość, `merge_alg=replace` po posortowaniu rosnąco wysokości (wyższe nadpisują).
- Drzewa: MSIP `kind == "tall"` z wysokością **12 m** (założenie, opisane na slajdzie). W T3 zastępujemy je nDSM.
- Typ `uint8` (metry, 0–255). Kraków ~31 × 20 km w 2 m to ~155 MB w RAM, akceptowalne.
- Zapis: `heights_2m.tif` (GeoTIFF, EPSG:2180, kompresja deflate).

### 7.5 `p05_shade.py`: cień zależny od położenia słońca

**Idea:** dla punktów próbkowanych co ~15 m wzdłuż każdej krawędzi, dla każdego binu słońca (16 azymutów × 8 wysokości) „idziemy" promieniem w stronę słońca. Punkt jest w cieniu, jeśli jakaś przeszkoda jest wyższa niż promień na tej odległości.

```
przeszkoda wysokości h w odległości d zacienia punkt  ⇔  h > 1.5 m + d · tan(elewacja)
```

```python
import numpy as np, rasterio, geopandas as gpd, shapely
from pipeline.common import PROC

AZ = np.arange(0, 360, 22.5)                         # 16 azymutów (od N, zgodnie z zegarem)
EL = np.array([5, 10, 15, 20, 30, 40, 50, 65])       # 8 elewacji [°]
STEP, MAXD, EYE = 2.0, 120.0, 1.5                    # krok [m], zasięg [m], wysokość głowy [m]
D = np.arange(STEP, MAXD + STEP, STEP, dtype=np.float32)

with rasterio.open(PROC / "heights_2m.tif") as src:
    H = src.read(1)
    x0, y0, res = src.transform.c, src.transform.f, src.transform.a

def sample(xs, ys):
    col = ((xs - x0) / res).astype(np.int32)
    row = ((y0 - ys) / res).astype(np.int32)
    ok = (row >= 0) & (row < H.shape[0]) & (col >= 0) & (col < H.shape[1])
    out = np.zeros(xs.shape, dtype=np.uint8)
    out[ok] = H[row[ok], col[ok]]
    return out

def shaded(px, py, az, el):
    dx, dy = np.sin(np.radians(az)), np.cos(np.radians(az))
    xs = px[:, None] + D[None, :] * dx              # (P, S)
    ys = py[:, None] + D[None, :] * dy
    need = EYE + D * np.tan(np.radians(el))         # (S,)
    return (sample(xs, ys) > need).any(axis=1)

edges = gpd.read_parquet(PROC / "edges.parquet")
# punkty co 15 m (shapely 2: wektorowo)
n_pts = np.maximum(2, (edges.length / 15).astype(int))
pts, owner = [], []
for eid, (geom, n) in enumerate(zip(edges.geometry, n_pts)):
    pts.append(shapely.line_interpolate_point(geom, np.linspace(0, 1, n), normalized=True))
    owner.append(np.full(n, eid))
pts = np.concatenate(pts); owner = np.concatenate(owner)
px, py = shapely.get_x(pts), shapely.get_y(pts)
under_canopy = sample(px, py) >= 3                   # punkt pod koroną drzewa/arkadą

counts = np.bincount(owner, minlength=len(edges))
shade = np.zeros((len(edges), len(AZ), len(EL)), dtype=np.uint8)
CH = 20_000
for i, az in enumerate(AZ):
    for j, el in enumerate(EL):
        s = np.empty(len(px), dtype=bool)
        for k in range(0, len(px), CH):
            s[k:k+CH] = shaded(px[k:k+CH], py[k:k+CH], az, el)
        s |= under_canopy
        frac = np.bincount(owner, weights=s, minlength=len(edges)) / counts
        shade[:, i, j] = np.round(frac * 255).astype(np.uint8)
np.save(PROC / "shade.npy", shade)                  # ~E×128 B ≈ 20 MB
```

Optymalizacje, jeśli będzie za wolno:
- liczyć cień dla **nieskierowanych** geometrii (u,v i v,u mają ten sam cień), co daje ~2× mniej pracy;
- pominąć `EL=65°` (w Krakowie słońce max ~63°);
- `multiprocessing.Pool` po azymutach.

### 7.6 `p06_rasters.py` + `p07_microclimate.py`: „Neural heuristic", wersja uczciwa

**Problem:** nie ma czujników temperatury na każdej ulicy. **Rozwiązanie:** etykieta = **anomalia temperatury powierzchni (LST)** z Landsata, czyli realny, mierzalny sygnał wysp ciepła. Model uczy się zależności *LST ← zieleń, zabudowa, wysokość, woda* i potem:

1. **wypełnia luki** (chmury, krawędzie scen),
2. **przenosi do rozdzielczości ulicy** (cechy z rastra 2 m i MSIP zamiast 30 m piksela),
3. umożliwia **symulację „co jeśli"** (dosadzenie drzew → spadek anomalii). To ładny feature pod Smart City.

```python
# p06_rasters.py: kompozyt letni LST (czerwiec–sierpień, 2022–2025, chmury < 10%)
import numpy as np, pystac_client, planetary_computer
from odc.stac import load
from pipeline.common import BBOX_WGS, CRS_METRIC, INTERIM

cat = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)
items = [it for it in cat.search(
    collections=["landsat-c2-l2"], bbox=BBOX_WGS, datetime="2022-06-01/2025-08-31",
    query={"eo:cloud_cover": {"lt": 10}, "platform": {"in": ["landsat-8", "landsat-9"]}},
).item_collection() if it.datetime.month in (6, 7, 8)]

# nazwy assetów: sprawdźcie items[0].assets.keys() (oczekiwane: lwir11, red, nir08, qa_pixel)
ds = load(items, bands=["lwir11", "red", "nir08", "qa_pixel"],
          crs=CRS_METRIC, resolution=30, bbox=BBOX_WGS, chunks={})
qa = ds.qa_pixel.astype("uint16")
clear = ((qa & (1 << 3)) == 0) & ((qa & (1 << 4)) == 0) & ((qa & (1 << 1)) == 0)  # cloud, shadow, dilated
lst_c = (ds.lwir11 * 0.00341802 + 149.0 - 273.15).where(clear)
lst = lst_c.median("time").compute()
lst_anom = lst - float(lst.median())
lst_anom.rio.to_raster(INTERIM / "lst_anom_30m.tif")     # wymaga rioxarray (zależność odc-stac)
```

```python
# p07_microclimate.py: model + uczciwa walidacja przestrzenna
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor           # do porównania na slajdzie
from sklearn.model_selection import GroupKFold, cross_val_score

FEATURES = ["ndvi", "tall_green_frac_60m", "green_frac_150m", "bld_frac_60m",
            "bld_h_mean_60m", "dist_water_m", "dist_major_road_m", "elev_m"]
# df: 1 wiersz = 1 piksel 30 m, cechy liczone z heights_2m.tif, MSIP, OSM
X, y = df[FEATURES], df["lst_anom"]
groups = (df.x // 1000).astype(int) * 10_000 + (df.y // 1000).astype(int)   # bloki 1 km

hgb = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31)
print("HGB R² (spatial CV):", cross_val_score(hgb, X, y, groups=groups, cv=GroupKFold(5), scoring="r2").mean())
hgb.fit(X, y)

# predykcja na punktach krawędzi (te same cechy liczone w otoczeniu punktu) → średnia per krawędź
# → data/processed/lst_anom_edge.npy  (E,) float32 [°C anomalii powierzchni]
```

**Na slajd:** R² w walidacji przestrzennej (bloki 1 km, bez przecieku), porównanie HGB vs MLP i mapa anomalii. Uczciwie zaznaczamy, że **LST to temperatura powierzchni, nie powietrza**. W modelu przeliczamy ją ostrożnie: ΔT_air ≈ k·ΔLST, `k ≈ 0.3` (założenie), skalowane natężeniem promieniowania.

### 7.7 `p08_edge_features.py`: cechy krawędzi do modelu smogu i wiatru

| Cecha | Jak | Po co |
|---|---|---|
| `f_pm`, `f_no2` | mnożnik lokalny zanieczyszczeń: przyrost przy drogach głównych (zanik wykładniczy z odległością, ~50 m), redukcja w głębi zieleni | smog na poziomie ulicy (8.3) |
| `wind_factor` | 0,5 kanion (H/W > 1), 0,7 pod drzewami, 0,9 otwarte, +0,1 w korytarzu przewietrzania | wiatr w UTCI |
| `W_cams` (E×9) | wagi biliniowe do siatki 3×3 punktów Open-Meteo | tło CAMS per krawędź |
| `W_idw` (E×9) | wagi IDW do 9 stacji GIOŚ | korekta stacjami |
| `name`, `highway` | z OSM | wyjaśnienia „Avoids: …" |

**Kalibracja `f_pm`/`f_no2` danymi:** stosunek stężeń stacji **komunikacyjnej** (Al. Krasińskiego, 400) do stacji **tła** (Bujaka, 401) z ostatnich 12 miesięcy (`archivalData`) daje empiryczny przyrost przy ruchliwej ulicy. Przypisujemy go pełnie do `primary/trunk`, 60% do `secondary`, 30% do `tertiary`, 0 do `residential`/`cycleway` z dala od arterii. Liczba z danych, a nie z sufitu, to dobry argument dla jury.

### 7.8 `p09_fuzzy_luts.py` i `p10_scenarios.py`

Opisane w sekcjach 9.4 i 8.5.

---

## 8. Model środowiskowy krawędzi (smog, upał, cień, UV)

Dla każdego zapytania i każdej krawędzi `e` liczymy wektorowo (numpy, ~150 tys. elementów):

### 8.1 Cień `s_e(t) ∈ [0,1]`

1. `pvlib.solarposition.get_solarposition(time, 50.06, 19.94)` → `apparent_elevation`, `azimuth`.
2. Jeśli elewacja ≤ 0 (noc), to `s_e = 1`.
3. Inaczej najbliższy bin azymutu + interpolacja liniowa między binami elewacji w `shade.npy`, `/255`. Dla elewacji < 5° bierzemy bin 5°.

### 8.2 Stres cieplny UTCI

```
T_a,e   = T_2m + k · ΔLST_e · min(1, SW/600)               # lokalna temp. powietrza
ΔTmrt   = SolarCal(DNI, elewacja)  → ΔTmrt_sun, ΔTmrt_shade (2 skalary na zapytanie)
Tmrt_e  = T_a,e + ΔTmrt_shade + (1 − s_e) · (ΔTmrt_sun − ΔTmrt_shade)
v_e     = clip(v_10m · wind_factor_e, 0.5, 17) [m/s]
UTCI_e  = utci(T_a,e, Tmrt_e, v_e, RH)
```

- `ΔTmrt` z modelu SolarCal w `pythermalcomfort` (`solar_gain`, parametry: elewacja słońca, DNI, `f_bes` = część ciała w słońcu: 1 w słońcu, 0 w cieniu). Sygnaturę trzeba zweryfikować w zainstalowanej wersji. Fallback: prosta aproksymacja liniowa od DNI.
- **Trik wydajnościowy:** UTCI to wielomian ~200 wyrazów. Kwantyzujemy (T_a co 0,5°C, ΔTmrt co 1°C, v co 0,5 m/s), liczymy UTCI tylko dla **unikalnych kombinacji** (`np.unique(..., return_inverse=True)`, zwykle < 1000) i rozkładamy z powrotem.

```python
from pythermalcomfort.models import utci

def utci_fast(ta, tmrt, v, rh):
    q = np.column_stack([np.round(ta * 2) / 2, np.round(tmrt - ta), np.round(v * 2) / 2])
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    res = utci(tdb=uniq[:, 0], tr=uniq[:, 0] + uniq[:, 1], v=uniq[:, 2], rh=rh, limit_inputs=False)
    vals = np.asarray(getattr(res, "utci", res), dtype=np.float32)
    return vals[inv.ravel()]
```

### 8.3 Zanieczyszczenia: fuzja CAMS + GIOŚ + ulica

```
CAMS_e       = W_cams @ cams_grid                         # tło z modelu (siatka 3×3 Open-Meteo)
r_s          = clip(GIOS_s / CAMS(x_s), 0.3, 3.0)         # korekta na stacjach
r_e          = W_idw @ r_s                                # interpolacja korekty (IDW)
C_e[pm2.5]   = CAMS_e · r_e · f_pm_e                      # + lokalny przyrost przy arteriach
C_e[no2]     = CAMS_e · r_e · f_no2_e
```

Jeśli dostępny jest Airly, jego czujniki dochodzą jako dodatkowe „stacje" do `r_s`.

**Indeks powietrza `A_e ∈ [0,6]`** (ciągła wersja EAQI): dla każdego zanieczyszczenia interpolujemy liniowo stężenie w pasmach indeksu, potem `A_e = max(PM2.5, PM10, NO2)`. Zasada „najgorszy decyduje" jest zgodna z EAQI.

```python
# UWAGA: EEA zrewidowała progi EAQI. Przed implementacją sprawdźcie aktualną tabelę:
# https://airindex.eea.europa.eu  (poniżej klasyczne pasma, wartość tymczasowa)
BANDS = {
    "pm25": [0, 10, 20, 25, 50, 75, 800],
    "pm10": [0, 20, 40, 50, 100, 150, 1200],
    "no2":  [0, 40, 90, 120, 230, 340, 1000],
}
def air_index(c: dict[str, np.ndarray], ve_ratio: float = 1.0) -> np.ndarray:
    sub = [np.interp(c[k] * ve_ratio, b, np.arange(7)) for k, b in BANDS.items()]
    return np.maximum.reduce(sub)
```

`ve_ratio` to stosunek wentylacji minutowej profilu do standardu. Sportowiec oddycha ~1,5–2× intensywniej, więc ta sama ulica jest dla niego „gorsza". To fizjologia, a nie arbitralna waga.

### 8.4 UV efektywne

```
UV_e = UV_index · (1 − 0.6 · s_e)       # cień usuwa składową bezpośrednią; rozproszone UV zostaje
```

Współczynnik 0,6 to założenie (drzewa/budynki redukują UV o ~50–75%), opisane na slajdzie.

### 8.5 Scenariusze (`p10_scenarios.py`)

Plik JSON per scenariusz: czas, pogoda (skalary), siatka 3×3 CAMS (PM2.5, PM10, NO2, UV), wartości stacji GIOŚ. Commitowany do repo, więc demo działa bez API.

| ID | Moment | Dane (zweryfikowane) |
|---|---|---|
| `heatwave_2025-07-03T14` | 3.07.2025, 14:00 | 34,5°C, RH 20%, wiatr 17,4 km/h, SW 862 W/m², DNI 853 W/m², chmury 0% |
| `smog_2025-01-20T17` | 20.01.2025, 17:00 (szczyt komunikacyjny) | CAMS PM10 161 µg/m³ (centrum), GIOŚ Krasińskiego 63,2 µg/m³. Szczyt wieczorny CAMS ~268–290 o 21–22:00, godzinę można przesunąć suwakiem |
| `live` | teraz | Open-Meteo + GIOŚ, odświeżane w tle |

### 8.6 Metryki dla użytkownika (raportowane, nie optymalizowane wprost)

| Metryka | Wzór |
|---|---|
| Czas | `Σ t_e`, `t_e = length_e / v_profil` |
| **Dawka wdychana PM2.5** [µg] | `Σ C_e · VE · t_e` |
| Udział cienia | `Σ t_e·s_e / Σ t_e` |
| Minuty w stresie cieplnym | `Σ t_e · [UTCI_e > 32]` |
| Średni dyskomfort | `Σ t_e·D_e / Σ t_e` (0–10) |

Parametry profili (przybliżone, z literatury, np. Int Panis i in. 2010. Przed slajdem zweryfikujcie i podajcie źródło):

| Profil | v [km/h] | VE [m³/h] | Uwagi |
|---|---|---|---|
| Standard | 15 | ~1,9 | |
| Asthma/Allergy | 14 | ~1,9 | niższe progi powietrza w fuzzy |
| Senior/Child | 12 | ~1,6 | niższe progi upału i UV |
| Athlete | 22 | ~3,2 | wyższa dawka, niższa waga dystansu |

---

## 9. Logika rozmyta: model dyskomfortu

### 9.1 Dlaczego fuzzy

- **Dyskomfort jest nieostry.** Ostre progi dają skoki i dziwne trasy, fuzzy daje płynne przejścia.
- **Wyjaśnialność.** Reguły czyta się po ludzku, więc slajd z regułami zrozumie każdy juror.
- **Personalizacja bez danych treningowych.** Profil = przesunięte zbiory i inne reguły.
- **Zakotwiczenie w normach:** UTCI (kategorie stresu cieplnego), EAQI (pasma jakości powietrza), skala UV WHO.

### 9.2 Zmienne i zbiory (profil Standard)

| Zmienna | Uniwersum | Zbiory (kotwice) |
|---|---|---|
| `heat` = UTCI [°C] | −30…50 | `cold` trap(−30,−30,0,9) · `comfortable` trap(0,9,22,26) · `warm` trap(22,26,30,32) · `hot` trap(28,32,36,38) · `very_hot` trap(36,38,50,50). Granice wg kategorii UTCI: 26 / 32 / 38 / 46 °C |
| `air` = ciągły EAQI | 0…6 | `good` trap(0,0,1,1.8) · `fair` tri(1,2,3) · `poor` trap(2.5,3.5,4.5,5) · `very_poor` trap(4.5,5.5,6,6) |
| `uv` = UV efektywne | 0…12 | `low` trap(0,0,2,3) · `moderate` tri(2,4,6) · `high` trap(5,6,7,8) · `very_high` trap(7,8.5,12,12). Skala WHO: 0–2 / 3–5 / 6–7 / 8–10 / 11+ |
| **`discomfort`** (wyjście) | 0…10 | `none` trap(0,0,1,2) · `low` tri(1,2.5,4) · `medium` tri(3,5,7) · `high` tri(6,7.5,9) · `extreme` trap(8,9,10,10) |

### 9.3 Reguły (Mamdani, defuzyfikacja centroidem)

> ⚠️ **Pułapka sprawdzona w teście: brak monotoniczności.** Pierwsza, „naiwna" wersja reguł (np. `air = fair → low` obok `heat = hot → high`) dawała absurdy: **gorsze powietrze obniżało dyskomfort nawet o 2,9 pkt**. Przy upale reguła „low" ściągała centroid w dół. Rozwiązanie: **reguły ze strażnikami**. Łagodniejsza konsekwencja odpala tylko wtedy, gdy *pozostałe* czynniki są co najwyżej tak samo łagodne. Po tej zmianie resztkowe spadki to ≤ 0,4 pkt w strefach przejściowych zbiorów. Usuwa je projekcja monotoniczna LUT (9.4). Jury lubi takie szczegóły: „sprawdziliśmy formalnie, że gorsze warunki nigdy nie poprawiają oceny".

Skróty strażników: `heat≤mild` = comfortable ∨ warm ∨ cold · `heat_mild` = warm ∨ cold · `air≤fair` = good ∨ fair · `uv_ok` = low ∨ moderate · `uv≤high` = low ∨ moderate ∨ high.

| # | JEŚLI | TO |
|---|---|---|
| R1 | air = very_poor ∨ heat = very_hot | extreme |
| R2 | air = poor ∧ (heat = hot ∨ uv = very_high) | extreme |
| R3 | heat = hot ∧ uv = very_high | extreme |
| R4 | heat = hot ∧ air≤fair ∧ uv≤high | high |
| R5 | air = poor ∧ heat≤mild ∧ uv≤high | high *(profil może podnieść)* |
| R6 | uv = very_high ∧ heat≤mild ∧ air≤fair | high |
| R7 | uv = high ∧ heat≤mild ∧ air≤fair | medium |
| R8 | heat_mild ∧ air = fair ∧ uv_ok | medium *(dwa łagodne czynniki naraz)* |
| R9 | heat_mild ∧ air = good ∧ uv_ok | low *(profil może podnieść)* |
| R10 | air = fair ∧ heat = comfortable ∧ uv_ok | low *(profil może podnieść)* |
| R11 | air = good ∧ heat = comfortable ∧ uv_ok | none |

**Zmierzone wartości (profil Standard, po projekcji):**

| UTCI [°C] | air (EAQI ciągły) | UV | Dyskomfort |
|---|---|---|---|
| 20 | 0,5 | 1 | **0,8** |
| 20 | 2,0 | 1 | 2,5 |
| 20 | 4,0 | 1 | 7,5 |
| 20 | 5,8 | 1 | 9,2 |
| 28 | 0,5 | 4 | 2,5 |
| 28 | 2,0 | 4 | 5,0 |
| 34 | 0,5 | 6 | 7,5 |
| 34 | 0,5 | 9 | 9,2 |
| 4 (zima) | 4,0 | 0 | 7,5 |

Wynik jest „schodkowy" (poziomy ≈ środków ciężkości konsekwencji: 0,8 / 2,5 / 5 / 7,5 / 9,2). Między schodkami wygładzają go nakładanie się zbiorów i interpolacja liniowa LUT. Gdyby routing za słabo rozróżniał odcinki w obrębie jednej klasy, można dodać do `D_e` mały składnik ciągły, np. `+0.05·air`.

**Modyfikacje profili (zmierzony efekt):**

| Profil | Zmiana | Efekt |
|---|---|---|
| Asthma/Allergy | kotwice `air` × 0,7; R10 → **medium**; R5 → **extreme** | UTCI 20, air 2,5: **9,2** vs 2,5 (Standard). Bardzo agresywne, więc do strojenia (np. R5 zostawić jako high) |
| Senior/Child | kotwice `heat` −3°C; kotwice `uv` × 0,8; R9 → **medium** | UTCI 28, air 0,5, UV 4: **6,2** vs 2,5 |
| Athlete | `ve_ratio ≈ 1,7` w indeksie powietrza (8.3); kotwice `heat` −2°C; mniejsza waga czasu w sweepie | wyższa „efektywna" dawka smogu |

### 9.4 Implementacja: skfuzzy offline → LUT → interpolacja online

`skfuzzy.control.ControlSystemSimulation` liczy pojedyncze wartości (rzędu ms na wywołanie). Dla 150 tys. krawędzi na zapytanie to minuty, więc **liczymy raz na siatce wejść i interpolujemy**.

```python
# app/fuzzy/model.py
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

HEAT_U = np.arange(-30, 50.01, 0.5)
AIR_U = np.arange(0, 6.001, 0.02)
UV_U = np.arange(0, 12.001, 0.05)
OUT_U = np.arange(0, 10.001, 0.05)

def build_system(p: dict) -> ctrl.ControlSystem:
    heat = ctrl.Antecedent(HEAT_U, "heat")
    air = ctrl.Antecedent(AIR_U, "air")
    uv = ctrl.Antecedent(UV_U, "uv")
    out = ctrl.Consequent(OUT_U, "discomfort", defuzzify_method="centroid")

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

    out["none"] = fuzz.trapmf(OUT_U, [0, 0, 1, 2])
    out["low"] = fuzz.trimf(OUT_U, [1, 2.5, 4])
    out["medium"] = fuzz.trimf(OUT_U, [3, 5, 7])
    out["high"] = fuzz.trimf(OUT_U, [6, 7.5, 9])
    out["extreme"] = fuzz.trapmf(OUT_U, [8, 9, 10, 10])

    # strażnicy: łagodna konsekwencja tylko gdy pozostałe czynniki też są łagodne (monotoniczność!)
    heat_ok = heat["comfortable"]
    heat_mild = heat["warm"] | heat["cold"]
    heat_le_mild = heat["comfortable"] | heat["warm"] | heat["cold"]
    air_le_fair = air["good"] | air["fair"]
    uv_ok = uv["low"] | uv["moderate"]
    uv_le_high = uv["low"] | uv["moderate"] | uv["high"]

    c = p["consequents"]  # profil może podnieść konsekwencje R5, R9, R10
    rules = [
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
    ]
    return ctrl.ControlSystem(rules)
```

```python
# app/fuzzy/profiles.py
PROFILES = {
    "standard": dict(heat_shift=0, air_scale=1.0, uv_scale=1.0, ve_ratio=1.0, speed_kmh=15, consequents={}),
    "asthma":   dict(heat_shift=0, air_scale=0.7, uv_scale=1.0, ve_ratio=1.0, speed_kmh=14,
                     consequents={"R10": "medium", "R5": "extreme"}),
    "senior":   dict(heat_shift=-3, air_scale=1.0, uv_scale=0.8, ve_ratio=0.85, speed_kmh=12,
                     consequents={"R9": "medium"}),
    "athlete":  dict(heat_shift=-2, air_scale=1.0, uv_scale=1.0, ve_ratio=1.7, speed_kmh=22, consequents={}),
}
```

> ✅ Ten kod (model + profile) został uruchomiony w teście ze skfuzzy 0.5.0: 0 luk w regułach na całej siatce, wszystkie 4 profile, zakres wyjścia 0,8–9,2.

```python
# pipeline/p09_fuzzy_luts.py
import numpy as np
from skfuzzy import control as ctrl
from app.fuzzy.model import build_system
from app.fuzzy.profiles import PROFILES
from pipeline.common import PROC

G_HEAT = np.arange(-30, 50.01, 2.0)   # 41
G_AIR = np.arange(0, 6.001, 0.2)      # 31
G_UV = np.arange(0, 12.001, 1.0)      # 13   → 16 523 komórek / profil

for name, p in PROFILES.items():
    sim = ctrl.ControlSystemSimulation(build_system(p), cache=False)
    lut = np.zeros((len(G_HEAT), len(G_AIR), len(G_UV)), dtype=np.float32)
    for i, h in enumerate(G_HEAT):
        for j, a in enumerate(G_AIR):
            for k, u in enumerate(G_UV):
                sim.input["heat"], sim.input["air"], sim.input["uv"] = h, a, u
                try:
                    sim.compute()
                    lut[i, j, k] = sim.output["discomfort"]
                except (ValueError, KeyError):   # żadna reguła nie odpaliła → luka w regułach
                    lut[i, j, k] = np.nan
    assert not np.isnan(lut).any(), f"{name}: niepokryte kombinacje wejść; uzupełnij reguły"
    np.save(PROC / f"lut_{name}.npy", monotone(lut, G_HEAT, comfort_hi=22 + p["heat_shift"]))
np.savez(PROC / "lut_grid.npz", heat=G_HEAT, air=G_AIR, uv=G_UV)


def monotone(lut, heat_grid, comfort_hi=22.0):
    """Projekcja monotoniczna (siatka bezpieczeństwa): gorsze warunki nigdy nie obniżają dyskomfortu.
    Zmierzone: koryguje ≤ 0.4 pkt w 6–15% komórek (zależnie od profilu)."""
    out = np.maximum.accumulate(lut, axis=1)                    # air ↑
    out = np.maximum.accumulate(out, axis=2)                    # uv ↑
    hot = heat_grid >= comfort_hi
    out[hot] = np.maximum.accumulate(out[hot], axis=0)          # upał ↑
    cold = ~hot
    out[cold] = np.maximum.accumulate(out[cold][::-1], axis=0)[::-1]   # mróz ↓
    return out
```

(W prawdziwym pliku `monotone` zdefiniujcie nad pętlą.)

**Czas (zmierzony):** skfuzzy 0.5.0 potrzebuje **~11–15 ms na komórkę**, więc ~16,5 tys. komórek to **~3–4 min na profil**, ~15 min dla 4 profili na 1 rdzeniu. Rozwiązanie: `joblib.Parallel(n_jobs=-1)` po osi `heat` (każdy worker ma własny `ControlSystemSimulation`). Na 8 rdzeniach daje to ~2 min dla wszystkich profili. Podczas iteracji nad regułami używajcie grubszej siatki (np. 21×13×7), a docelową liczcie raz.

```python
# online (app/services/exposure.py)
from scipy.interpolate import RegularGridInterpolator
interp = RegularGridInterpolator((g["heat"], g["air"], g["uv"]), lut, bounds_error=False, fill_value=None)
D = interp(np.column_stack([np.clip(utci, -30, 50), np.clip(air, 0, 6), np.clip(uv, 0, 12)])) / 10.0
```

### 9.5 Wyjaśnienia („dlaczego ta trasa")

Zamiast wyciągać aktywacje reguł z wnętrza skfuzzy (kruche API) liczymy **dominujący czynnik** krawędzi z tych samych wejść:

```python
sev = np.column_stack([
    np.clip((utci - 26) / 12, 0, 1),   # heat
    np.clip((air - 1) / 4, 0, 1),      # air
    np.clip((uv - 3) / 6, 0, 1),       # uv
])
reason = np.where(sev.max(1) < 0.15, -1, sev.argmax(1))   # -1 = OK, 0 heat, 1 air, 2 uv
```

`explain.py` porównuje trasę z *Fastest*: odcinki *Fastest* z wysokim `D_e`, których nowa trasa unika, grupuje po `name` i zwraca top 3: „Avoids: Al. Krasińskiego (high PM, no shade), ul. Dietla (heat stress)".

---

## 10. Silnik tras: Dijkstra-sweep + NSGA-II „Route Morphing"

### 10.1 Sformułowanie

Dla trasy `P` (ciąg krawędzi przez punkty pośrednie) minimalizujemy dwa cele:

```
f1(P) = Σ t_e                 (czas)
f2(P) = Σ t_e · D_e           (ekspozycja: dyskomfort × czas przebywania)
```

Dawkę PM2.5, cień i minuty stresu raportujemy (8.6), ale nie optymalizujemy osobno, bo są skorelowane z `f2`. Dwa cele dają czytelny wykres 2D.

> Uwaga terminologiczna: to **nie jest Orienteering Problem** (OP = wybór podzbioru punktów przy limicie budżetu). Mamy *wielokryterialne wyznaczanie trasy przez zadane punkty*, z opcjonalną optymalizacją kolejności (wariant TSP-path na ≤ 7 punktach).

### 10.2 Graf w pamięci (`services/graph.py`)

```python
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

class NoRoute(Exception):
    pass

class Graph:
    def __init__(self, z):
        self.indptr, self.indices, self.perm = z["indptr"], z["indices"], z["perm"]
        self.N = len(self.indptr) - 1
        self.xy = np.column_stack([z["x"], z["y"]])
        self.u, self.v = z["u"], z["v"]
        self.kd = cKDTree(self.xy)

    def snap(self, xy: np.ndarray) -> np.ndarray:
        return self.kd.query(xy)[1]

    def corridor(self, way_xy: np.ndarray, detour: float = 1.5, pad_m: float = 1500) -> "SubGraph":
        """Węzły w elipsach wokół kolejnych odcinków A→B (ogniska = punkty)."""
        keep = np.zeros(self.N, dtype=bool)
        for a, b in zip(way_xy[:-1], way_xy[1:]):
            d_ab = np.hypot(*(b - a))
            s = np.hypot(*(self.xy - a).T) + np.hypot(*(self.xy - b).T)
            keep |= s <= detour * d_ab + pad_m
        return SubGraph(self, np.flatnonzero(keep))

class SubGraph:
    def __init__(self, g: Graph, nodes: np.ndarray):
        self.g, self.nodes = g, nodes
        self.local = -np.ones(g.N, dtype=np.int64)
        self.local[nodes] = np.arange(len(nodes))
        base = sp.csr_matrix((g.perm + 1, g.indices, g.indptr), shape=(g.N, g.N))
        sub = base[nodes][:, nodes].tocsr()
        self.indptr, self.indices = sub.indptr, sub.indices
        self.perm = (sub.data - 1).astype(np.int64)    # slot → globalny eid
        self.n = len(nodes)

    def matrix(self, w_edge: np.ndarray) -> sp.csr_matrix:
        return sp.csr_matrix((w_edge[self.perm], self.indices, self.indptr), shape=(self.n, self.n))

    def edge_id(self, a: int, b: int) -> int:
        lo, hi = self.indptr[a], self.indptr[a + 1]
        k = np.flatnonzero(self.indices[lo:hi] == b)[0]
        return int(self.perm[lo + k])

    def shortest(self, w_edge, sources):
        return dijkstra(self.matrix(w_edge), directed=True, indices=sources, return_predecessors=True)

    def path_edges(self, pred_row, s: int, t: int) -> list[int]:
        seq = [t]
        while seq[-1] != s:
            p = pred_row[seq[-1]]
            if p < 0:
                raise NoRoute
            seq.append(p)
        seq.reverse()
        return [self.edge_id(a, b) for a, b in zip(seq[:-1], seq[1:])]
```

- Wagi muszą być **> 0**, więc zawsze dodajemy `+1e-3`.
- Punkty użytkownika snapujemy do węzłów **w dużym grafie**, a potem mapujemy na lokalne id korytarza (`sub.local[...]`). Jeśli punkt wypadnie poza korytarzem, poszerzamy `pad_m`.
- Jeśli korytarz jest za mały (brak trasy), ponawiamy z `detour=2.5`, a w ostateczności używamy pełnego grafu.

### 10.3 Etap 1 (MVP): sweep wag → front Pareto (`router_fast.py`)

```
w_e(λ) = t_e · ((1 − λ) + λ · κ · D_e) + 1e-3,     κ = 1 / mean(D_e)   (normalizacja skali)
λ ∈ {0, .1, .2, .35, .5, .65, .8, .9, 1}
```

```python
import itertools
import numpy as np

LAMBDAS = np.array([0, .1, .2, .35, .5, .65, .8, .9, 1.0])

def evaluate(eids, t, D):
    e = np.asarray(eids)
    return float(t[e].sum()), float((t[e] * D[e]).sum())

def best_order(cost_mat, fixed_ends=True):
    k = cost_mat.shape[0]
    mids = range(1, k - 1)
    best, best_c = None, np.inf
    for perm in itertools.permutations(mids):              # ≤ 5! = 120 przy 7 punktach
        order = (0, *perm, k - 1)
        c = sum(cost_mat[a, b] for a, b in zip(order[:-1], order[1:]))
        if c < best_c:
            best, best_c = order, c
    return list(best)

def weights(t, D, lam, kappa):
    return t * ((1 - lam) + lam * kappa * D) + 1e-3

def sweep(sub, t, D, way_local, optimize_order=False):
    kappa = 1.0 / max(D.mean(), 1e-6)
    order = list(range(len(way_local)))
    if optimize_order:                                       # kolejność ustalamy raz, dla λ = 0.5
        dist, _ = sub.shortest(weights(t, D, 0.5, kappa), way_local)
        order = best_order(dist[:, way_local])
    srcs = way_local if optimize_order else way_local[:-1]   # wiersz pred[a] = źródło nr a (w obu wariantach)

    cands = {}
    for lam in LAMBDAS:
        _, pred = sub.shortest(weights(t, D, lam, kappa), srcs)
        legs = []
        for a, b in zip(order[:-1], order[1:]):
            legs += sub.path_edges(pred[a], way_local[a], way_local[b])
        key = tuple(legs)
        if key not in cands:
            cands[key] = (lam, *evaluate(legs, t, D))
    return order, [(list(k), *v) for k, v in cands.items()]  # (eids, λ, f1, f2)
```

**Wybór 3 tras z frontu** (`pareto.py`):

```python
def nondominated(F: np.ndarray) -> np.ndarray:
    """Indeksy punktów niezdominowanych (minimalizacja, 2 cele)."""
    idx = np.lexsort((F[:, 1], F[:, 0]))
    keep, best = [], np.inf
    for i in idx:
        if F[i, 1] < best - 1e-9:
            keep.append(i); best = F[i, 1]
    return np.array(keep)

def knee(F: np.ndarray) -> int:
    """Punkt najdalej od prostej łączącej skrajne rozwiązania (po normalizacji)."""
    Z = (F - F.min(0)) / np.maximum(np.ptp(F, axis=0), 1e-9)   # ndarray.ptp usunięte w NumPy 2
    a, b = Z[Z[:, 0].argmin()], Z[Z[:, 0].argmax()]
    n = np.array([b[1] - a[1], a[0] - b[0]])
    return int(np.abs((Z - a) @ n).argmax())

def lower_hull_mask(F: np.ndarray) -> np.ndarray:
    """True dla punktów na dolnej otoczce wypukłej (= osiągalne sumą ważoną)."""
    idx = np.lexsort((F[:, 1], F[:, 0])); hull = []
    for i in idx:
        while len(hull) >= 2:
            o, a = F[hull[-2]], F[hull[-1]]
            if (a[0]-o[0])*(F[i,1]-o[1]) - (a[1]-o[1])*(F[i,0]-o[0]) <= 0:
                hull.pop()
            else:
                break
        hull.append(i)
    m = np.zeros(len(F), bool); m[hull] = True
    return m

def hypervolume_2d(F: np.ndarray, ref: np.ndarray) -> float:
    P = F[nondominated(F)]; P = P[np.argsort(P[:, 0])]
    hv, prev_y = 0.0, ref[1]
    for x, y in P:
        hv += (ref[0] - x) * (prev_y - y); prev_y = y
    return hv
```

Trasy: **Fastest** = min `f1`, **Cleanest** = min `f2`, **Balanced** = `knee`. Duplikaty odrzucamy, gdy podobieństwo Jaccarda zbiorów krawędzi > 0,9.

### 10.4 Etap 2: NSGA-II z „Route Morphing" (`router_evo.py`)

**Uzasadnienie (na slajd):** suma ważona (sweep) znajduje **wyłącznie punkty na wypukłej otoczce frontu** (*supported solutions*). Rozwiązania z „wklęsłych" fragmentów frontu są dla niej niewidoczne dla *każdego* λ. NSGA-II przeszukuje przestrzeń bezpośrednio z sortowaniem niezdominowanym i nie ma tego ograniczenia. Na wykresie oznaczamy ★ rozwiązania leżące **powyżej dolnej otoczki** (`~lower_hull_mask`), czyli takie, których sweep z definicji nie znajdzie.

**Genotyp:** nie lista ulic (losowe mutacje dawałyby nieciągłe trasy), tylko **pole preferencji przestrzennych**:

```
genom = [λ, g_1, …, g_C]       λ ∈ [0,1],  g_c ∈ [−1.5, 1.5]   (log-mnożnik dla komórki c)
komórki: siatka 400 m × 400 m pokrywająca korytarz (zwykle 40–150 genów)
```

**Dekoder (genotyp → trasa):**

```
w_e = t_e · ((1 − λ) + λ · κ · D_e · exp(g_{cell(e)})) + 1e-3   →   Dijkstra   →   trasa P
fitness(P) = (f1(P), f2(P))       ← liczone na PRAWDZIWYCH t_e, D_e, bez mnożników
```

Mnożniki „wyginają" trasę lokalnie (np. „w tej okolicy mocniej unikaj dyskomfortu"), ale ocena jest zawsze uczciwa.

**Mutacja Route Morphing (operator autorski):** gaussowski „bąbel" zmiany preferencji wokół losowej komórki. Mutacja jest skorelowana przestrzennie, więc trasa zmienia się płynnie w jednej okolicy, a nie chaotycznie.

```python
import random, time, copy
import numpy as np
from deap import base, creator, tools

if not hasattr(creator, "FitMin2"):
    creator.create("FitMin2", base.Fitness, weights=(-1.0, -1.0))
    creator.create("Ind", list, fitness=creator.FitMin2)

G_LO, G_HI = -1.5, 1.5

def mut_morph(ind, cells_xy, sigma=0.6, radius=600.0, p_lam=0.3):
    c = random.randrange(len(cells_xy))
    d = np.hypot(*(cells_xy - cells_xy[c]).T)
    bump = random.gauss(0.0, sigma) * np.exp(-(d / radius) ** 2)
    ind[1:] = np.clip(np.asarray(ind[1:]) + bump, G_LO, G_HI).tolist()
    if random.random() < p_lam:
        ind[0] = float(np.clip(ind[0] + random.gauss(0, 0.15), 0, 1))
    return (ind,)

def run_nsga2(sub, t, D, cell_of_edge, cells_xy, way_local, seeds, budget_s=3.0,
              pop_size=40, max_gen=40, on_generation=None):
    # way_local: punkty JUŻ w kolejności z trybu fast (way_local[order]);
    # cell_of_edge: (E,) indeks komórki siatki dla każdej krawędzi (spoza korytarza: dowolna)
    C = len(cells_xy)
    kappa = 1.0 / max(D.mean(), 1e-6)
    low, up = [0.0] + [G_LO] * C, [1.0] + [G_HI] * C

    def decode(ind):
        g = np.exp(np.asarray(ind[1:]))[cell_of_edge]
        w = t * ((1 - ind[0]) + ind[0] * kappa * D * g) + 1e-3
        _, pred = sub.shortest(w, way_local[:-1])
        eids = []
        for i in range(len(way_local) - 1):
            eids += sub.path_edges(pred[i], way_local[i], way_local[i + 1])
        return eids

    def evaluate(ind):
        ind.eids = decode(ind)
        e = np.asarray(ind.eids)
        return float(t[e].sum()), float((t[e] * D[e]).sum())

    tb = base.Toolbox()
    tb.register("mate", tools.cxSimulatedBinaryBounded, eta=15.0, low=low, up=up)
    tb.register("mutate", mut_morph, cells_xy=cells_xy)
    tb.register("select", tools.selNSGA2)

    # seeding: rozwiązania ze sweepu (g = 0) + losowe → front EA nigdy nie jest gorszy od sweepu
    pop = [creator.Ind([lam] + [0.0] * C) for lam in seeds]
    while len(pop) < pop_size:
        pop.append(creator.Ind([random.random()] + np.random.uniform(-0.7, 0.7, C).tolist()))
    for ind in pop:
        ind.fitness.values = evaluate(ind)
    pop = tb.select(pop, pop_size)                       # nadaje crowding_dist

    deadline = time.perf_counter() + budget_s
    for gen in range(max_gen):
        if time.perf_counter() > deadline:
            break
        off = [copy.deepcopy(i) for i in tools.selTournamentDCD(pop, pop_size)]  # pop_size % 4 == 0
        for a, b in zip(off[::2], off[1::2]):
            if random.random() < 0.9:
                tb.mate(a, b)
            tb.mutate(a); tb.mutate(b)
            del a.fitness.values, b.fitness.values
        for ind in off:
            if not ind.fitness.valid:
                ind.fitness.values = evaluate(ind)
        pop = tb.select(pop + off, pop_size)
        if on_generation:
            on_generation(gen, pop)                       # → streaming frontu do UI
    return pop
```

**Wydajność NSGA-II:**

| Dźwignia | Efekt |
|---|---|
| Korytarz zamiast całego grafu | Dijkstra ~2–3 ms zamiast ~15–30 ms |
| Budżet czasowy (*anytime*) | zawsze zwraca najlepszy front w zadanym czasie |
| Seeding ze sweepu | od 1. generacji front ≥ sweep (elitaryzm NSGA-II) |
| `pop_size=40`, ≤ 40 generacji | ~800–1600 ewaluacji w 3–5 s |
| (opcjonalnie) cache trasy po genomie zaokrąglonym do 0,1 | mniej powtórnych Dijkstr |

**Metryka sukcesu na slajd:** hypervolume frontu NSGA-II vs sweep (ten sam punkt odniesienia) oraz liczba ★ (rozwiązań nieosiągalnych dla sumy ważonej), uśrednione na 30 losowych zapytaniach (`scripts/bench.py --evo`). **Raportujemy uczciwie, nawet jeśli zysk jest mały.** „W X% zapytań EA znalazł trasy niedostępne dla Dijkstry" to i tak mocny wynik.

---

## 11. Backend: FastAPI

### 11.1 Endpointy

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/health` | status + wersja artefaktów + wiek danych live |
| GET | `/api/profiles` | lista profili z opisami (do UI) |
| GET | `/api/scenarios` | lista scenariuszy (`live`, `heatwave_…`, `smog_…`) |
| GET | `/api/conditions?scenario=&at=` | warunki (temp, UV, PM tło/skorygowane, stacje GIOŚ) do stopki UI |
| POST | `/api/routes` | **główny**: `mode=fast` (sweep) lub `deep` (NSGA-II, odpowiedź końcowa) |
| POST | `/api/routes/stream` | `deep` ze streamingiem NDJSON: kolejne generacje frontu, na końcu wynik |
| GET | `/api/layers/edges?bbox=&metric=&scenario=&profile=&at=` | wartości per krawędź w widoku mapy (discomfort/shade/heat/air) do nakładek |
| GET | `/docs` | Swagger (automatycznie) |

### 11.2 Schematy (`app/schemas.py`)

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

Profile = Literal["standard", "asthma", "senior", "athlete"]

class LatLon(BaseModel):
    lat: float = Field(ge=49.95, le=50.15)
    lon: float = Field(ge=19.75, le=20.25)

class RouteRequest(BaseModel):
    waypoints: list[LatLon] = Field(min_length=2, max_length=7)
    profile: Profile = "standard"
    scenario: str = "live"
    depart_at: datetime | None = None          # None = teraz / czas scenariusza
    optimize_order: bool = False
    mode: Literal["fast", "deep"] = "fast"
    time_budget_s: float = Field(3.0, ge=0.5, le=10.0)

class RouteMetrics(BaseModel):
    distance_m: float
    time_min: float
    discomfort_avg: float                      # 0–10
    pm25_dose_ug: float
    shade_pct: float
    heat_stress_min: float

class Segment(BaseModel):
    coords_from: int                           # indeks w geometrii
    coords_to: int
    discomfort: float
    reason: Literal["ok", "heat", "air", "uv"]

class Route(BaseModel):
    id: Literal["fastest", "balanced", "cleanest"]
    label: str
    geometry: dict                             # GeoJSON LineString
    metrics: RouteMetrics
    vs_fastest: dict[str, float]               # np. {"time_pct": +12.0, "pm25_dose_pct": -38.0}
    avoids: list[str]                          # ["Al. Krasińskiego (high PM, no shade)", …]
    segments: list[Segment]

class FrontPoint(BaseModel):
    time_min: float
    exposure: float
    source: Literal["sweep", "evo"]
    supported: bool                            # False = ★ (poza otoczką wypukłą)
    route_id: str | None = None

class RouteResponse(BaseModel):
    order: list[int]
    routes: list[Route]
    front: list[FrontPoint]
    conditions: dict
    timing_ms: dict[str, float]
```

### 11.3 Szkielet aplikacji (`app/main.py`)

```python
import asyncio, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import orjson

from app.config import settings
from app.schemas import RouteRequest, RouteResponse
from app.state import Engine
from app.services.conditions import ConditionsService
from app.services.graph import NoRoute

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = Engine.load(settings.data_dir)            # graf, cień, LUT-y, cechy: raz, do RAM
    app.state.cond = ConditionsService(settings)
    await app.state.cond.refresh()                               # pierwsze pobranie (fallback: ostatni plik)
    task = asyncio.create_task(app.state.cond.refresh_loop())
    app.state.engine.warmup(app.state.cond)                      # 1 przykładowe zapytanie = rozgrzane cache
    yield
    task.cancel()

app = FastAPI(title="AirRoute Kraków API", version="0.1.0", lifespan=lifespan)

@app.get("/api/health")
def health():
    return {"ok": True, "artifacts": app.state.engine.meta, "live_age_s": app.state.cond.age_s()}

@app.post("/api/routes", response_model=RouteResponse)
def routes(req: RouteRequest):                                   # sync def → threadpool, nie blokuje event loop
    t0 = time.perf_counter()
    try:
        cond = app.state.cond.get(req.scenario, req.depart_at)
        return app.state.engine.route(req, cond, t0=t0)
    except NoRoute:
        raise HTTPException(422, "No route between given points (try moving a waypoint).")

@app.post("/api/routes/stream")
def routes_stream(req: RouteRequest):
    cond = app.state.cond.get(req.scenario, req.depart_at)
    def gen():
        for event in app.state.engine.route_deep_iter(req, cond):   # yield {"type":"gen",...} … {"type":"result",...}
            yield orjson.dumps(event) + b"\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")

# na końcu: statyczny frontend (trasy /api/* mają pierwszeństwo, bo są zarejestrowane wcześniej)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
```

### 11.4 `ConditionsService`

- **Live:** co `CONDITIONS_REFRESH_MIN` asynchronicznie (`httpx.AsyncClient`, `asyncio.gather`):
  1. Open-Meteo forecast (1 punkt: pogoda),
  2. Open-Meteo AQ (siatka 3×3: PM2.5/PM10/NO2/UV, prognoza 48 h),
  3. GIOŚ `data/getData` dla PM10/PM2.5/NO2 na stacjach (rozłożone w czasie pod limity).
- Wynik zapisujemy też do `data/processed/last_live.json`. Jeśli API nie odpowiada, bierzemy ostatni plik, a UI pokazuje „data age: 2 h".
- **`depart_at`** wybiera godzinę z prognozy (live) albo przesuwa czas w scenariuszu. Wpływa na słońce (cień) i godzinowe wartości.
- **Scenariusze** to JSON-y z `scenarios/`, ładowane przy starcie.

### 11.5 `Engine.route` (`app/state.py`, przepływ)

```
1. cache_key = (scenario, hour(depart_at), profile)
   t_e, D_e, aux = exposure.compute(...)          # LRU cache (maxsize ~32)
2. xy = to_metric(waypoints);  snap → węzły globalne
3. sub = graph.corridor(xy);   way_local = sub.local[snapped]
4. order, cands = router_fast.sweep(sub, t_e, D_e, way_local, optimize_order)
5. if mode == "deep": pop = router_evo.run_nsga2(..., seeds=[λ z cands], budget_s)
6. F = [(f1, f2)] → nondominated → fastest / knee / cleanest
7. explain: metryki (8.6), vs_fastest, avoids, segmenty (sklejone kolejne krawędzie o tym samym reason)
8. geometria: sklejenie edge_coords[offs[e]:offs[e+1]] (bez duplikatów na łączeniach)
9. timing_ms = {snap, costs, search, explain, total}
```

---

## 12. Frontend: HTML + CSS + vanilla JS + Leaflet

### 12.1 Zasady

- **Zero buildu:** 3 pliki statyczne, biblioteki z CDN: [Leaflet 1.9.4](https://leafletjs.com) i [Chart.js 4](https://www.chartjs.org).
- Podkład mapy: **CARTO Positron** (jasny, kolorowe trasy dobrze kontrastują) z atrybucją „© OpenStreetMap contributors © CARTO". Alternatywa: standardowe kafle OSM (zgodnie z [tile usage policy](https://operations.osmfoundation.org/policies/tiles/), demo o małym ruchu jest OK).
- `preferCanvas: true` w Leaflet, żeby nakładki z tysiącami odcinków działały płynnie.
- Responsywność: na wąskim ekranie sidebar staje się dolnym panelem (`@media (max-width: 800px)`).

### 12.2 Układ (wireframe)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ 🌿 AirRoute Kraków   Scenario [Live ▾]  Profile [Senior ▾]  Depart [──●── 14:00]   │
├──────────────────────┬───────────────────────────────────────────────────────────┤
│ WAYPOINTS            │                                                           │
│  A  Rynek Główny  ✕  │                                                           │
│  B  AGH           ✕  │                    M A P   (Leaflet)                      │
│  C  Bulwary       ✕  │                                                           │
│  (click map to add)  │     ━━ Fastest (grey)                                     │
│  ☐ Optimize order    │     ━━ Balanced (violet)                                  │
│ [ Find routes ]      │     ━━ Cleanest (green)   ●A ●B ●C (draggable)            │
│ [ Deep search ✨ ]   │                                                           │
├──────────────────────┤                                    Layers ☐ Discomfort    │
│ ● CLEANEST           │                                           ☐ Shade now     │
│ 7.9 km · 32 min      │                                           ☐ Greenery      │
│ +7 min vs fastest    │                                                           │
│ PM2.5 dose  −41%     │                                                           │
│ Shade 71% · Heat 2m  │                                                           │
│ Avoids: Al. Mickie-  │                                                           │
│ wicza (heat, no shade)│                                                          │
│ ● BALANCED  …        │                                                           │
│ ● FASTEST   …        │                                                           │
├──────────────────────┤                                                           │
│ PARETO FRONT         │                                                           │
│  exposure            │                                                           │
│   │•                 │                                                           │
│   │  •  ★            │                                                           │
│   │      • ★ •       │                                                           │
│   └──────────── time │                                                           │
├──────────────────────┴───────────────────────────────────────────────────────────┤
│ Now: 34.5°C · UTCI 38 · UV 8 · PM10 63 µg/m³ (GIOŚ-corrected) · computed in 412 ms │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Interakcje:**

- Klik na mapie dodaje punkt (A, B, C…), marker można przeciągać (`draggable`), ✕ usuwa punkt.
- Klik w kartę podświetla trasę (pozostałe półprzezroczyste) i koloruje jej odcinki wg `discomfort` (zielony → czerwony). Najechanie na odcinek pokazuje tooltip z powodem.
- Suwak „Depart" (co 30 min) wysyła ponowne zapytanie z debounce 300 ms. Animacja zmiany cienia to moment „wow".
- „Deep search" czyta `fetch` + `ReadableStream` (NDJSON) i dopisuje punkty na wykresie co generację. Punkty ★ dostają inny kolor.
- Stopka pokazuje warunki i **czas obliczeń** z `timing_ms.total`.

### 12.3 `index.html` (szkielet)

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AirRoute Kraków</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="topbar">
    <h1>🌿 AirRoute Kraków</h1>
    <label>Scenario <select id="scenario"></select></label>
    <label>Profile <select id="profile"></select></label>
    <label>Depart <input id="depart" type="range" min="0" max="47" step="1" /><output id="departOut"></output></label>
  </header>
  <main class="layout">
    <aside class="sidebar">
      <section><h2>Waypoints</h2><ol id="waypoints"></ol>
        <label><input type="checkbox" id="optimize" /> Optimize order</label>
        <div class="buttons">
          <button id="findBtn" class="primary">Find routes</button>
          <button id="deepBtn">Deep search ✨</button>
        </div>
      </section>
      <section id="cards"></section>
      <section><h2>Pareto front</h2><canvas id="pareto" height="220"></canvas></section>
    </aside>
    <div id="map"></div>
  </main>
  <footer id="status">Click the map to add a start point.</footer>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <script src="app.js"></script>
</body>
</html>
```

### 12.4 `app.js` (rdzeń, ~150 linii w finalnej wersji)

```js
const API = "/api";
const COLORS = { fastest: "#6b7280", balanced: "#7c3aed", cleanest: "#16a34a" };
const map = L.map("map", { preferCanvas: true }).setView([50.0614, 19.9366], 13);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap contributors &copy; CARTO", maxZoom: 19,
}).addTo(map);

const state = { waypoints: [], markers: [], routeLayers: {}, chart: null };

map.on("click", (e) => addWaypoint(e.latlng));

function addWaypoint(latlng) {
  if (state.waypoints.length >= 7) return;
  const label = String.fromCharCode(65 + state.waypoints.length);
  const m = L.marker(latlng, { draggable: true, title: label }).addTo(map).bindTooltip(label, { permanent: true });
  m.on("dragend", () => { state.waypoints[state.markers.indexOf(m)] = m.getLatLng(); findRoutes(); });
  state.waypoints.push(latlng); state.markers.push(m);
  renderWaypoints();
  if (state.waypoints.length >= 2) findRoutes();
}

function requestBody(mode) {
  return {
    waypoints: state.waypoints.map((p) => ({ lat: p.lat, lon: p.lng })),
    profile: document.getElementById("profile").value,
    scenario: document.getElementById("scenario").value,
    depart_at: departIso(),
    optimize_order: document.getElementById("optimize").checked,
    mode,
  };
}

async function findRoutes() {
  setStatus("Computing…");
  const res = await fetch(`${API}/routes`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody("fast")),
  });
  if (!res.ok) return setStatus((await res.json()).detail ?? "Error");
  const data = await res.json();
  drawRoutes(data.routes); renderCards(data.routes); renderPareto(data.front);
  setStatus(conditionsLine(data.conditions) + ` · computed in ${Math.round(data.timing_ms.total)} ms`);
}

async function deepSearch() {
  const res = await fetch(`${API}/routes/stream`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody("deep")),
  });
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const ev = JSON.parse(buf.slice(0, nl)); buf = buf.slice(nl + 1);
      if (ev.type === "gen") { renderPareto(ev.front); setStatus(`Evolving… generation ${ev.gen}`); }
      if (ev.type === "result") { drawRoutes(ev.routes); renderCards(ev.routes); renderPareto(ev.front); }
    }
  }
}

function drawRoutes(routes) {
  Object.values(state.routeLayers).forEach((l) => map.removeLayer(l));
  state.routeLayers = {};
  for (const r of [...routes].reverse()) {           // cleanest na wierzchu
    state.routeLayers[r.id] = L.geoJSON(r.geometry, { style: { color: COLORS[r.id], weight: 6, opacity: 0.85 } })
      .bindTooltip(r.label).addTo(map);
  }
  const all = L.featureGroup(Object.values(state.routeLayers)); map.fitBounds(all.getBounds(), { padding: [40, 40] });
}

// renderCards, renderPareto (Chart.js scatter: sweep szare, evo pomarańczowe, ★ supported=false),
// renderWaypoints, departIso, conditionsLine, setStatus: proste funkcje DOM
document.getElementById("findBtn").onclick = findRoutes;
document.getElementById("deepBtn").onclick = deepSearch;
```

### 12.5 Design: wskazówki (Design = 20% oceny)

- Jedna paleta: szary / fiolet / zieleń dla tras, czerwono-zielona skala dyskomfortu (dla daltonistów dodatkowo grubość linii).
- Liczby w kartach w formie **porównań** („−41% PM2.5 for +7 min"), a nie surowe wartości.
- Font systemowy, duże przyciski, mało tekstu. Ikony emoji wystarczą.
- Pusty stan („Click the map to add a start point") i stany błędów (brak trasy, dane offline).
- Zrzuty ekranu do PDF robimy w 1920×1080 na scenariuszu *Heatwave* (najbardziej kolorowym).

---

## 13. Testy i wydajność

### 13.1 Testy (`pytest`)

| Test | Co sprawdza |
|---|---|
| `test_fuzzy.py::test_monotonic_air` | więcej zanieczyszczeń → dyskomfort **nie maleje** (na siatce LUT, każdy profil) |
| `test_fuzzy.py::test_monotonic_heat_above_comfort` | dla UTCI > 26 rosnący upał → dyskomfort nie maleje |
| `test_fuzzy.py::test_profiles_order` | Asthma ≥ Standard dla złego powietrza; Senior ≥ Standard dla upału |
| `test_fuzzy.py::test_lut_complete` | brak NaN (reguły pokrywają całą przestrzeń wejść) |
| `test_pareto.py` | `nondominated`, `knee`, `lower_hull_mask`, `hypervolume_2d` na ręcznych przykładach |
| `test_graph.py::test_path_continuity` | kolejne krawędzie trasy dzielą węzeł; trasa zaczyna/kończy się w snapniętych punktach |
| `test_graph.py::test_sweep_contains_shortest` | λ=0 daje trasę o minimalnym czasie (porównanie z networkx na małym grafie) |
| `test_api.py` | `TestClient`: 200 dla poprawnego żądania, 422 dla punktu poza Krakowem, schemat odpowiedzi |

### 13.2 Benchmark (`scripts/bench.py`)

- 50 losowych par/trójek punktów w Krakowie (odległości 2–12 km), każdy profil, scenariusz *Heatwave*.
- Raport: p50/p95 `timing_ms.total` dla `fast`, oraz HV i liczba ★ dla `deep` vs sweep.
- **Cele:** `fast` p95 < 1000 ms (docelowo < 500 ms), `deep` ≤ budżet + 200 ms.
- Wyniki idą na slajd „Engineering" (tabelka + wykres).

---

## 14. Uruchomienie na demo (lokalnie)

Decyzja: **lokalnie, za darmo, bez tunelu.**

### 14.1 Dzień demo: checklista

- [ ] `data/processed/` kompletne na laptopie prezentującym (skopiowane z dysku zespołu).
- [ ] `make run` (1 worker, bez `--reload`). Po starcie log „warmup done" i pierwsze zapytanie < 1 s.
- [ ] **Tryb offline:** scenariusze są w repo. Bez internetu nie ładują się tylko kafle podkładu, więc przygotujcie fallback (zrzut ekranu lub przetestowany wcześniej cache przeglądarki).
- [ ] Zamknięte zbędne aplikacje (RAM), zasilacz podłączony, rozdzielczość 1920×1080, zoom przeglądarki 100–110%.
- [ ] Przygotowane 2 zestawy punktów (zapisane w `localStorage` lub jako przycisk „Demo route").
- [ ] **Nagranie wideo demo (1:30–2:00)** z OBS Studio (darmowe) w trakcie dnia. To ono jest „demo linkiem" w zgłoszeniu na HackTribe (YouTube niepubliczny / Google Drive), bo mentorzy w fazie 1 nie zobaczą działającej aplikacji.
- [ ] Repo publiczne na GitHubie z README: zrzut ekranu, `make setup && make data && make run`, opis architektury.

### 14.2 Gdyby kiedyś trzeba było wystawić publicznie

Bez zmian w kodzie: ten sam `Dockerfile` na dowolnym VPS (≥ 2 GB RAM), za reverse proxy (Caddy daje automatyczny HTTPS). Poza zakresem hackathonu.

---

## 15. Plan 24 h, role i kamienie milowe

### 15.1 Role (dla zespołu 4-osobowego; przy mniejszym łączymy R3+R4)

| Rola | Zakres |
|---|---|
| **R1 GIS/Data** | p01–p05, p08 (graf, MSIP, budynki, raster, cień, cechy) |
| **R2 Engine** | `graph.py`, `router_fast.py`, `pareto.py`, potem `router_evo.py`, benchmark |
| **R3 Backend/Fuzzy/ML** | `fuzzy/*`, p09, `exposure.py`, `conditions.py`, p06–p07, p10, FastAPI |
| **R4 Frontend/Design/Pitch** | `static/*`, UX, zrzuty, wideo, slajdy, opis zgłoszenia |

### 15.2 Harmonogram (H = godziny od startu)

| H | R1 GIS/Data | R2 Engine | R3 Backend/Fuzzy/ML | R4 Front/Pitch |
|---|---|---|---|---|
| **0–1** | *Wszyscy:* lektura briefu, decyzja o kategorii, repo + szkielet, `make setup` u każdego | | | |
| 1–4 | p01 graf, p02 MSIP | `graph.py` + sweep na grafie z p01 (wagi = sama długość) | `fuzzy/model.py`, p09 LUT, testy monotoniczności | `index.html` + mapa + markery na **mock JSON** |
| 4–8 | p03 budynki (T1), p04 raster, p05 cień | Pareto, wybór 3 tras, `optimize_order` | `conditions.py` (Open-Meteo, GIOŚ), `exposure.py`, FastAPI `/api/routes` | karty, Chart.js, suwak czasu, style |
| **8–10** | **M1: end-to-end na realnych danych** (trasa live w UI). Integracja i naprawa błędów, wszyscy razem | | | |
| 10–14 | p08 cechy (f_pm z GIOŚ), korytarze przewietrzania | `router_evo.py` NSGA-II + streaming | p06–p07 ML LST, p10 scenariusze, `explain.py` | Deep search UI, nakładki, wyjaśnienia na mapie |
| 14–17 | 😴 **Sen zmianowy:** po 2–3 h, nie wszyscy naraz (R1+R3 śpią 14–17, R2+R4 17–20) | | | |
| 17–20 | upgrade T2 budynków (jeśli czas) | benchmark, HV, ★, tuning budżetu | testy API, fallback offline, cache | zrzuty, **szkic slajdów** |
| **20** | **FEATURE FREEZE.** Od teraz tylko bugfixy | | | |
| 20–22 | README, porządki | wyniki benchmarku do slajdów | stabilność, `make run` na laptopie demo | **nagranie wideo**, slajdy v1 |
| 22–23 | *Wszyscy:* przegląd slajdów, opis projektu, **wysłanie zgłoszenia na HackTribe najpóźniej H23 − 30 min** | | | |
| 23–24 | bufor / próba pitchu | | | |

### 15.3 Kamienie milowe i cięcia (MoSCoW)

| Priorytet | Zakres |
|---|---|
| **Must** (M1, H10) | graf + cień (choćby statyczny) + fuzzy + sweep + 3 trasy w UI + live/scenariusze |
| **Should** (H17) | cień zależny od godziny + suwak, profile, wyjaśnienia „Avoids", optimize order, korekta GIOŚ |
| **Could** (H20) | NSGA-II deep search + streaming + ★, ML LST, nakładki warstw |
| **Won't (tym razem)** | Airly, nDSM z LiDAR, hałas, tryb „city planner", aplikacja mobilna |

**Zasada:** jeśli coś z *Could* nie działa na H20, to wylatuje z demo i ląduje na slajdzie „Next steps".

---

## 16. Pitch: 10 slajdów pod kryteria oceny

| # | Slajd | Kryterium |
|---|---|---|
| 1 | **Problem:** Kraków, smog zimą i upał latem; rowerzysta wdycha 2–3× więcej niż kierowca; mapy optymalizują tylko czas | Relation |
| 2 | **Rozwiązanie w 1 zdaniu** + duży zrzut ekranu (3 trasy) | Idea |
| 3 | **Demo flow** (3 kadry: heatwave → zmiana godziny → smog + astma) + link do wideo | Usability, Design |
| 4 | **Dane:** fuzja OSM + MSIP + GIOŚ + CAMS + Landsat; fakt „CAMS 161 vs GIOŚ 63 µg/m³" | Innovation, Relation |
| 5 | **Cień zależny od słońca:** ray-marching po rastrze wysokości, mapa 14:00 vs 18:30 | Innovation |
| 6 | **Fuzzy:** 3 wejścia → dyskomfort, reguły czytelne, profile zdrowotne, kotwice w normach UTCI/EAQI/WHO | Innovation, Relation |
| 7 | **Pareto + NSGA-II:** dlaczego suma ważona nie wystarcza (★), Route Morphing, HV vs sweep | Innovation |
| 8 | **Engineering:** architektura offline/online, p95 czasu odpowiedzi, testy | Completeness |
| 9 | **Wpływ / kto skorzysta:** pod kategorię (patrz niżej) | Applicability |
| 10 | **Next steps + zespół + repo** | Completeness |

**Akcent zależny od kategorii (decyzja po briefie):**

- **Smart City:** warstwa dla miasta, czyli mapa „hotspotów dyskomfortu" na sieci rowerowej (gdzie sadzić drzewa, gdzie brakuje cienia) oraz symulacja „co jeśli" z modelu ML (dosadzenie drzew → spadek anomalii). Integracja z danymi MSIP/ZTP.
- **Sport & Healthcare:** dawka wdychana PM2.5 per trasa, profile (astma, senior, sportowiec), minuty w stresie cieplnym UTCI, „healthy commute score".

---

## 17. Ryzyka i plan B

| Ryzyko | Prawdop. | Plan B |
|---|---|---|
| Overpass/OSMnx timeout przy pobieraniu grafu | średnie | `ox.settings.use_cache=True`; inny mirror Overpass (`ox.settings.overpass_url`); ostatecznie ekstrakt `.pbf` z Geofabrik (Małopolska) |
| `csgraph` sumuje krawędzie równoległe → złe wagi | wysokie, jeśli się zapomni | deduplikacja (u,v) w p01, test `test_path_continuity` |
| skfuzzy: „no rules fired" | średnie | `assert` w p09; obecny zestaw reguł sprawdzony: 0 luk; test `test_lut_complete` przy każdej zmianie reguł |
| Fuzzy niemonotoniczny (gorsze warunki → niższa ocena) | **pewne przy naiwnych regułach** (zmierzone: −2,9 pkt) | reguły ze strażnikami (9.3) + `monotone()` + testy monotoniczności |
| Cień liczy się za długo | średnie | geometrie nieskierowane, mniej binów, multiprocessing; w ostateczności cień tylko z drzew MSIP (bez budynków) |
| NSGA-II za wolny | średnie | korytarz, mniejsza populacja, budżet czasu; w ostateczności zostaje sweep (Must działa bez EA) |
| Open-Meteo/GIOŚ niedostępne na demo | niskie | scenariusze w repo, `last_live.json` |
| Limity GIOŚ | średnie | pobieranie w tle co 60 min, tylko kluczowe sensory |
| Parsowanie CityGML/BDOT zajmuje za długo | wysokie | zostajemy na T1 (OSM + wysokości domyślne), opisane uczciwie |
| Dane MSIP z 2015 (nieaktualne) | pewne | uzupełnienie NDVI z Sentinel-2 (Should/Could), wzmianka na slajdzie |
| Brak Wi-Fi na sali | średnie | wideo + zrzuty; scenariusze działają offline (poza kaflami) |
| Za mało snu → błędy pod koniec | wysokie | sen zmianowy, feature freeze H20 |

---

## 18. Licencje i atrybucje

W stopce UI i na slajdzie „Data sources":

- **OpenStreetMap**: © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).
- **Open-Meteo**: [CC BY 4.0](https://open-meteo.com/en/terms), tylko użycie niekomercyjne. Dane jakości powietrza: **Copernicus Atmosphere Monitoring Service (CAMS)**.
- **GIOŚ**: dane Głównego Inspektoratu Ochrony Środowiska (źródło: powietrze.gios.gov.pl).
- **MSIP Kraków**: dane Urzędu Miasta Krakowa, wykorzystanie zgodnie z regulaminem MSIP.
- **GUGiK / Geoportal**: dane PZGiK udostępniane bezpłatnie.
- **Landsat**: USGS (domena publiczna). **Sentinel-2/Copernicus**: free & open.
- **CARTO basemap**: © CARTO (warunki dla użytku niekomercyjnego).
- Biblioteki: Leaflet (BSD-2), Chart.js (MIT), DEAP (LGPL), scikit-fuzzy (BSD), OSMnx (MIT), FastAPI (MIT).

Pkt 14 regulaminu: prawa autorskie do rozwiązania **zostają przy zespole**.

---

## 19. Otwarte kwestie do sprawdzenia na miejscu

1. **Godzina startu** (regulamin: „11:00 PM 3.10", możliwa literówka) i czy wolno wcześniej pobrać publiczne dane. Pytanie na Discordzie.
2. **Brief zadania:** po starcie dopasować akcent (sekcja 16) i ewentualnie zakres.
3. **Aktualne progi EAQI** (EEA mogła je zrewidować), żeby podmienić `BANDS` w 8.3.
4. **Sygnatury `pythermalcomfort`** (`utci`, `solar_gain`) w zainstalowanej wersji.
5. **Nazwy assetów Landsat** w Planetary Computer (`items[0].assets.keys()`).
6. **Limity GIOŚ** per endpoint w Swaggerze.
7. **Airly:** czy da się szybko dostać darmowy klucz i jaki ma limit (opcjonalne).
8. **Kontraruch rowerowy** w grafie OSMnx (`oneway:bicycle=no`), test na 2–3 znanych ulicach w centrum.
9. **Format LoD1/BDOT10k** dla Krakowa (czy da się w < 1 h wyciągnąć wysokości), inaczej zostaje T1.
10. Parametry przyjęte jako **założenia** (do jawnego opisania na slajdzie): wysokość drzew 12 m, `k_LST = 0.3`, redukcja UV w cieniu 0,6, `wind_factor`, wartości VE/prędkości profili.

---

*Źródła zweryfikowane 3.10.2026: Open-Meteo (forecast, archive, air-quality: zapytania testowe), GIOŚ API v1 (lista stacji, sensory, indeks, dane archiwalne, OpenAPI), MSIP ArcGIS REST (warstwy, pola, liczba obiektów, eksport GeoJSON), dokumentacja Geoportalu, Copernicus, Planetary Computer/GEE, OSMnx.*
