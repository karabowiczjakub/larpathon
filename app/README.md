# Backend (Flask) — how to run and how to plug in your module

Contracts: `app/contracts.py` (source of truth, details in `roles/04_backend_integration.md` §4).

## Run

```bash
make mock            # whole app on mocks, no data needed (http://127.0.0.1:8000/api/health)
make dev             # real modules where available, mocks for the rest
make demo            # waitress, one process, 8 threads (use this for the demo)
make test            # pytest
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
`data/processed/` exist.

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
| `engine/ordering.py` | "optimize order" for via points |
| `profiles.py` | speed, ventilation and ECO α per profile |
| `mocks/` | stand-ins for roles 1–3 (synthetic grid over Kraków with real Dijkstra) |

## API additions to roles/04 §4.4 (backward compatible)

- `POST /api/route` accepts `optimize_order: bool` (default `false`); the response has `order`,
  the visiting order as indices of `points`.
- `timing_ms` has the keys `env, shade, exposure, costs, routing, describe, total`.
- `/api/health` has `errors` (why a module fell back to its mock).
- An unknown `scenario` returns 400 `validation`.

`scripts/tune_alpha.py` tunes ECO α and benchmarks latency on the current modules (mocks or real).
