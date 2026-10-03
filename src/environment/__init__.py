from dataclasses import dataclass
from datetime import datetime
import zoneinfo

from src.environment.weather import get_weather_snapshot
from src.environment.pollution import get_pollution_snapshot
from src.environment.normalization import compute_heat_factor, compute_uv_factor

TZ = zoneinfo.ZoneInfo("Europe/Warsaw")

@dataclass
class EnvironmentalContext:
    timestamp: datetime
    temperature_c: float | None
    apparent_temperature_c: float | None
    uv_index: float | None
    weather_source: str
    weather_quality: str
    heat_factor: float
    uv_factor: float
    pollution_by_edge: dict[str, float]
    pollution_source: str
    pollution_quality: str

def build_environmental_context(
    timestamp: datetime | None = None,
    edge_points: dict[str, tuple[float, float]] | None = None
) -> EnvironmentalContext:
    """
    Główna funkcja fabrykująca, przygotowująca dane środowiskowe dla routingu.
    Wszystkie operacje sieciowe używają cache, więc wywołanie jej podczas wyznaczania tras 
    jest szybkie i nie obciąża API.
    """
    if timestamp is None:
        timestamp = datetime.now(TZ)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=TZ)
    else:
        timestamp = timestamp.astimezone(TZ)
        
    if edge_points is None:
        edge_points = {}
        
    # Centrum Krakowa jako domyślny punkt dla ogólnej pogody
    krakow_lat = 50.0614
    krakow_lon = 19.9366
    
    weather = get_weather_snapshot(timestamp, krakow_lat, krakow_lon)
    pollution = get_pollution_snapshot(timestamp, edge_points)
    
    return EnvironmentalContext(
        timestamp=weather.timestamp,
        temperature_c=weather.temperature_c,
        apparent_temperature_c=weather.apparent_temperature_c,
        uv_index=weather.uv_index,
        weather_source=weather.source,
        weather_quality=weather.quality,
        heat_factor=compute_heat_factor(weather.apparent_temperature_c or weather.temperature_c),
        uv_factor=compute_uv_factor(weather.uv_index),
        pollution_by_edge=pollution.pollution_by_edge,
        pollution_source=pollution.pollution_source,
        pollution_quality=pollution.pollution_quality
    )
