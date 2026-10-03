# Environment — przekazanie Roli 02

Moduł `app/env/` dostarcza warunki (`EnvironmentService`) i ekspozycję każdej krawędzi
(`compute_edge_exposure`): UTCI, stężenia, UV, dyskomfort 0..1 z logiki rozmytej i dominujący
czynnik. Nie liczy tras, cienia ani endpointów Flask. Źródło prawdy: `roles/02_environment.md`
i kontrakt z `roles/04_backend_integration.md` §4 (`app/contracts.py`).

## Kontrakt integracyjny

```python
from app.env.service import EnvironmentService
from app.env.exposure import compute_edge_exposure

env = EnvironmentService("scenarios", "data/processed")   # wątek w tle odświeża live co 30 min
ctx = env.get("smog_2025-01-20", depart_at)                # nigdy nie rzuca; ctx.source: live|scenario|fallback
shade = shade_model.edge_shade(ctx.timestamp)              # Rola 3
exp = compute_edge_exposure(ctx, shade, graph, shade_model.edge_tree_frac, "asthma")
cost = graph.edge_length_m / v * (1 + alpha * exp.discomfort)   # → graph.route(...)
```

- `env.scenarios()` → `live` + scenariusze z `scenarios/*.json` (z `default_at`).
- Scenariusz to jedna doba: `at` z innej daty jest przenoszone na dzień scenariusza z zachowaniem
  godziny (suwak godziny). Do cienia używajcie `ctx.timestamp`, nie surowego `depart_at`.
- `EnvironmentService(..., refresh=False)` — bez wątku i sieci (testy, skrypty).
- Ekspozycja dla całego miasta (150 tys. krawędzi): ~60 ms; stałe per graf (czynnik drogi,
  wagi IDW) liczone raz dla danego obiektu grafu.

## Przygotowanie danych

```bash
make scenarios        # Open-Meteo archive + CAMS + GIOŚ archiwum → scenarios/*.json (24 h, w gicie)
make calibrate-road   # 90 dni GIOŚ Krasińskiego/Bujaka → app/env/road_factors.json (w gicie)
make fuzzy            # skfuzzy → data/processed/lut_*.npy (śledzone w gicie mimo .gitignore)
make env-report       # docs/env_report.json + docs/env_discomfort.png (fakty na slajd)
make env-test         # testy roli 02 + integracja z RoutingGraph i ShadeModel
```

Demo działa bez internetu: scenariusze, LUT i `road_factors.json` są w repo; live zapisuje
`data/processed/last_live.json` (ignorowany) i bez sieci przechodzi na `fallback`.

## Model (założenia do opisania na slajdzie)

| Składnik | Wzór / założenie |
|---|---|
| Temperatura pod drzewami | `T_a = T_2m − 1 °C · tree_frac · min(1, SW/600)` |
| Promieniowanie | `Tmrt = T_a + (1 − shade) · 0,03 · DNI + 2 °C` przy SW > 100 W/m² (~25 K w pełnym słońcu) |
| Wiatr | `v = clip(v_10m · (1 − 0,3 · tree_frac), 0,5, 17)` |
| UTCI | `pythermalcomfort`, liczone tylko dla unikalnych skwantowanych wejść |
| Tło smogu | mediana godzinowych stacji GIOŚ; korekta CAMS = GIOŚ/CAMS |
| Smog w przestrzeni | IDW (potęga 2) ze stacji **tła** jako mnożnik względem ich mediany, przycięty do 0,5–2; ≥3 stacje, PM2.5 pożycza wzór PM10 |
| Smog przy drodze | `f_road` z danych: mediana ilorazu Krasińskiego/Bujaka; niższe klasy proporcjonalnie |
| Zieleń | `1 − 0,1 · tree_frac` |
| Indeks powietrza | ciągły EAQI 0..6 na progach EEA 2024 (godzinowe); `ve_ratio` profilu mnoży stężenie |
| UV | `UV · (1 − 0,6 · shade)` |
| Dyskomfort | Mamdani (11 reguł ze strażnikami) → LUT 41×31×13 → interpolacja liniowa; projekcja monotoniczna |
| Wyjaśnienie | `reason`: −1 OK, 0 upał, 1 powietrze, 2 UV (najgorszy znormalizowany czynnik) |

