# Role 2 — Environment

## Source of truth

Backend framework: **Flask** (not FastAPI).

Before making changes, read `roles/02_environment.md`.

`roles/02_environment.md` is authoritative and takes precedence over this file and `PLAN.md`.
Use `PLAN.md` for background only; where it conflicts with `roles/`, follow `roles/`.

## Responsibility

You own environmental data used by the routing system.

Implement the environmental sources and transformations specified in `PLAN.md`,
including the required weather and air-quality information.

This includes the relevant integrations such as:
- Open-Meteo,
- GIOŚ,
- caching,
- normalization/scoring required by the routing model,
- source quality / provenance required by the plan.

## Module boundary

Environment prepares data.

It must NOT:
- calculate routes,
- modify the bicycle graph during requests,
- calculate building shadows,
- contain Flask endpoint logic,
- contain frontend logic.

Routing must never need to know how Open-Meteo or GIOŚ works.

## Output

Expose a small, stable interface returning prepared environmental data.

The rest of the application should consume this interface rather than calling
external environmental APIs directly.

Follow the environmental contracts defined in `PLAN.md`.

## Data honesty

Do not represent GIOŚ or Open-Meteo pollution data as exact street-level
measurements unless `PLAN.md` explicitly provides a model supporting that claim.

Keep measured data, interpolated/modelled data and proxies distinguishable.

## Reliability

External requests should have:
- timeout,
- cache where specified,
- graceful fallback where specified,
- source/timestamp/quality information when required by the plan.

## Parallel development

Provide deterministic mock data so Routing and Backend can integrate before
external APIs are finished.

## Files

Prefer working only inside environment/data-provider/cache modules and their tests.

Do not modify routing, shade, frontend or Flask code unless a shared contract
requires a coordinated change.

## Done when

- required environmental providers work,
- data is converted to the project's internal format,
- failures do not unnecessarily break routing,
- mock data is available,
- tests cover normalization and provider behaviour.