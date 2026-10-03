import json
from pathlib import Path

from app.env.fetch import fetch_hours

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


if __name__ == "__main__":
    build_scenarios()
