import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import scipy

from app.graph.routing import RoutingGraph


def timing_stats(durations: list[float], target_ms: float) -> dict:
    p50, p95 = np.percentile(durations, [50, 95])
    return {
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max(durations), 2),
        "target_ms": target_ms,
        "target_met": bool(p95 < target_ms),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--samples", type=int, default=50)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    started = perf_counter()
    g = RoutingGraph.load(args.data_dir)
    load_ms = (perf_counter() - started) * 1000
    with np.load(Path(args.data_dir) / "graph.npz") as z:
        points = np.column_stack([z["node_lat"], z["node_lon"]])
    rng = np.random.default_rng(42)
    time_s = g.edge_length_m / (15 / 3.6)
    eco = time_s * (1 + 3 * rng.uniform(0, 1, g.n_edges))
    report = {
        "nodes": g.N,
        "edges": g.n_edges,
        "samples": args.samples,
        "timestamp": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "scipy": scipy.__version__,
        "platform": platform.platform(),
        "load_ms": round(load_ms, 2),
        "seed": 42,
        "workload": "random graph nodes; route plus geometry; synthetic ECO costs; one request at a time",
        "results": {},
    }
    manifest = Path(args.data_dir) / "graph_manifest.json"
    if manifest.exists():
        report["graph_sha256"] = json.loads(manifest.read_text(encoding="utf-8"))[
            "sha256"
        ]["graph.npz"]
    for count in [2, 5]:
        durations = []
        eco_durations = []
        for _ in range(args.samples + 1):
            selected = points[rng.choice(len(points), count, replace=False)].tolist()
            start = perf_counter()
            route = g.route(selected, time_s)
            g.geometry(route.eids)
            durations.append((perf_counter() - start) * 1000)
            start = perf_counter()
            route = g.route(selected, eco)
            g.geometry(route.eids)
            eco_durations.append((perf_counter() - start) * 1000)
        report["results"][str(count)] = {
            "fastest": timing_stats(durations[1:], 150),
            "eco_synthetic": timing_stats(eco_durations[1:], 150),
            "fastest_and_eco": timing_stats(
                [a + b for a, b in zip(durations[1:], eco_durations[1:])], 300
            ),
        }
    start = perf_counter()
    g.route([points[0].tolist()] * 5, time_s)
    report["identical_points_ms"] = round((perf_counter() - start) * 1000, 2)
    output = Path(args.data_dir) / "routing_benchmark.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
