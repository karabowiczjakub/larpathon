import math
from src.environment.normalization import compute_heat_factor, compute_uv_factor, normalize_pollution_score

def test_compute_heat_factor():
    assert compute_heat_factor(20.0) == 0.0
    assert compute_heat_factor(30.0) == 0.5
    assert compute_heat_factor(40.0) == 1.0
    assert compute_heat_factor(10.0) == 0.0  # clamp
    assert compute_heat_factor(50.0) == 1.0  # clamp
    assert compute_heat_factor(None) == 0.0
    assert compute_heat_factor(float('nan')) == 0.0

def test_compute_uv_factor():
    assert compute_uv_factor(0.0) == 0.0
    assert compute_uv_factor(5.5) == 0.5
    assert compute_uv_factor(11.0) == 1.0
    assert compute_uv_factor(15.0) == 1.0  # clamp
    assert compute_uv_factor(None) == 0.0
    assert compute_uv_factor(float('nan')) == 0.0

def test_normalize_pollution_score():
    # Brak danych
    assert normalize_pollution_score() == 0.0
    
    # Skrajne maksima (wynik = 1.0)
    assert normalize_pollution_score(pm25=75.0) == 1.0
    assert normalize_pollution_score(pm10=150.0) == 1.0
    assert normalize_pollution_score(no2=340.0) == 1.0
    
    # Środkowe wartości
    assert normalize_pollution_score(pm25=37.5) == 0.5
    
    # Najgorszy decyduje
    assert normalize_pollution_score(pm25=37.5, pm10=150.0) == 1.0
    
    # Pomiary powyżej maksimum
    assert normalize_pollution_score(pm25=100.0) == 1.0
    
    # Obsługa None i NaN
    assert normalize_pollution_score(pm25=None, pm10=float('nan'), no2=170.0) == 0.5
