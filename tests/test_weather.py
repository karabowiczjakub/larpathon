from datetime import datetime
import zoneinfo
from unittest.mock import patch
import requests
import pytest

from src.environment.weather import get_weather_snapshot, WeatherSnapshot
from src.services.cache import weather_cache

TZ = zoneinfo.ZoneInfo("Europe/Warsaw")

@pytest.fixture(autouse=True)
def clear_cache():
    weather_cache.clear()

def test_weather_complete_response():
    mock_response = {
        "hourly": {
            "time": ["2026-10-03T15:00", "2026-10-03T16:00"],
            "temperature_2m": [15.0, 16.0],
            "apparent_temperature": [14.0, 15.0],
            "uv_index": [2.0, 2.5]
        }
    }
    
    with patch('src.environment.weather._fetch_open_meteo', return_value=mock_response):
        dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
        snapshot = get_weather_snapshot(dt, 50.0, 19.0)
        
        assert snapshot.temperature_c == 16.0
        assert snapshot.apparent_temperature_c == 15.0
        assert snapshot.uv_index == 2.5
        assert snapshot.source == "open-meteo"
        assert snapshot.quality == "model"

def test_weather_missing_uv():
    mock_response = {
        "hourly": {
            "time": ["2026-10-03T16:00"],
            "temperature_2m": [16.0],
            "apparent_temperature": [15.0],
            # uv_index brak
        }
    }
    
    with patch('src.environment.weather._fetch_open_meteo', return_value=mock_response):
        dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
        snapshot = get_weather_snapshot(dt, 50.0, 19.0)
        
        assert snapshot.temperature_c == 16.0
        assert snapshot.uv_index is None
        assert snapshot.source == "open-meteo"
        assert snapshot.quality == "model"

def test_weather_fallback_on_network_error():
    with patch('src.environment.weather._fetch_open_meteo', side_effect=requests.RequestException("Timeout")):
        dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
        snapshot = get_weather_snapshot(dt, 50.0, 19.0)
        
        assert snapshot.temperature_c is None
        assert snapshot.uv_index is None
        assert snapshot.source == "fallback"
        assert snapshot.quality == "no_data"

def test_cache_weather():
    mock_response = {
        "hourly": {
            "time": ["2026-10-03T16:00"],
            "temperature_2m": [16.0],
            "apparent_temperature": [15.0],
            "uv_index": [2.0]
        }
    }
    
    with patch('src.environment.weather._fetch_open_meteo', return_value=mock_response) as mock_fetch:
        dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
        # Pierwsze wywołanie pobiera z sieci
        get_weather_snapshot(dt, 50.0, 19.0)
        mock_fetch.assert_called_once()
        
        # Drugie wywołanie powinno być z cache
        get_weather_snapshot(dt, 50.0, 19.0)
        mock_fetch.assert_called_once()  # Call count remains 1

def test_datetime_timezone():
    mock_response = {
        "hourly": {
            "time": ["2026-10-03T17:00"],
            "temperature_2m": [16.0],
            "apparent_temperature": [15.0],
            "uv_index": [2.0]
        }
    }
    with patch('src.environment.weather._fetch_open_meteo', return_value=mock_response):
        # 15:00 UTC to 17:00 CEST (Europe/Warsaw in summer/early autumn)
        import pytz
        dt_utc = datetime(2026, 10, 3, 15, 0, tzinfo=pytz.UTC)
        snapshot = get_weather_snapshot(dt_utc, 50.0, 19.0)
        
        # timestamp w obiekcie snapshotu powinien być na naszą strefę
        assert snapshot.timestamp.tzinfo == TZ
        assert snapshot.timestamp.hour == 17
        assert snapshot.temperature_c == 16.0
