import logging
from dataclasses import dataclass
from datetime import datetime
import zoneinfo
import requests

from src.services.cache import weather_cache

logger = logging.getLogger(__name__)
TZ = zoneinfo.ZoneInfo("Europe/Warsaw")

@dataclass
class WeatherSnapshot:
    timestamp: datetime
    temperature_c: float | None
    apparent_temperature_c: float | None
    uv_index: float | None
    source: str
    quality: str

def _fetch_open_meteo(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "hourly": "temperature_2m,apparent_temperature,uv_index",
        "timezone": "Europe/Warsaw"
    }
    
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()

def get_weather_snapshot(timestamp: datetime, lat: float, lon: float) -> WeatherSnapshot:
    """
    Pobiera dane pogodowe dla podanego czasu i lokalizacji.
    Najpierw szuka w cache. W razie błędu API zwraca wartości None.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=TZ)
    else:
        timestamp = timestamp.astimezone(TZ)
        
    cache_key = f"weather_{lat:.4f}_{lon:.4f}"
    
    try:
        data = weather_cache.get_or_compute(cache_key, lambda: _fetch_open_meteo(lat, lon))
    except Exception as e:
        logger.warning(f"Błąd pobierania danych pogodowych: {e}")
        return WeatherSnapshot(
            timestamp=timestamp,
            temperature_c=None,
            apparent_temperature_c=None,
            uv_index=None,
            source="fallback",
            quality="no_data"
        )
        
    try:
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        
        # Szukamy najbliższej godziny
        target_iso = timestamp.strftime("%Y-%m-%dT%H:00")
        
        if target_iso in times:
            idx = times.index(target_iso)
            temp_list = hourly.get("temperature_2m", [])
            app_temp_list = hourly.get("apparent_temperature", [])
            uv_list = hourly.get("uv_index", [])
            
            temp = temp_list[idx] if idx < len(temp_list) else None
            app_temp = app_temp_list[idx] if idx < len(app_temp_list) else temp
            uv = uv_list[idx] if idx < len(uv_list) else None
        else:
            # Fallback do aktualnej pogody
            current = data.get("current_weather", {})
            temp = current.get("temperature")
            app_temp = temp  # Jeśli nie ma w hourly
            uv = None        # Brak UV w basic current_weather
            
        return WeatherSnapshot(
            timestamp=timestamp,
            temperature_c=float(temp) if temp is not None else None,
            apparent_temperature_c=float(app_temp) if app_temp is not None else None,
            uv_index=float(uv) if uv is not None else None,
            source="open-meteo",
            quality="model" if temp is not None else "no_data"
        )
    except Exception as e:
        logger.warning(f"Błąd parsowania danych pogodowych: {e}")
        return WeatherSnapshot(
            timestamp=timestamp,
            temperature_c=None,
            apparent_temperature_c=None,
            uv_index=None,
            source="fallback",
            quality="no_data"
        )
