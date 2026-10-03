"""Fakty środowiskowe na slajd: CAMS vs GIOŚ, kalibracja f_road, progi norm i wykresy dyskomfortu."""

import argparse
import json
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.env import exposure as ex
from app.env.fuzzy_profiles import PROFILES
from app.env.gios_sensors import TRAFFIC_STATION
from app.env.service import EnvironmentService

ROOT = Path(__file__).resolve().parents[1]
MOMENTS = {"heatwave_2025-07-03": ["2025-07-03T14:00"], "smog_2025-01-20": ["2025-01-20T17:00", "2025-01-20T22:00"]}
NORMS = {
    "UTCI [°C] (Bröde i in. 2012)": "26 umiarkowany · 32 silny · 38 bardzo silny · 46 ekstremalny stres cieplny",
    "EAQI PM2.5 [µg/m³] (EEA 2024)": "5 · 15 · 50 · 90 · 140 (good | fair | moderate | poor | very poor | extremely poor)",
    "EAQI PM10 [µg/m³] (EEA 2024)": "15 · 45 · 120 · 195 · 270",
    "EAQI NO2 [µg/m³] (EEA 2024)": "10 · 25 · 60 · 100 · 150",
    "UV index (WHO)": "0–2 niski · 3–5 umiarkowany · 6–7 wysoki · 8–10 bardzo wysoki · 11+ ekstremalny",
}


def cams_vs_gios(scenario_dir: Path) -> list[dict]:
    rows = []
    for scenario, keys in MOMENTS.items():
        hours = json.loads((scenario_dir / f"{scenario}.json").read_text(encoding="utf-8"))["hours"]
        for key in keys:
            h = hours[key]
            traffic = next((s for s in h["stations"] if s["station_id"] == TRAFFIC_STATION), {})
            rows.append({"scenario": scenario, "hour": key, "stations": len(h["stations"]),
                         **{f"{k}_cams": h[f"{k}_cams"] for k in ex.POLLUTANTS},
                         **{f"{k}_gios_median": round(h[f"{k}_city"], 1) for k in ex.POLLUTANTS},
                         **{f"{k}_krasinskiego": traffic.get(k) for k in ex.POLLUTANTS},
                         "pm10_cams_over_gios": round(h["pm10_cams"] / h["pm10_city"], 2)})
    return rows


def discomfort_curves() -> dict:
    utci, air = np.arange(-10, 46.0, 0.5), np.arange(0, 6.01, 0.05)
    return {
        "utci": utci.tolist(), "air": air.tolist(),
        "vs_heat": {p: ex.discomfort(p, utci, np.full_like(utci, 1.0), np.full_like(utci, 2.0)).tolist() for p in PROFILES},
        "vs_air": {p: ex.discomfort(p, np.full_like(air, 20.0), air, np.full_like(air, 1.0)).tolist() for p in PROFILES},
    }


def plot(curves: dict, output: Path) -> None:
    fig = Figure(figsize=(11, 4.2), layout="constrained")
    FigureCanvasAgg(fig)
    ax_heat, ax_air = fig.subplots(1, 2, sharey=True)
    for p in PROFILES:
        ax_heat.plot(curves["utci"], np.array(curves["vs_heat"][p]) * 10, label=p)
        ax_air.plot(curves["air"], np.array(curves["vs_air"][p]) * 10, label=p)
    for x in (26, 32, 38):
        ax_heat.axvline(x, color="0.85", lw=0.8, zorder=0)
    ax_heat.set(xlabel="UTCI [°C]  (air index 1, UV 2)", ylabel="Discomfort 0–10", title="Heat")
    ax_air.set(xlabel="Continuous EAQI 0–6  (UTCI 20 °C, UV 1)", title="Air")
    ax_air.legend(frameon=False)
    fig.savefig(output, dpi=150)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenarios", type=Path, default=ROOT / "scenarios")
    ap.add_argument("--out", type=Path, default=ROOT / "docs")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    EnvironmentService(args.scenarios, args.out, refresh=False)             # walidacja plików scenariuszy
    road = json.loads(ex.ROAD_FACTORS_FILE.read_text(encoding="utf-8")) if ex.ROAD_FACTORS_FILE.exists() else None
    curves = discomfort_curves()
    report = {"cams_vs_gios": cams_vs_gios(args.scenarios), "road_calibration": road, "norms": NORMS,
              "discomfort_curves": curves}
    (args.out / "env_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    plot(curves, args.out / "env_discomfort.png")

    print("| scenariusz | godzina | PM10 CAMS | PM10 GIOŚ (mediana) | PM10 Krasińskiego | CAMS/GIOŚ |")
    print("|---|---|---|---|---|---|")
    for r in report["cams_vs_gios"]:
        print(f"| {r['scenario']} | {r['hour'][11:]} | {r['pm10_cams']} | {r['pm10_gios_median']} | "
              f"{r['pm10_krasinskiego']} | {r['pm10_cams_over_gios']}× |")
    if road:
        print(f"\nf_road z GIOŚ {road['period'][0]}…{road['period'][1]}: mediana Krasińskiego/Bujaka "
              f"{road['median_hourly_ratio']} (godzin: {road['n_hours']}) → primary (PM, NO2) = {road['f_road']['primary']}")
    print(f"\n→ {args.out / 'env_report.json'}, {args.out / 'env_discomfort.png'}")


if __name__ == "__main__":
    main()
