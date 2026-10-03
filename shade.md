# Role 3 — Shade + Buildings + Sun

## Source of truth

Backend framework: **Flask** (not FastAPI).

Before making changes, read `roles/03_shade_buildings_sun.md`.

`roles/03_shade_buildings_sun.md` is authoritative and takes precedence over this file and `PLAN.md`.
Use `PLAN.md` for background only; where it conflicts with `roles/`, follow `roles/`.

## Responsibility

You own the shade model.

Implement the building, height, solar-position and shadow calculations described
in `PLAN.md`.

This includes the relevant sources specified there, such as:
- GUGiK building data,
- OSM building information where required,
- building heights,
- solar position,
- building shadows,
- shade values for route/graph edges.

## Module boundary

Shade calculates shade information.

It must NOT:
- calculate complete routes,
- fetch weather or pollution data,
- implement Flask endpoints,
- implement frontend behaviour.

Routing should receive prepared shade values without knowing how shadows were
calculated.

## Coordinates

Be strict about CRS.

Use the coordinate systems required by `PLAN.md`.

Do metric geometry calculations only in the project's metric CRS.
Convert data at module boundaries when required.

Do not mix latitude/longitude geometry with metre-based calculations.

## Performance

Heavy building-data processing belongs in preprocessing where possible.

Do not repeatedly:
- download buildings,
- process the whole city,
- rebuild expensive geometries

for every route request.

Use the caching/preprocessing strategy from `PLAN.md`.

## Output

Expose a small interface that provides the shade information required by routing.

Keep edge identity compatible with Routing: index every per-edge array by `eid`, in the row order of
`data/processed/edges.parquet` (see `roles/01_graph_routing.md`), not by `(u, v, key)`.

## Parallel development

Start with small synthetic building/edge geometries.

Provide deterministic mock shade values so Routing and Backend do not depend on
the full shade pipeline being finished.

## Done when

- building data can be prepared,
- building height can be determined using the plan's fallback rules,
- solar position works,
- shade can be calculated for an edge,
- results use the expected range/format,
- synthetic geometry tests pass.