# Routing

`RoutingGraph.load("data/processed")` loads the frozen graph. Call
`route([(lat, lon), ...], edge_cost)` with 2–5 points and a finite,
nonnegative `(E,)` cost array indexed by `eid`. Results contain `eids`
and `node_path`; `geometry(eids)` returns `[lon, lat]` coordinates.
Points more than 300 m from a node raise `PointOutsideArea` with `index`.
Disconnected routes raise `NoRoute`. Identical snapped points produce
an empty edge list and empty geometry; the backend handles that response.

Build from `data/raw/malopolskie-latest.osm.pbf`:

```powershell
python -m pipeline.graph_build
python -m scripts.validate_graph
python -m unittest discover -s tests -v
python -m scripts.benchmark_graph --samples 200
python -m scripts.demo_routing --synthetic
```

Artifacts and `routing_benchmark.json` are saved in `data/processed`.
The build keeps the shortest parallel edge per directed `(u, v)` and
assigns contiguous `eid` values. Rebuilding invalidates downstream arrays.
The build writes a checksum manifest; `RoutingGraph.load` verifies it when
present and rejects mixed artifact versions. Node and edge numbering is
deterministic for the same input graph. The city boundary is exported to
`app/static/krakow_boundary.geojson`.
For repeated exports, `python -m pipeline.graph_build --reuse-osm` skips
PBF filtering. Use it only when the existing filtered XML matches the
current filter rules; after filter changes run the full build.

The benchmark measures FASTEST, ECO with synthetic test costs, and their
combined time, including geometry. The 150 ms target applies to each route;
the combined budget is 300 ms. Sampling uses existing graph nodes and one
request at a time, so this is not an HTTP or concurrency benchmark.

On the development laptop (Windows 11, Python 3.12.4, SciPy 1.18.1),
200 samples on the current graph gave these p95 times including geometry:

| Points | FASTEST | ECO (synthetic) | Both |
| --- | --- | --- | --- |
| 2 | 30.16 ms | 29.50 ms | 58.04 ms |
| 5 | 105.22 ms | 108.07 ms | 205.44 ms |

Current artifacts contain 76,133 nodes and 174,039 edges. Treat the
checksum manifest as their identifier; arrays from the previous graph
must be regenerated. `data/processed/krakow_graph.zip` contains the graph,
manifest, validation and benchmark reports, and service boundary.

`demo_routing` saves a GeoJSON comparison. For real environment data use
`--discomfort path/to/discomfort.npy` instead of `--synthetic`; values must
be finite, in `[0, 1]`, and indexed by the current `eid`. It applies the
backend formula `t = length / (speed_kmh / 3.6)`, `eco = t * (1 + alpha * D)`.
The output uses `avg_discomfort` in `[0, 1]`, not the HTTP display scale 0–10.

The `app` package currently contains routing and its contracts; Flask integration
belongs to the backend role. The existing `streamlit run app.py` entry
point and `src/router_fast.py` prototype remain available.
