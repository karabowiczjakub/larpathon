import logging
from dataclasses import dataclass
from datetime import datetime
import math
import zoneinfo
import requests

from src.services.cache import pollution_cache
from src.environment.normalization import normalize_pollution_score

logger = logging.getLogger(__name__)
TZ = zoneinfo.ZoneInfo("Europe/Warsaw")

# Krakowskie stacje GIOŚ wg dokumentacji (dla uproszczenia kilka kluczowych)
GIOS_STATIONS = [
    (400,   "Al. Krasińskiego",      50.057678, 19.926189, {"pm10": 2750,  "pm25": 2752, "no2": 2747}),
    (401,   "ul. Bujaka",            50.010575, 19.949189, {"pm10": 2771,  "pm25": 2773, "no2": 2766}),
    (402,   "ul. Bulwarowa",         50.069308, 20.053492, {"pm10": 2793,  "pm25": 2794, "no2": 2788}),
]

@dataclass
class PollutionSnapshot:
    pollution_by_edge: dict[str, float]
    pollution_source: str
    pollution_quality: str

def _fetch_gios_data() -> list[dict]:
    """Pobiera dane z krakowskich stacji GIOŚ."""
    results = []
    base_url = "https://api.gios.gov.pl/pjp-api/v1/rest/data/getData"
    
    for sid, name, lat, lon, sensors in GIOS_STATIONS:
        station_data = {"lat": lat, "lon": lon, "pm10": None, "pm25": None, "no2": None}
        has_data = False
        
        for pol, sensor_id in sensors.items():
            try:
                response = requests.get(f"{base_url}/{sensor_id}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    measurements = data.get("Lista danych pomiarowych", [])
                    # Szukamy najświeższej wartości nie-null
                    for m in measurements:
                        val = m.get("Wartość")
                        if val is not None:
                            station_data[pol] = float(val)
                            has_data = True
                            break
            except Exception as e:
                logger.debug(f"Błąd GIOŚ dla sensora {sensor_id}: {e}")
                
        if has_data:
            results.append(station_data)
            
    if not results:
        raise ValueError("Brak danych z GIOŚ")
        
    return results

def _fetch_open_meteo_aq(lat: float, lon: float) -> dict:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10,pm2_5,nitrogen_dioxide",
        "timezone": "Europe/Warsaw"
    }
    
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    hourly = data.get("hourly", {})
    
    # Pobierzmy po prostu pierwszy dostępny rekord dla prostoty fallbacku
    if hourly and "pm10" in hourly and hourly["pm10"]:
        for i in range(len(hourly["pm10"])):
            if hourly["pm10"][i] is not None:
                return {
                    "lat": lat, "lon": lon,
                    "pm10": hourly.get("pm10", [])[i],
                    "pm25": hourly.get("pm2_5", [])[i],
                    "no2": hourly.get("nitrogen_dioxide", [])[i]
                }
    
    raise ValueError("Brak danych z Open-Meteo AQ")

def _haversine(lat1, lon1, lat2, lon2):
    """Zwraca odległość w metrach."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def _interpolate_idw(points: list[dict], target_lat: float, target_lon: float, power: float = 2.0) -> dict:
    """Prosta interpolacja IDW z listy punktów posiadających pm10, pm25, no2."""
    if not points:
        return {"pm10": None, "pm25": None, "no2": None}
        
    weights = []
    for p in points:
        d = _haversine(target_lat, target_lon, p["lat"], p["lon"])
        if d < 10:  # Zabezpieczenie przed dzieleniem przez zero
            return {"pm10": p.get("pm10"), "pm25": p.get("pm25"), "no2": p.get("no2")}
        weights.append(1.0 / (d ** power))
        
    total_w = sum(weights)
    result = {"pm10": 0.0, "pm25": 0.0, "no2": 0.0}
    weight_sums = {"pm10": 0.0, "pm25": 0.0, "no2": 0.0}
    
    for w, p in zip(weights, points):
        for k in ["pm10", "pm25", "no2"]:
            if p.get(k) is not None:
                result[k] += p[k] * w
                weight_sums[k] += w
                
    for k in ["pm10", "pm25", "no2"]:
        if weight_sums[k] > 0:
            result[k] /= weight_sums[k]
        else:
            result[k] = None
            
    return result

def get_pollution_snapshot(timestamp: datetime, edge_points: dict[str, tuple[float, float]]) -> PollutionSnapshot:
    """
    Pobiera i interpoluje zanieczyszczenia dla podanych krawędzi grafu.
    Stosuje sekwencyjny fallback: GIOŚ -> Open-Meteo AQ -> neutralne 0.5.
    """
    pollution_by_edge = {}
    
    try:
        # Próba GIOŚ
        stations_data = pollution_cache.get_or_compute("gios_data", _fetch_gios_data)
        
        for edge_id, (lat, lon) in edge_points.items():
            interpolated = _interpolate_idw(stations_data, lat, lon)
            score = normalize_pollution_score(
                interpolated.get("pm25"), 
                interpolated.get("pm10"), 
                interpolated.get("no2")
            )
            pollution_by_edge[edge_id] = score
            
        return PollutionSnapshot(
            pollution_by_edge=pollution_by_edge,
            pollution_source="GIOS",
            pollution_quality="interpolated"
        )
        
    except Exception as e:
        logger.warning(f"Fallback z GIOŚ z powodu błędu: {e}")
        
    # Fallback 1: Open-Meteo AQ
    try:
        # Zakładamy, że pobieramy tło dla centrum Krakowa (50.06, 19.94) dla wszystkich krawędzi w fallbacku
        om_data = pollution_cache.get_or_compute("open_meteo_aq", lambda: _fetch_open_meteo_aq(50.06, 19.94))
        
        score = normalize_pollution_score(om_data.get("pm25"), om_data.get("pm10"), om_data.get("no2"))
        
        for edge_id in edge_points.keys():
            pollution_by_edge[edge_id] = score
            
        return PollutionSnapshot(
            pollution_by_edge=pollution_by_edge,
            pollution_source="OpenMeteoAQ",
            pollution_quality="fallback"
        )
        
    except Exception as e:
        logger.warning(f"Ostateczny fallback dla AQ z powodu błędu: {e}")
        
    # Fallback 2: Wartość neutralna 0.5
    for edge_id in edge_points.keys():
        pollution_by_edge[edge_id] = 0.5
        
    return PollutionSnapshot(
        pollution_by_edge=pollution_by_edge,
        pollution_source="fallback",
        pollution_quality="neutral"
    )
