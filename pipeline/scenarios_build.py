import json
from pathlib import Path
from app.env.fetch import fetch_hours

SCEN = [
    dict(id="heatwave_2025-07-03", label="Heatwave · 3 Jul 2025", day="2025-07-03", default_at="2025-07-03T14:00:00+02:00"),
    dict(id="smog_2025-01-20",     label="Smog · 20 Jan 2025",    day="2025-01-20", default_at="2025-01-20T17:00:00+01:00"),
]

def build_scenarios():
    Path("scenarios").mkdir(exist_ok=True)
    for s in SCEN:
        print(f"Building scenario {s['id']}...")
        hours = fetch_hours(start=s["day"], end=s["day"])
        Path(f"scenarios/{s['id']}.json").write_text(json.dumps({**s, "hours": hours}, ensure_ascii=False, indent=1))
        h = hours[s["default_at"][:16]]
        print(s["id"], "→", {k: h[k] for k in ("temperature_2m", "uv_index", "pm10_cams", "pm10_city", "pm10_ratio")})

if __name__ == "__main__":
    build_scenarios()
