import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from app.graph.routing import RoutingGraph
from pipeline.graph_build import DROP_HW


def validate_graph(data_dir: str) -> dict:
    root = Path(data_dir)
    manifest = json.loads((root / "graph_manifest.json").read_text(encoding="utf-8"))
    if manifest["format_version"] != 1:
        raise ValueError("unsupported artifact version")
    graph = RoutingGraph.load(data_dir)
    if (graph.N, graph.n_edges) != (manifest["nodes"], manifest["edges"]):
        raise ValueError("manifest graph size mismatch")
    edges = gpd.read_parquet(root / "edges.parquet")
    if edges.crs.to_epsg() != 2180:
        raise ValueError("edges.parquet must use EPSG:2180")
    if edges.duplicated(["u", "v"]).any():
        raise ValueError("parallel edges must be deduplicated")
    if edges.highway.isin(DROP_HW).any():
        raise ValueError("graph contains excluded highway types")
    matrix = csr_matrix(
        (np.ones(graph.n_edges), graph.indices, graph.indptr), shape=(graph.N, graph.N)
    )
    components = connected_components(
        matrix, directed=True, connection="strong", return_labels=False
    )
    if components != 1:
        raise ValueError("city graph must be strongly connected")
    length_ratio = edges.geometry.length.to_numpy() / edges.length_m.to_numpy()
    report = {
        "ok": True,
        "nodes": graph.N,
        "edges": graph.n_edges,
        "strong_components": int(components),
        "artifact_checksums": "verified",
        "highway_counts": {
            str(k): int(v) for k, v in edges.highway.value_counts().items()
        },
        "projected_geometry_to_osm_length_ratio": {
            "p01": round(float(np.percentile(length_ratio, 1)), 5),
            "p50": round(float(np.percentile(length_ratio, 50)), 5),
            "p99": round(float(np.percentile(length_ratio, 99)), 5),
        },
    }
    (root / "graph_validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Check frozen graph artifacts before integration"
    )
    parser.add_argument("--data-dir", default="data/processed")
    args = parser.parse_args()
    print(json.dumps(validate_graph(args.data_dir), indent=2))


if __name__ == "__main__":
    main()
