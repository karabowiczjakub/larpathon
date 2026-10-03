# Role 5 — Frontend

## Source of truth

Before making changes, read `PLAN.md`.

`PLAN.md` is authoritative.
If this file conflicts with `PLAN.md`, follow `PLAN.md`.

## Responsibility

You own the user-facing interface.

Implement the UI and interaction flow described in `PLAN.md`.

Use the frontend stack defined there.

The frontend should allow the user to:
- view the Kraków map,
- select points A and B using the interaction defined in the plan,
- request route calculation,
- see FASTEST and ECO routes,
- compare the route metrics required by the plan,
- see loading/error states,
- understand the environmental information presented by the application.

## Module boundary

Frontend communicates with Backend through HTTP/JSON.

It must NOT:
- calculate routes,
- reproduce ECO scoring,
- call GIOŚ/Open-Meteo directly,
- calculate shadows,
- process the OSM graph.

Backend results are authoritative.

## API isolation

Keep API communication separate from map rendering where practical.

The map should consume already prepared route GeoJSON/data.

Do not make frontend code depend on Python implementation details.

## Parallel development

Do not wait for Backend.

Create a mock API response matching the agreed backend response and build the
entire interface against it.

When Backend is ready, replace the mock with the real request.

## Map

Use the map technology specified by `PLAN.md`.

Keep route layers for FASTEST and ECO separate so they can be styled and updated
independently.

Preserve required map/data attribution.

## UX

Prioritize hackathon demo reliability:

A -> B -> calculate -> clearly compare FASTEST vs ECO.

Avoid adding UI features not required by `PLAN.md` until this flow works.

## Files

Prefer working only inside templates/static/frontend files.

Do not modify routing, environment, shade or graph implementation.

## Done when

- A/B selection works,
- route request works against a mock,
- both routes render correctly,
- required metrics are visible,
- loading state works,
- errors are understandable,
- switching from mock API to real Backend requires minimal changes.