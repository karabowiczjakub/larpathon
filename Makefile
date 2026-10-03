PY ?= .venv/bin/python
PORT ?= 8000

.PHONY: dev mock demo test

dev:  ## Flask dev server with reload (real modules, mock fallback)
	$(PY) -m flask --app app:create_app run --debug --port $(PORT)

mock:  ## whole app on mocks, no data needed
	USE_MOCKS=1 $(PY) -m flask --app app:create_app run --debug --port $(PORT)

demo:  ## one process, threads; never several workers (graph and shade live in RAM)
	$(PY) -m waitress --host 127.0.0.1 --port $(PORT) --threads 8 --call app:create_app

test:
	$(PY) -m pytest -q