Godziny bez pomiarów GIOŚ (opóźnienie 1–2 h, prognoza): CAMS × ostatnia zmierzona korekta
(0,3–3), a odczyty stacji zostają przez 3 h (`stations_at` w danych godzinowych mówi, skąd są).

## Fakty na slajd

| Moment | PM10 CAMS | PM10 GIOŚ (mediana 7–8 stacji) | Krasińskiego | CAMS / GIOŚ |
|---|---|---|---|---|
| Upał 3.07.2025 14:00 | 5,0 | 20,0 | 38,2 | 0,25× (CAMS zaniża 4×) |
| Smog 20.01.2025 17:00 | 161,0 | 78,9 | 63,2 | 2,0× |
| Smog 20.01.2025 22:00 | 289,7 | 64,4 | 51,5 | 4,5× |

Wniosek: model regionalny (~11 km) myli się kilkukrotnie w obie strony, więc korygujemy go stacjami.

Kalibracja drogi (5.07–2.10.2026, ~2100 par godzin): Krasińskiego/Bujaka **PM10 ×1,12, NO₂ ×2,29**
→ `primary` = (1,12; 2,29), `secondary` = (1,07; 1,65), `tertiary` = (1,04; 1,32). Okres letni —
zimą iloraz PM może być inny; przed demo można odświeżyć `make calibrate-road`.

Progi norm: UTCI 26 / 32 / 38 / 46 °C; EAQI PM2.5 5/15/50/90/140, PM10 15/45/120/195/270,
NO₂ 10/25/60/100/150 µg/m³ (airindex.eea.europa.eu); UV wg WHO 3 / 6 / 8 / 11.

`docs/env_discomfort.png`: dyskomfort w funkcji UTCI i indeksu powietrza dla 4 profili (Athlete
różni się przez `ve_ratio` = 1,7 przed indeksem, więc na panelu „Air” pokrywa się ze Standard).

## Odstępstwa od `roles/02` (sprawdzone w API 3.10.2026)

- **Stanowiska dobowe.** Bujaka 2771/2773, Bulwarowa 2793, Wadów 17310 i Swoszowice 20321 dają
  1 wartość na dobę (`getData` → 400). Zamienione na godzinowe 2770, 2792, 17309, 20320; Bujaka
  nie ma godzinowego PM2.5, więc `f_road` dla PM pochodzi z PM10.
- **Strefa czasowa archiwum.** `archivalData` podaje godziny w CET (UTC+1) cały rok — latem
  przesuwamy o +1 h (bieżące `getData` jest w czasie lokalnym).
- **Progi EAQI** podmienione na rewizję EEA 2024 (rola prosiła o weryfikację).
- **Asthma:** R5 zostaje `high` zamiast `extreme` (rola: „agresywne, do strojenia”).
- **Funkcje przynależności bez płaskich wierzchołków** (3.10.2026, po teście na prawdziwym grafie).
  Trapezy z §7 dawały plateau: całe „poor” 3,5–4,5 → stałe 7,5, „hot” 32–36 °C → 7,5, więc arteria
  i osiedle (smog, `standard`) albo półcień i słońce (upał) miały ten sam dyskomfort i ECO nie miało
  czego omijać. Teraz sąsiednie zbiory sumują się do 1: `warm` △(22,26,32), `hot` △(26,32,44),
  `very_hot` od 32 do pełna przy 44; `poor` △(2,3,6), `very_poor` od 3 do pełna przy 6; UV `high` △(4,6,8),
  `very_high` od 6 do 8. Reguły R1–R11 bez zmian. Efekt (smog, `standard`): D(powietrze 3→5)
  0,75 → 0,84 zamiast stałego 0,75; trasy identyczne z FASTEST: 75% → 42%.
- **Live:** odświeżanie w pętli co 30 min (retry co 2 min), a nie na żądanie.

## Ryzyka

| Ryzyko | Zachowanie |
|---|---|
| Open-Meteo/GIOŚ nie odpowiada | `last_live.json`, potem domyślny scenariusz (`source="fallback"`) |
| Pojedynczy sensor GIOŚ pada | pomijany (3 próby, log), reszta stacji działa |
| Brak LUT | wzór „najgorszy czynnik” + ostrzeżenie w logu |
| Brak pythermalcomfort | uproszczony UTCI (PLAN B) + ostrzeżenie |
| Październik live: zimno i czysto | ECO ≈ FASTEST — uczciwy komunikat; demo na scenariuszach |
