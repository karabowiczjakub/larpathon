"""Rider profiles used by Backend for travel time, inhaled dose and ECO weight."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiderProfile:
    id: str
    speed_kmh: float
    ventilation_m3h: float  # minute ventilation while cycling
    eco_alpha: float  # ECO cost = t * (1 + alpha * excess discomfort), see engine/variants.py
    eco_air_weight: float = 0.0  # + weight * t * air penalty: exposure and hotspots of polluted air (asthma)

    @property
    def speed_ms(self) -> float:
        return self.speed_kmh / 3.6


PROFILES: dict[str, RiderProfile] = {
    p.id: p
    for p in (
        # alpha tuned on the real graph (scripts/tune_alpha.py): heatwave ECO +4-8% time (p90 <= ~20%)
        RiderProfile("standard", speed_kmh=15, ventilation_m3h=1.9, eco_alpha=5.0),
        # air weight tuned on the real graph: asthma puts air before shade; the healthier route avoids NO2
        # hotspots without detours that raise the inhaled PM2.5 (smog: dose p90 +1.2%, live: -87% poor air)
        RiderProfile("asthma", speed_kmh=14, ventilation_m3h=1.9, eco_alpha=5.0, eco_air_weight=6.0),
        RiderProfile("senior", speed_kmh=12, ventilation_m3h=1.6, eco_alpha=4.0),
        RiderProfile("athlete", speed_kmh=22, ventilation_m3h=3.2, eco_alpha=3.0),
    )
}
DEFAULT_PROFILE = "standard"
