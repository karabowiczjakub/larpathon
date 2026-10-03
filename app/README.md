# Backend (Flask) — how to run and how to plug in your module

Contracts: `app/contracts.py` (source of truth, details in `roles/04_backend_integration.md` §4).

## Run

```bash
make mock            # whole app on mocks, no data needed (http://127.0.0.1:8000/api/health)
make dev             # real modules where available, mocks for the rest
make demo            # waitress, one process, 8 threads (use this for the demo)
make test            # pytest
make bench           # 50 random routes on the current modules: p50/p95 latency, ECO vs FASTEST
```

Settings are environment variables, listed in `.env.example` (e.g. `MOCK_MODULES=shade make dev`).

## Plugging in a role module

The backend loads each module from the path below. If the module is missing or breaks the contract,
the app falls back to its mock and keeps working. `/api/health` shows `"real"`, `"mock"` or
`"mock (fallback)"` for each module, and `errors` explains the fallback. Set `STRICT_MODULES=1` to
fail loudly instead.

| Role | Module path (config key) | Called as | Must return |
|---|---|---|---|
| 1 Graph | `app.graph.routing:RoutingGraph.load` (`GRAPH_FACTORY`) | `load(data_dir)` | `RoutingGraphP` |
| 3 Shade | `app.shade.model:ShadeModel.load` (`SHADE_FACTORY`) | `load(data_dir, n_edges=E)` | `ShadeModelP` |
| 2 Env | `app.env.service:EnvironmentService` (`ENV_FACTORY`) | `EnvironmentService(scenario_dir, data_dir)` | `EnvironmentServiceP` |
| 2 Exposure | `app.env.exposure:compute_edge_exposure` (`EXPOSURE_FN`) | `fn(ctx, shade, graph, tree_frac, profile)` | `EdgeExposure` |

Rules, checked at startup and on every request (`app/contract_checks.py`):

- every per-edge array has shape `(E,)` in `eid` order (`edge_mid_lonlat`: `(E, 2)`);
- `snap(lat, lon, index)` raises `PointOutsideArea(msg, index=index)`, and `route()` raises `NoRoute`;
- `geometry(eids)` returns `[[lon, lat], ...]` without duplicating shared nodes, and `coord_counts(eids)` returns the number of points per edge;
- times passed to `sun()` and `edge_shade()` are tz-aware Europe/Warsaw;
- arrays the backend passes to you (such as `shade`) are read-only, so do not modify them in place;
- NaN values are replaced by 0 and logged, but please do not return them.

`tests/test_contracts.py` runs automatically on your real module once your code and the artefacts in
`data/processed/` exist. `tests/test_integration.py` loads all four real modules through this config from
tiny artefacts in the §4.2 formats, so the chain is tested even before the city-wide data is built.

Role 2's `EnvironmentService` refreshes live data in a background thread (every 30 min) and caches it in
`DATA_DIR/last_live.json`; when the feed is down it serves `source="fallback"` and the API keeps working.

Optional for Role 1: `cost_matrix(points, edge_cost) -> (k, k)` makes "optimize order" use real
travel costs. Without it, the backend orders the points by straight-line distance.

## Code map (Backend)

| File | Responsibility |
|---|---|
| `__init__.py` | `create_app(overrides, modules=None)` |
| `api.py` | endpoints only (validate → Engine → JSON) |
| `errors.py` | exception → JSON error (`validation` 400, `point_outside_area` 422, `no_route` 404, `internal` 500) |
| `schemas.py` | pydantic request models; naive times are taken as Kraków time |
| `providers.py` | real-or-mock factory per module (`Modules`) |
| `engine/service.py` | `Engine`: env → costs → routing → response |
| `engine/costs.py` | per-edge time/shade/exposure, LRU cache (conditions × 30-min bucket × profile) |
| `engine/variants.py` | route strategies: FASTEST, ECO (add a variant = one `RouteVariant`) |
| `engine/metrics.py`, `engine/explain.py` | metrics, comparison, segments, "avoids" |
| `engine/layers.py` | shade/discomfort map overlay for `/api/layers/shade` |
| `engine/ordering.py` | "optimize order" for via points |
| `profiles.py` | speed, ventilation and ECO α per profile |
| `mocks/` | stand-ins for roles 1–3 (synthetic grid over Kraków with real Dijkstra) |
| `static/` | frontend (Role 5): Leaflet UI served at `/`; `./run_frontend_demo.sh` starts it with the backend |

