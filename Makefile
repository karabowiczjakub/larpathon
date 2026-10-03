PY ?= .venv/bin/python
PYTHON ?= $(PY)
PORT ?= 8000

.PHONY: dev mock demo test bench

dev:  ## Flask dev server with reload (real modules, mock fallback)
	$(PY) -m flask --app app:create_app run --debug --port $(PORT)

mock:  ## whole app on mocks, no data needed
	USE_MOCKS=1 $(PY) -m flask --app app:create_app run --debug --port $(PORT)

demo:  ## one process, threads; never several workers (graph and shade live in RAM)
	$(PY) -m waitress --host 127.0.0.1 --port $(PORT) --threads 8 --call app:create_app

test:
	$(PY) -m pytest -q

bench:  ## 50 random A->B routes on the current modules: p50/p95 latency and ECO vs FASTEST
	$(PY) -m scripts.tune_alpha --pairs 50

.PHONY: shade
shade:
	$(PYTHON) -m pipeline.shade_build $(SHADE_ARGS)

# --- Rola 2: Environment (scenariusze i road_factors.json wymagają internetu) ---
.PHONY: scenarios fuzzy calibrate-road env-report env-test
scenarios:
	$(PYTHON) -m pipeline.scenarios_build

fuzzy:
	$(PYTHON) -m pipeline.fuzzy_build

calibrate-road:
	$(PYTHON) -m pipeline.calibrate_road

env-report:
	$(PYTHON) -m scripts.env_report

env-test:
	$(PYTHON) -m pytest -q tests/test_env.py tests/test_exposure.py tests/test_fuzzy.py tests/test_env_integration.py
