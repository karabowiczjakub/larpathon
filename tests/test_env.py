from datetime import datetime
from zoneinfo import ZoneInfo
import os
import json
import pytest
from app.env.service import EnvironmentService

# Fixture setup scenarios
@pytest.fixture(scope="session", autouse=True)
def setup_scenarios():
    os.makedirs("scenarios", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)
    # create a dummy scenario file if it doesn't exist
    scenario_path = "scenarios/heatwave_2025-07-03.json"
    if not os.path.exists(scenario_path):
        dummy_data = {
            "id": "heatwave_2025-07-03", 
            "label": "Heatwave",
            "default_at": "2025-07-03T14:00:00+02:00",
            "hours": {
                "2025-07-03T14:00": {
                    "temperature_2m": 35.0,
                    "relative_humidity_2m": 20.0,
                    "wind_speed_10m": 5.0,
                    "shortwave_radiation": 862.0,
                    "direct_normal_irradiance": 853.0,
                    "uv_index": 8.0,
                    "pm25_city": 12.0,
                    "pm10_city": 25.0,
                    "no2_city": 20.0,
                    "stations": []
                }
            }
        }
        with open(scenario_path, "w") as f:
            json.dump(dummy_data, f)
            
    smog_path = "scenarios/smog_2025-01-20.json"
    if not os.path.exists(smog_path):
        dummy_data = {
            "id": "smog_2025-01-20", 
            "label": "Smog",
            "default_at": "2025-01-20T17:00:00+01:00",
            "hours": {
                "2025-01-20T17:00": {
                    "temperature_2m": -5.0,
                    "relative_humidity_2m": 80.0,
                    "wind_speed_10m": 1.0,
                    "shortwave_radiation": 10.0,
                    "direct_normal_irradiance": 5.0,
                    "uv_index": 0.0,
                    "pm25_city": 100.0,
                    "pm10_city": 150.0,
                    "no2_city": 80.0,
                    "stations": []
                }
            }
        }
        with open(smog_path, "w") as f:
            json.dump(dummy_data, f)

def test_scenarios_offline():
    env = EnvironmentService("scenarios", "data/processed")
    ctx = env.get("heatwave_2025-07-03", None)
    assert ctx.source == "scenario" and 30 < ctx.temperature_c < 40 and ctx.dni_wm2 > 500
    ctx = env.get("smog_2025-01-20", datetime(2025, 1, 20, 17, tzinfo=ZoneInfo("Europe/Warsaw")))
    assert ctx.pm10 > 50

def test_live_never_raises(monkeypatch):
    import app.env.service as svc
    
    def raise_err(*args, **kwargs):
        raise RuntimeError("offline")
        
    # patch where it's imported (service module)
    monkeypatch.setattr(svc, "fetch_hours", raise_err)
    ctx = EnvironmentService("scenarios", "/tmp").get("live", None)
    assert ctx.source in ("fallback", "live")
