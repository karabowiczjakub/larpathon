from __future__ import annotations
import json, logging, threading, time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from ..contracts import EnvironmentalContext, StationReading
from .fetch import fetch_hours

TZ = ZoneInfo("Europe/Warsaw")
log = logging.getLogger(__name__)
LAT, LON = 50.06, 19.94
TTL_S = 30 * 60
DEFAULT_SCENARIO = "heatwave_2025-07-03"

class EnvironmentService:
    def __init__(self, scenario_dir: str, data_dir: str):
        self.scen = {s["id"]: s for s in (json.loads(p.read_text()) for p in Path(scenario_dir).glob("*.json"))}
        self.live_path = Path(data_dir) / "last_live.json"
        self.live: dict | None = json.loads(self.live_path.read_text()) if self.live_path.exists() else None
        self._fetched_at = 0.0
        self._lock = threading.Lock()
        self._refreshing = False
        threading.Thread(target=self._refresh, daemon=True).start()     # pierwsze pobranie w tle

    # ---------- API dla Backendu ----------
    def scenarios(self) -> list[dict]:
        out = [{"id": "live", "label": "Live now"}]
        out += [{"id": s["id"], "label": s["label"], "default_at": s["default_at"]} for s in self.scen.values()]
        return out

    def get(self, scenario: str, at: datetime | None) -> EnvironmentalContext:
        if scenario != "live" and scenario in self.scen:
            s = self.scen[scenario]
            at = at or datetime.fromisoformat(s["default_at"])
            return self._ctx_from_hours(s["hours"], at, "scenario", 0.0)
        # live
        if time.time() - self._fetched_at > TTL_S and not self._refreshing:
            threading.Thread(target=self._refresh, daemon=True).start()   # stale-while-revalidate
        live = self.live
        if live is None:                                                  # nic nie mamy → scenariusz
            s = self.scen.get(DEFAULT_SCENARIO)
            if s:
                return self._ctx_from_hours(s["hours"], datetime.fromisoformat(s["default_at"]), "fallback", 0.0)
            else:
                return EnvironmentalContext(
                    timestamp=at or datetime.now(TZ), source="fallback",
                    temperature_c=20.0, humidity_pct=50.0, wind_ms=2.0, shortwave_wm2=500.0,
                    dni_wm2=500.0, uv_index=5.0, pm25=15.0, pm10=25.0, no2=20.0, stations=()
                )
        age = time.time() - live["fetched_at"]
        return self._ctx_from_hours(live["hours"], at or datetime.now(TZ), "live" if age < 3 * TTL_S else "fallback", age)

    # ---------- pobieranie ----------
    def _refresh(self):
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        try:
            hours = fetch_hours(past_days=1, forecast_days=2)
            data = {"fetched_at": time.time(), "hours": hours}
            self.live = data
            self.live_path.write_text(json.dumps(data))
            self._fetched_at = time.time()
            log.info("live env refreshed: %d hours", len(hours))
        except Exception:
            log.exception("live env refresh failed — using last known / fallback")
            self._fetched_at = time.time() - TTL_S + 120      # spróbuj znów za 2 min
        finally:
            self._refreshing = False

    @staticmethod
    def _ctx_from_hours(hours: dict, at: datetime, source: str, age: float) -> EnvironmentalContext:
        at = at.astimezone(TZ)
        key = min(hours, key=lambda k: abs(datetime.fromisoformat(k).replace(tzinfo=TZ) - at))
        h = hours[key]
        st = tuple(StationReading(**x) for x in h.get("stations", []))
        return EnvironmentalContext(
            timestamp=datetime.fromisoformat(key).replace(tzinfo=TZ), source=source,
            temperature_c=h["temperature_2m"], humidity_pct=h["relative_humidity_2m"],
            wind_ms=h["wind_speed_10m"], shortwave_wm2=h["shortwave_radiation"],
            dni_wm2=h["direct_normal_irradiance"], uv_index=h["uv_index"] or 0.0,
            pm25=h["pm25_city"], pm10=h["pm10_city"], no2=h["no2_city"],
            stations=st, data_age_s=age)
