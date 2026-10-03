"""Tune the ECO weight alpha and measure latency (roles/04 §7 and the 50-route benchmark).

    .venv/bin/python scripts/tune_alpha.py --pairs 30 --alphas 1 2 3 5 8
    USE_MOCKS=1 .venv/bin/python scripts/tune_alpha.py

Uses the same modules as the app (config/env vars). Goal: ECO 5-25% longer, clearly better on discomfort.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.profiles import PROFILES  # noqa: E402
from app.providers import build_modules  # noqa: E402
from app.schemas import RouteRequest  # noqa: E402

M_PER_DEG_LAT = 111_320.0


def random_pairs(graph, n: int, min_m: float, max_m: float, seed: int) -> list[tuple[dict, dict]]:
    rng = np.random.default_rng(seed)
    mids = np.asarray(graph.edge_mid_lonlat, dtype=np.float64)
    pairs = []
    while len(pairs) < n:
        a, b = mids[rng.integers(len(mids), size=2)]
        dx = (a[0] - b[0]) * M_PER_DEG_LAT * np.cos(np.radians(a[1]))
        dy = (a[1] - b[1]) * M_PER_DEG_LAT
        if min_m <= np.hypot(dx, dy) <= max_m:
            pairs.append(({"lat": a[1], "lon": a[0]}, {"lat": b[1], "lon": b[0]}))
    return pairs


def evaluate(modules, pairs, scenario: str, profile: str, alpha: float) -> dict:
    profiles = {**PROFILES, profile: replace(PROFILES[profile], eco_alpha=alpha)}
    engine = Engine(modules, profiles=profiles)
    rows, times = [], []
    for a, b in pairs:
        try:
            d = engine.route(RouteRequest(points=[a, b], scenario=scenario, profile=profile))
        except Exception as e:  # a pair outside the network etc.
            logging.debug("skipped pair: %s", e)
            continue
        f, e_ = (r["metrics"] for r in d["routes"])
        c = d["comparison"]
        rows.append((c["same_route"], c["time_delta_pct"], f["avg_discomfort"] - e_["avg_discomfort"],
                     c["shade_delta_pp"], c["pm25_dose_delta_pct"]))
        times.append(d["timing_ms"]["total"])
    if not rows:
        return {}
    same, dt, dd, ds, dpm = (np.array(col, dtype=float) for col in zip(*rows, strict=True))
    return {
        "alpha": alpha, "n": len(rows), "same_%": 100 * same.mean(),
        "dtime_med_%": np.median(dt), "dtime_p90_%": np.percentile(dt, 90),
        "ddiscomfort_med": np.median(dd), "dshade_med_pp": np.median(ds), "dpm25_med_%": np.median(dpm),
        "p50_ms": np.percentile(times, 50), "p95_ms": np.percentile(times, 95),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=int, default=30)
    ap.add_argument("--alphas", type=float, nargs="+", default=[1, 2, 3, 5, 8])
    ap.add_argument("--scenario", default="heatwave_2025-07-03")
    ap.add_argument("--profile", default="standard", choices=sorted(PROFILES))
    ap.add_argument("--min-km", type=float, default=1.5)
    ap.add_argument("--max-km", type=float, default=6.0)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    modules = build_modules(config.from_env())
    print(f"modules: {modules.status}  edges: {modules.graph.n_edges}  scenario: {args.scenario}")
    pairs = random_pairs(modules.graph, args.pairs, args.min_km * 1000, args.max_km * 1000, args.seed)
    results = [r for alpha in args.alphas if (r := evaluate(modules, pairs, args.scenario, args.profile, alpha))]
    if not results:
        sys.exit("no routable pairs")
    cols = list(results[0])
    print(" | ".join(f"{c:>15}" for c in cols))
    for r in results:
        print(" | ".join(f"{r[c]:>15.1f}" if isinstance(r[c], float) else f"{r[c]:>15}" for c in cols))


if __name__ == "__main__":
    main()
