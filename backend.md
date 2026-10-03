# Role 4 — Backend + Integration

## Source of truth

Backend framework: **Flask** (not FastAPI).

Before making changes, read `roles/04_backend_integration.md`.

`roles/04_backend_integration.md` is authoritative and takes precedence over this file and `PLAN.md`.
Use `PLAN.md` for background only; where it conflicts with `roles/`, follow `roles/`.

## Responsibility

You own application integration and the Flask API.

Your job is to connect:

Environment ----\
Shade -----------> Routing ---> Flask API ---> Frontend
Graph -----------/

Backend orchestrates modules.

Backend does NOT absorb their internal business logic.

## Responsibilities

Implement the Flask application and API specified in `roles/04_backend_integration.md`
(`PLAN.md` section 11 describes the extended version with the Pareto front).

You also coordinate shared contracts between modules.

Flask entry point: `create_app()` in `app/__init__.py`, endpoints in a blueprint in `app/api.py`.
Keep both thin: load modules once at startup, then only orchestrate.

The current root `app.py` is a Streamlit page, not part of the Flask app.
Agree with the team to rename or remove it, so it is not confused with the `app/` package.

Run:
- development: `FLASK_APP=app:create_app flask run --debug --port 8000` (`make dev`),
- without data: `USE_MOCKS=1` (`make mock`),
- demo: `waitress-serve --port 8000 --threads 8 --call app:create_app` (`make run`), one process only.

A request should approximately:

1. validate input,
2. obtain prepared environmental context,
3. call routing,
4. serialize route results,
5. return JSON.

## Shared contracts

Protect shared interfaces.

When a contract is needed between two modules:
1. define the smallest required structure,
2. document it,
3. keep it stable,
4. notify affected module owners before changing it.

Important shared concepts include those defined by `PLAN.md`, such as:
- environmental context,
- routing profile,
- route result,
- edge identity.

Do not silently change these structures.

## Integration

Integrate modules through their public interfaces.

Do not import private implementation details from another module.

Do not duplicate:
- routing formulas,
- environmental scoring,
- shade calculations

inside Flask code.

## Mock-first development

Backend must work before all modules are finished.

Use mock implementations for:
- environment,
- shade/environmental edge values,
- routing results

where necessary.

Replace mocks incrementally with real implementations.

## Files

You own backend/integration files, shared configuration and integration tests.

Avoid editing another person's implementation files.

## Tests

Own integration/API tests, using `create_app({...}).test_client()`.

Test at minimum:
- valid route request,
- invalid input,
- provider failure/fallback,
- routing failure,
- response compatible with frontend contract.

## Done when

- application starts,
- API works using mocks,
- real modules can replace mocks without rewriting endpoints,
- FASTEST and ECO results reach the frontend,
- failures return controlled errors,
- integration tests pass.