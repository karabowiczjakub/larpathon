import math

def clamp(val: float, min_val: float, max_val: float) -> float:
    if math.isnan(val):
        return 0.0
    return max(min_val, min(val, max_val))

def compute_heat_factor(temp_c: float | None) -> float:
    """
    Oblicza heat_factor [0, 1] na podstawie temperatury.
    Zakłada wzrost liniowy od 20°C (0.0) do 40°C (1.0).
    """
    if temp_c is None or math.isnan(temp_c):
        return 0.0
    
    factor = (temp_c - 20.0) / 20.0
    return clamp(factor, 0.0, 1.0)

def compute_uv_factor(uv_index: float | None) -> float:
    """
    Oblicza uv_factor [0, 1] na podstawie indeksu UV.
    Zakłada wzrost liniowy od UV 0 (0.0) do UV 11 (1.0).
    """
    if uv_index is None or math.isnan(uv_index):
        return 0.0
    
    factor = uv_index / 11.0
    return clamp(factor, 0.0, 1.0)

def normalize_pollution_score(pm25: float | None = None, pm10: float | None = None, no2: float | None = None) -> float:
    """
    Zwraca znormalizowany pollution_score w przedziale [0, 1].
    Wykorzystuje przybliżone progi jakości powietrza dla określenia najgorszego składnika.
    """
    scores = []
    
    if pm25 is not None and not math.isnan(pm25):
        # max ~ 75+ (bardzo zły) -> 1.0
        scores.append(clamp(pm25 / 75.0, 0.0, 1.0))
        
    if pm10 is not None and not math.isnan(pm10):
        # max ~ 150+ (bardzo zły) -> 1.0
        scores.append(clamp(pm10 / 150.0, 0.0, 1.0))
        
    if no2 is not None and not math.isnan(no2):
        # max ~ 340+ (bardzo zły) -> 1.0
        scores.append(clamp(no2 / 340.0, 0.0, 1.0))
        
    if not scores:
        return 0.0
        
    return max(scores)
