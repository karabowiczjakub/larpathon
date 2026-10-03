@echo off
rem AirRoute Krakow: backend + frontend in one Flask process -> http://127.0.0.1:8000
rem Without data in data\processed run: set USE_MOCKS=1 before this script
cd /d "%~dp0"
.venv\Scripts\python -m waitress --host 127.0.0.1 --port 8000 --threads 8 --call app:create_app
