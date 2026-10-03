"""MockEnv: fixed conditions for live and the two demo scenarios, with a simple daily cycle."""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from ..contracts import EnvironmentalContext

TZ = ZoneInfo("Europe/Warsaw")
SCENARIOS = (
    {"id": "live", "label": "Live now"},
    {"id": "heatwave_2025-07-03", "label": "Heatwave · 3 Jul 2025", "default_at": "2025-07-03T14:00:00+02:00"},
    {"id": "smog_2025-01-20", "label": "Smog · 20 Jan 2025", "default_at": "2025-01-20T17:00:00+01:00"},
)
# Conditions at the scenario's default hour (live: a mild October day at 13:00).
PEAK = {
    "live": dict(temperature_c=14.0, humidity_pct=65, wind_ms=2.5, shortwave_wm2=350, dni_wm2=400,
                 uv_index=2.5, pm25=15.0, pm10=24.0, no2=22.0),
    "heatwave_2025-07-03": dict(temperature_c=34.5, humidity_pct=20, wind_ms=4.8, shortwave_wm2=862,
                                dni_wm2=853, uv_index=8.1, pm25=12.0, pm10=21.0, no2=18.0),
    "smog_2025-01-20": dict(temperature_c=-2.0, humidity_pct=85, wind_ms=0.8, shortwave_wm2=0, dni_wm2=0,
                            uv_index=0.0, pm25=63.2, pm10=95.0, no2=52.0),
}
LIVE_DEFAULT_HOUR = 13


def _daylight(hour: float) -> float:
    return max(0.0, math.cos(math.pi * (hour - 13.5) / 15))


class MockEnv:
    def scenarios(self) -> list[dict]:
        return [dict(s) for s in SCENARIOS]

    def get(self, scenario: str, at: datetime | None) -> EnvironmentalContext:
        if scenario not in PEAK:
            scenario = "live"
        default = self._default_at(scenario)
        at = (at or default).astimezone(TZ).replace(minute=0, second=0, microsecond=0)
        base = PEAK[scenario]
        d_now, d_ref = _daylight(at.hour), _daylight(default.hour)
        sun_scale = d_now / d_ref if d_ref > 0 else 0.0
        values = {
            **base,
            "temperature_c": round(base["temperature_c"] + 6 * (d_now - d_ref), 1),
            "shortwave_wm2": round(base["shortwave_wm2"] * sun_scale),
            "dni_wm2": round(base["dni_wm2"] * sun_scale),
            "uv_index": round(base["uv_index"] * sun_scale, 1),
        }
        return EnvironmentalContext(timestamp=at, source="mock", **values)

    @staticmethod
    def _default_at(scenario: str) -> datetime:
        for s in SCENARIOS:
            if s["id"] == scenario and "default_at" in s:
                return datetime.fromisoformat(s["default_at"])
        return datetime.now(TZ).replace(hour=LIVE_DEFAULT_HOUR)
