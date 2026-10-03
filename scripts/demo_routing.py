import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from app.graph.routing import RoutingGraph


def compare_routes(
    graph: RoutingGraph,
    points: list[tuple[float, float]],
    discomfort: np.ndarray,
    speed_kmh: float = 15,
    alpha: float = 3,
) -> dict:
    if np.iscomplexobj(discomfort):
        raise ValueError("discomfort values must be real numbers")
    discomfort = np.asarray(discomfort, dtype=np.float64)
    if (
        discomfort.shape != (graph.n_edges,)
        or not np.isfinite(discomfort).all()
        or (discomfort < 0).any()
        or (discomfort > 1).any()
    ):
        raise ValueError("discomfort must contain one finite value in [0, 1] per eid")
    if not np.isfinite([speed_kmh, alpha]).all() or speed_kmh <= 0 or alpha < 0:
        raise ValueError("speed must be positive and alpha nonnegative")
    travel_time = graph.edge_length_m / (speed_kmh / 3.6)
    features = []
    paths = []
    started = perf_counter()
    for name, costs in [
        ("fastest", travel_time),
        ("eco", travel_time * (1 + alpha * discomfort)),
    ]:
        route = graph.route(points, costs)
        paths.append(route.eids)
        time_s = float(travel_time[route.eids].sum())
        exposure = float((travel_time[route.eids] * discomfort[route.eids]).sum())
        coords = graph.geometry(route.eids)
        if not coords:
            coords = [graph.node_lonlat[route.node_path[0]].tolist()] * 2
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": name,
                    "distance_m": float(graph.edge_length_m[route.eids].sum()),
                    "time_s": time_s,
                    "exposure_s": exposure,
                    "avg_discomfort": exposure / time_s if time_s else 0,
                    "edge_count": len(route.eids),
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "same_route": bool(np.array_equal(*paths)),
        "routing_ms": round((perf_counter() - started) * 1000, 2),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compare FASTEST/ECO on the real graph"
    )
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument(
        "--point", action="append", help="lat,lon; provide 2 to 5 times"
    )
    parser.add_argument("--speed-kmh", type=float, default=15)
    parser.add_argument("--alpha", type=float, default=3)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--discomfort", help="real environment .npy array in frozen eid order"
    )
    source.add_argument(
        "--synthetic",
        action="store_true",
        help="test costs; these are not environmental measurements",
    )
    parser.add_argument("--output", default="data/processed/routing_comparison.geojson")
    args = parser.parse_args()
    graph = RoutingGraph.load(args.data_dir)
    points = (
        [tuple(map(float, p.split(","))) for p in args.point]
        if args.point
        else [(50.0614, 19.9366), (50.0647, 19.9239)]
    )
    discomfort = (
        np.random.default_rng(42).uniform(0, 1, graph.n_edges)
        if args.synthetic
        else np.load(args.discomfort)
    )
    report = compare_routes(graph, points, discomfort, args.speed_kmh, args.alpha)
    report["discomfort_source"] = (
        "synthetic_test" if args.synthetic else str(args.discomfort)
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "routes": [f["properties"] for f in report["features"]],
                "same_route": report["same_route"],
                "routing_ms": report["routing_ms"],
                "discomfort_source": report["discomfort_source"],
                "output": str(path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
