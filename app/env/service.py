from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..contracts import EnvironmentalContext, StationReading, WeatherPoint
from .fetch import GRID_POINTS, fetch_hours

TZ = ZoneInfo("Europe/Warsaw")
log = logging.getLogger(__name__)
TTL_S = 30 * 60
RETRY_S = 120
DEFAULT_SCENARIO = "heatwave_2025-07-03"
NEUTRAL_HOUR = {"temperature_2m": 20.0, "relative_humidity_2m": 50.0, "wind_speed_10m": 2.0, "shortwave_radiation": 500.0,
                    "direct_normal_irradiance": 500.0, "uv_index": 5.0, "pm25_city": 15.0, "pm10_city": 25.0, "no2_city": 20.0}


class EnvironmentService:
    def __init__(self, scenario_dir: str, data_dir: str, refresh: bool = True):
        self.scen = {s["id"]: s for s in (json.loads(p.read_text(encoding="utf-8"))
                                          for p in sorted(Path(scenario_dir).glob("*.json")))}
        self.live_path = Path(data_dir) / "last_live.json"
        self.live: dict | None = None
        if self.live_path.exists():
            try:
                self.live = json.loads(self.live_path.read_text())
            except (OSError, ValueError):
                log.warning("unreadable %s, ignoring", self.live_path)
        if refresh:
            threading.Thread(target=self._refresh_loop, daemon=True, name="env-refresh").start()

    # ---------- API dla Backendu ----------
    def scenarios(self) -> list[dict]:
        out = [{"id": "live", "label": "Live now"}]
        out += [{"id": s["id"], "label": s["label"], "default_at": s["default_at"]} for s in self.scen.values()]
        return out

    def get(self, scenario: str, at: datetime | None) -> EnvironmentalContext:
        if scenario != "live" and scenario in self.scen:
            s = self.scen[scenario]
            default = datetime.fromisoformat(s["default_at"])
            return self._ctx_from_hours(s["hours"], _on_day(at, default) if at else default, "scenario", 0.0)
        live = self.live
        if live is None:                                                  # nic nie mamy → scenariusz
            s = self.scen.get(DEFAULT_SCENARIO)
            if s:
                return self._ctx_from_hours(s["hours"], datetime.fromisoformat(s["default_at"]), "fallback", 0.0)
            at = _local(at or datetime.now(TZ))
            return self._ctx_from_hours({at.strftime("%Y-%m-%dT%H:00"): NEUTRAL_HOUR}, at, "fallback", 0.0)
        age = time.time() - live["fetched_at"]
        return self._ctx_from_hours(live["hours"], at or datetime.now(TZ), "live" if age < 3 * TTL_S else "fallback", age)

    # ---------- pobieranie ----------
    def refresh(self) -> bool:
        try:
            hours = fetch_hours(past_days=1, forecast_days=2)
        except Exception:
            log.exception("live env refresh failed — using last known / fallback")
            return False
        data = {"fetched_at": time.time(), "hours": hours}
        self.live = data
        try:
            self.live_path.parent.mkdir(parents=True, exist_ok=True)
            self.live_path.write_text(json.dumps(data))
        except OSError:
            log.warning("cannot write %s", self.live_path, exc_info=True)
        log.info("live env refreshed: %d hours", len(hours))
        return True

    def _refresh_loop(self):
        while True:
            time.sleep(TTL_S if self.refresh() else RETRY_S)

    @staticmethod
    def _ctx_from_hours(hours: dict, at: datetime, source: str, age: float) -> EnvironmentalContext:
        at = _local(at)
        key = min(hours, key=lambda k: abs(datetime.fromisoformat(k).replace(tzinfo=TZ) - at))
        h = hours[key]
        st = tuple(StationReading(**x) for x in h.get("stations", []))
        g = h.get("grid") or {}
        grid = tuple(WeatherPoint(la, lo, dt, wr) for (la, lo), dt, wr in zip(GRID_POINTS, g.get("dt", ()), g.get("wr", ())))
        return EnvironmentalContext(
            timestamp=datetime.fromisoformat(key).replace(tzinfo=TZ), source=source,
            temperature_c=h["temperature_2m"], humidity_pct=h["relative_humidity_2m"],
            wind_ms=h["wind_speed_10m"], shortwave_wm2=h["shortwave_radiation"] or 0.0,
            dni_wm2=h["direct_normal_irradiance"] or 0.0, uv_index=h["uv_index"] or 0.0,
            pm25=h["pm25_city"], pm10=h["pm10_city"], no2=h["no2_city"],
            stations=st, data_age_s=age, weather_grid=grid)


def _local(at: datetime) -> datetime:
    return at.replace(tzinfo=TZ) if at.tzinfo is None else at.astimezone(TZ)


def _on_day(at: datetime, default: datetime) -> datetime:
    """Scenariusz to jedna doba: z `at` bierzemy godzinę zegarową, dzień — ze scenariusza (suwak godziny)."""
    day = default.astimezone(TZ)
    return _local(at).replace(year=day.year, month=day.month, day=day.day)
