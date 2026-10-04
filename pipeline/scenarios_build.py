import json
import sys
from pathlib import Path

from app.env.fetch import HISTORICAL_FORECAST_URL, fetch_grid, fetch_hours

OUT = Path(__file__).resolve().parents[1] / "scenarios"
SCEN = [
    {"id": "heatwave_2025-07-03", "label": "Heatwave · 3 Jul 2025", "day": "2025-07-03", "default_at": "2025-07-03T14:00:00+02:00"},
    {"id": "smog_2025-01-20",     "label": "Smog · 20 Jan 2025",    "day": "2025-01-20", "default_at": "2025-01-20T17:00:00+01:00"},
]


def build_scenarios():
    OUT.mkdir(exist_ok=True)
    for s in SCEN:
        print(f"Building scenario {s['id']}...")
        hours = fetch_hours(start=s["day"], end=s["day"])
        assert len(hours) == 24, f"{s['id']}: expected 24 hours, got {len(hours)}"
        (OUT / f"{s['id']}.json").write_text(json.dumps({**s, "hours": hours}, ensure_ascii=False, indent=1), encoding="utf-8")
        h = hours[s["default_at"][:16]]
        print(s["id"], "→", {k: h[k] for k in ("temperature_2m", "uv_index", "pm10_cams", "pm10_city", "pm10_ratio")},
              "stations/h:", min(len(x["stations"]) for x in hours.values()), "-", max(len(x["stations"]) for x in hours.values()))


def add_weather_grid():
    """Dopisuje siatkę pogody do istniejących scenariuszy bez ponownego pobierania GIOŚ (wartości dla
    miasta zostają bez zmian; siatka to tylko różnice względem punktu miasta)."""
    for s in SCEN:
        path = OUT / f"{s['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        grid = fetch_grid({"start_date": s["day"], "end_date": s["day"]}, HISTORICAL_FORECAST_URL)
        missing = [t for t in data["hours"] if t not in grid]
        assert not missing, f"{s['id']}: no grid for {missing}"
        for t, h in data["hours"].items():
            h["grid"] = grid[t]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        dts = [v for t in data["hours"] for v in grid[t]["dt"]]
        print(s["id"], "grid added: dT", round(min(dts), 1), "…", round(max(dts), 1), "°C")


if __name__ == "__main__":
    add_weather_grid() if "--grid-only" in sys.argv else build_scenarios()
