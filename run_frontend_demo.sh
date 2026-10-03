#!/usr/bin/env sh
# AirRoute Kraków: backend + frontend in one Flask process -> http://127.0.0.1:8000
# Without data in data/processed run: USE_MOCKS=1 ./run_frontend_demo.sh
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python -m waitress --host 127.0.0.1 --port "${PORT:-8000}" --threads 8 --call app:create_app
