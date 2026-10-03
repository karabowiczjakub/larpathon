from datetime import datetime
import zoneinfo
from unittest.mock import patch
import pytest

from src.environment.pollution import get_pollution_snapshot, _interpolate_idw
from src.services.cache import pollution_cache

TZ = zoneinfo.ZoneInfo("Europe/Warsaw")

@pytest.fixture(autouse=True)
def clear_cache():
    pollution_cache.clear()

def test_pollution_gios_success():
    mock_gios_data = [
        {"lat": 50.05, "lon": 19.92, "pm10": 50.0, "pm25": 25.0, "no2": 40.0}
    ]
    
    with patch('src.environment.pollution._fetch_gios_data', return_value=mock_gios_data):
        dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
        snapshot = get_pollution_snapshot(dt, {"edge1": (50.06, 19.93)})
        
        assert snapshot.pollution_source == "GIOS"
        assert snapshot.pollution_quality == "interpolated"
        assert "edge1" in snapshot.pollution_by_edge
        # pm10 = 50.0 / 150.0 = 0.333
        # pm25 = 25.0 / 75.0 = 0.333
        # no2 = 40.0 / 340.0 = 0.117
        # max is ~0.333
        assert 0.3 < snapshot.pollution_by_edge["edge1"] < 0.35

def test_pollution_idw():
    # Punkty testowe
    p1 = {"lat": 50.0, "lon": 20.0, "pm10": 100.0, "pm25": None, "no2": None}
    p2 = {"lat": 51.0, "lon": 20.0, "pm10": 0.0, "pm25": None, "no2": None}
    
    # Blisko p1
    res1 = _interpolate_idw([p1, p2], 50.1, 20.0)
    # W połowie drogi
    res2 = _interpolate_idw([p1, p2], 50.5, 20.0)
    
    assert res1["pm10"] > 90.0
    assert 49.0 < res2["pm10"] < 51.0

def test_pollution_fallback():
    # GIOŚ rzuca błąd, wchodzimy do OM AQ
    mock_om_aq = {"lat": 50.0, "lon": 19.0, "pm10": 75.0, "pm25": None, "no2": None}
    
    with patch('src.environment.pollution._fetch_gios_data', side_effect=Exception("GIOŚ padł")), \
         patch('src.environment.pollution._fetch_open_meteo_aq', return_value=mock_om_aq):
         
        dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
        snapshot = get_pollution_snapshot(dt, {"edge1": (50.06, 19.93)})
        
        assert snapshot.pollution_source == "OpenMeteoAQ"
        assert snapshot.pollution_quality == "fallback"
        # pm10 = 75 / 150 = 0.5
        assert abs(snapshot.pollution_by_edge["edge1"] - 0.5) < 0.01

def test_pollution_ultimate_fallback():
    # Obie sieci padają
    with patch('src.environment.pollution._fetch_gios_data', side_effect=Exception("GIOŚ padł")), \
         patch('src.environment.pollution._fetch_open_meteo_aq', side_effect=Exception("OM padł")):
         
        dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
        snapshot = get_pollution_snapshot(dt, {"edge1": (50.06, 19.93)})
        
        assert snapshot.pollution_source == "fallback"
        assert snapshot.pollution_quality == "neutral"
        assert snapshot.pollution_by_edge["edge1"] == 0.5
