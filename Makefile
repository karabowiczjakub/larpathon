PYTHON ?= .venv/bin/python

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
