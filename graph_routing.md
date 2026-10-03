# Role 1 — Graph + Routing

## Source of truth

Backend framework: **Flask** (not FastAPI).

Before making changes, read `roles/01_graph_routing.md`.

`roles/01_graph_routing.md` is authoritative and takes precedence over this file and `PLAN.md`.
Use `PLAN.md` for background only; where it conflicts with `roles/`, follow `roles/`.

## Responsibility

You own the bicycle graph and route calculation.

Your module should:
- load the prepared Kraków bicycle graph,
- find graph nodes for points A and B,
- calculate the FASTEST route,
- calculate the ECO route using environmental data supplied by other modules,
- return exact route edges and route metrics,
- build route geometry required by the backend/frontend.

## Module boundary

Routing receives prepared data.

It must NOT:
- call Open-Meteo,
- call GIOŚ,
- download building data,
- calculate sun position,
- calculate building shadows,
- contain Flask/UI logic.

No HTTP requests or expensive GIS preprocessing inside the routing algorithm.

## Inputs

Routing should work from inputs such as:

- start/end coordinates,
- bicycle graph,
- routing profile,
- prepared environmental context / edge scores.

Use the exact contracts defined by the project and `PLAN.md`.

For `MultiDiGraph`, preserve exact edge identity:

`(u, v, key)`

Do not assume `(u, v)` uniquely identifies an edge.

## Outputs

Return a structured route result containing the information required by `PLAN.md`,
including the exact selected edges and route geometry.

Do not invent additional public API fields without coordinating with Backend.

## Parallel development

Do not wait for Environment or Shade.

Use deterministic mock environmental values so FASTEST and ECO routing can be tested independently.

## Files

Prefer working only inside routing/graph modules and their tests.

Do not modify:
- environment implementation,
- shade/building implementation,
- frontend,
- Flask endpoints,

unless integration requires a small coordinated contract change.

## Done when

- graph loads correctly,
- A -> B routing works,
- FASTEST works,
- ECO works with mocked environmental data,
- parallel edges are handled correctly,
- returned geometry follows the project coordinate conventions,
- routing tests pass.