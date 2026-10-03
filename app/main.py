"""
Minimal FastAPI entrypoint for AirRoute Kraków.
Serves the static frontend from app/static/ and exposes /api/* stubs
that the backend team will flesh out.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AirRoute Kraków API", version="0.1.0")

# ── /api stubs (backend team owns these) ────────────────────────
# TODO: replace with real routers once backend modules are ready.

@app.get("/api/health")
def health():
    return {"ok": True, "note": "backend not yet implemented"}

@app.get("/api/profiles")
def profiles():
    return [
        {"id": "standard", "label": "Standard"},
        {"id": "asthma",   "label": "Asthma / Allergy"},
        {"id": "senior",   "label": "Senior / Child"},
        {"id": "athlete",  "label": "Athlete"},
    ]

@app.get("/api/scenarios")
def scenarios():
    return [
        {"id": "live",                    "label": "Live"},
        {"id": "heatwave_2025-07-03T14",  "label": "Heatwave — 3 Jul 2025, 14:00"},
        {"id": "smog_2025-01-20T17",      "label": "Smog — 20 Jan 2025, 17:00"},
    ]

# ── Static frontend — must come AFTER /api/* routes ─────────────
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