## API additions to roles/04 §4.4 (backward compatible)

- `POST /api/route` accepts `optimize_order: bool` (default `false`); the response has `order`,
  the visiting order as indices of `points`.
- `timing_ms` has the keys `env, shade, exposure, costs, routing, describe, total`.
- `/api/health` has `errors` (why a module fell back to its mock) and `live_source`;
  `live_data_age_s` is `null` unless live data is actually being served.
- An unknown `scenario` returns 400 `validation`.
- `GET /api/layers/shade?bbox=w,s,e,n&scenario=&at=&profile=` (the §4.4 stretch) returns a GeoJSON
  FeatureCollection of the edges whose midpoint is in the bbox, one per two-way street, with `shade`,
  `discomfort` (0..1) and `reason`. Over 5000 edges it keeps the longest ones and sets `truncated: true`.
- A scenario is one recorded day: `depart_at` (and `at` in `/api/conditions`) keeps its clock time but
  is moved to the scenario's date, so the sun and shade always match the scenario's weather.

## ECO cost and benchmark (real graph, 3 Oct 2026)

`ECO = t · (1 + α · excess)`, where `excess = clip((D − D₁₀) / (1 − D₁₀), 0, 1)` and `D₁₀` is the 10th
percentile of discomfort over the whole city in the current conditions (`engine/variants.py`). With the
plain `t · (1 + α · D)` from roles/04 §7, the whole city sits at D 0.7–0.9 in a heatwave or smog, every
detour adds discomfort-minutes, and ECO collapsed onto FASTEST (+0.4% time, +3 pp shade). On mild days
`D₁₀ ≈ 0` and both formulas agree. α per profile is in `profiles.py`.

`make bench` (= `python -m scripts.tune_alpha --pairs 50`): 50 random A→B pairs 1.5–6 km on the
real modules (174,039 edges, LoD1 shade, GIOŚ-corrected scenarios), each profile with its own α:

| Scenario | Profile (α) | ECO ≠ FASTEST | Δ time median / p90 | Δ shade | Δ PM2.5 dose | p50 / p95 |
|---|---|---|---|---|---|---|
| Heatwave 14:00 | standard (5) | 98% | +6.0% / +13.5% | +17.5 pp | +1.3% | 37 / 114 ms |
| Heatwave 14:00 | asthma (5) | 98% | +6.7% / +18.7% | +13.8 pp | +2.1% | 42 / 85 ms |
| Heatwave 14:00 | senior (4) | 98% | +8.1% / +16.7% | +19.7 pp | +4.0% | 35 / 48 ms |
| Heatwave 14:00 | athlete (3) | 100% | +4.6% / +12.8% | +13.6 pp | +0.7% | 37 / 52 ms |
| Smog 17:00 | standard (5) | 86% | +1.2% / +12.4% | — | −0.2% | 41 / 76 ms |
| Smog 17:00 | asthma (5) | 94% | +1.2% / +6.3% | — | −0.9% | 39 / 70 ms |
| Smog 17:00 | senior (4) | 96% | +3.3% / +13.5% | — | 0.0% | 37 / 45 ms |
| Smog 17:00 | athlete (3) | 90% | +1.1% / +4.5% | — | −1.3% | 37 / 52 ms |

Times are `Engine.route` (env → shade → exposure → 2 × Dijkstra → geometry), the first request per
scenario/profile included (it computes exposure for all edges, ~120 ms; later ones hit the cost cache).
In smog ECO avoids arterials (NO₂ ×2.3), but the episode covers the whole city, so the PM2.5 dose barely
moves — an honest result. `python -m scripts.tune_alpha --alphas 2 3 5 8 --scenario … --profile …` tunes α.
