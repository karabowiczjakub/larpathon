from datetime import datetime
import zoneinfo
from unittest.mock import patch
import pytest

from src.environment import build_environmental_context, EnvironmentalContext
from src.environment.weather import WeatherSnapshot
from src.environment.pollution import PollutionSnapshot

TZ = zoneinfo.ZoneInfo("Europe/Warsaw")

def test_end_to_end_environment_context():
    dt = datetime(2026, 10, 3, 16, 0, tzinfo=TZ)
    edge_points = {"e1": (50.0, 19.0)}
    
    mock_weather = WeatherSnapshot(
        timestamp=dt,
        temperature_c=25.0,
        apparent_temperature_c=26.0,
        uv_index=5.5,
        source="open-meteo",
        quality="model"
    )
    
    mock_pollution = PollutionSnapshot(
        pollution_by_edge={"e1": 0.8},
        pollution_source="GIOS",
        pollution_quality="interpolated"
    )
    
    with patch('src.environment.get_weather_snapshot', return_value=mock_weather), \
         patch('src.environment.get_pollution_snapshot', return_value=mock_pollution):
         
        ctx = build_environmental_context(dt, edge_points)
        
        # Weryfikacja typu
        assert isinstance(ctx, EnvironmentalContext)
        
        # Weryfikacja wartości pogody
        assert ctx.temperature_c == 25.0
        assert ctx.uv_index == 5.5
        assert ctx.weather_source == "open-meteo"
        
        # Weryfikacja czynników
        # temp = 26.0 -> factor = (26-20)/20 = 0.3
        assert abs(ctx.heat_factor - 0.3) < 0.01
        # uv = 5.5 -> factor = 5.5/11 = 0.5
        assert abs(ctx.uv_factor - 0.5) < 0.01
        
        # Weryfikacja zanieczyszczeń
        assert ctx.pollution_by_edge["e1"] == 0.8
        assert ctx.pollution_source == "GIOS"

def test_build_environmental_context_defaults():
    # Sprawdzamy czy poprawnie ustawia aktualny czas jeśli None
    
    mock_weather = WeatherSnapshot(
        timestamp=datetime.now(TZ),
        temperature_c=20.0,
        apparent_temperature_c=20.0,
        uv_index=0.0,
        source="open-meteo",
        quality="model"
    )
    
    mock_pollution = PollutionSnapshot(
        pollution_by_edge={},
        pollution_source="GIOS",
        pollution_quality="interpolated"
    )
    
    with patch('src.environment.get_weather_snapshot', return_value=mock_weather), \
         patch('src.environment.get_pollution_snapshot', return_value=mock_pollution):
         
        ctx = build_environmental_context()
        assert ctx.timestamp.tzinfo == TZ
