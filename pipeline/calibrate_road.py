"""Kalibracja czynnika drogi f_road z danych GIOŚ (roles/02 §6.3).

Mediana godzinowego ilorazu stacji komunikacyjnej (Al. Krasińskiego) do stacji tła (ul. Bujaka)
z ostatnich N dni = empiryczny przyrost stężenia przy arterii → f_road dla primary/trunk.
Niższe klasy dostają proporcjonalnie mniejszy przyrost (te same proporcje co wartości startowe).
Wynik: app/env/road_factors.json (commitowany; exposure.py czyta go przy imporcie).
"""
import argparse
import json
from datetime import date, datetime, timedelta

import numpy as np

from app.env.exposure import ROAD_FACTORS_FILE
from app.env.fetch import gios_series
from app.env.gios_sensors import BACKGROUND_STATION, GIOS_STATIONS, TRAFFIC_STATION
from app.env.service import TZ

# udział przyrostu arterii (PM, NO2) — z wartości startowych 1.35/1.20/1.10 i 1.8/1.4/1.2
SHARE = {"primary": (1.0, 1.0), "secondary": (0.2 / 0.35, 0.4 / 0.8), "tertiary": (0.1 / 0.35, 0.2 / 0.8)}
MIN_BACKGROUND = 1.0                 # µg/m³ — pomijamy godziny z prawie zerowym mianownikiem
RATIO_RANGE = (1.0, 3.0)             # iloraz < 1 nie jest dowodem przyrostu przy drodze


def median_ratio(traffic: dict, background: dict) -> tuple[float, int]:
    r = np.array([traffic[t] / background[t] for t in traffic if background.get(t, 0) > MIN_BACKGROUND])
    if not len(r):
        raise ValueError("no overlapping hours")
    return float(np.median(r)), len(r)


def calibrate(days: int = 90, end: date | None = None) -> dict:
    end = end or datetime.now(TZ).date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    sensors = {sid: s for sid, _, _, _, s in GIOS_STATIONS}
    ratio, n_hours = {}, {}
    for k in ("pm10", "pm25", "no2"):
        if k not in sensors[BACKGROUND_STATION]:          # Bujaka: PM2.5 tylko dobowy → PM z PM10
            continue
        a = gios_series(sensors[TRAFFIC_STATION][k], start.isoformat(), end.isoformat())
        b = gios_series(sensors[BACKGROUND_STATION][k], start.isoformat(), end.isoformat())
        ratio[k], n_hours[k] = median_ratio(a, b)
    r_pm = float(np.clip(np.mean([ratio[k] for k in ("pm10", "pm25") if k in ratio]), *RATIO_RANGE))
    r_no2 = float(np.clip(ratio["no2"], *RATIO_RANGE))
    f_road = {}
    for cls, (s_pm, s_no2) in SHARE.items():
        f_road[cls] = f_road[f"{cls}_link"] = [round(1 + (r_pm - 1) * s_pm, 3), round(1 + (r_no2 - 1) * s_no2, 3)]
    f_road["trunk"] = f_road["trunk_link"] = f_road["primary"]
    return {
        "source": f"GIOŚ archivalData: stacja {TRAFFIC_STATION} (Al. Krasińskiego, komunikacyjna) / "
                  f"{BACKGROUND_STATION} (ul. Bujaka, tło), mediana ilorazów godzinowych",
        "period": [start.isoformat(), end.isoformat()],
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "median_hourly_ratio": {k: round(v, 3) for k, v in ratio.items()},
        "n_hours": n_hours,
        "f_road": f_road,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()
    out = calibrate(args.days)
    ROAD_FACTORS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("period", "median_hourly_ratio", "n_hours")}, ensure_ascii=False))
    print("f_road primary (PM, NO2):", out["f_road"]["primary"], "→", ROAD_FACTORS_FILE)


if __name__ == "__main__":
    main()
