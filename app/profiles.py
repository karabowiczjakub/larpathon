"""Rider profiles used by Backend for travel time, inhaled dose and ECO weight."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiderProfile:
    id: str
    speed_kmh: float
    ventilation_m3h: float  # minute ventilation while cycling
    eco_alpha: float  # ECO cost = t * (1 + alpha * discomfort)

    @property
    def speed_ms(self) -> float:
        return self.speed_kmh / 3.6


PROFILES: dict[str, RiderProfile] = {
    p.id: p
    for p in (
        RiderProfile("standard", speed_kmh=15, ventilation_m3h=1.9, eco_alpha=3.0),
        RiderProfile("asthma", speed_kmh=14, ventilation_m3h=1.9, eco_alpha=5.0),
        RiderProfile("senior", speed_kmh=12, ventilation_m3h=1.6, eco_alpha=5.0),
        RiderProfile("athlete", speed_kmh=22, ventilation_m3h=3.2, eco_alpha=2.0),
    )
}
DEFAULT_PROFILE = "standard"
