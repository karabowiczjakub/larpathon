# pipeline/graph_build.py
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import osmium
import shapely

PBF = "data/raw/malopolskie-latest.osm.pbf"
BBOX = (
    19.79,
    49.96,
    20.22,
    50.13,
)  # lon_min, lat_min, lon_max, lat_max (Kraków + zapas)

DROP_HW = {
    "motorway",
    "motorway_link",
    "construction",
    "proposed",
    "planned",
    "abandoned",
    "raceway",
    "bus_guideway",
    "platform",
    "elevator",
    "escalator",
    "corridor",
    "steps",
}
BIKE_OK = {"yes", "designated", "permissive"}


def keep(t) -> bool:
    hw = t.get("highway")
    if hw is None or hw in DROP_HW or t.get("motorroad") == "yes":
        return False
    bike = t.get("bicycle")
    if bike in ("no", "dismount"):
        return False
    if hw in ("footway", "pedestrian") and bike not in BIKE_OK:
        return False
    if hw == "service" and t.get("service") in ("parking_aisle", "drive-through"):
        return False
    return not (t.get("access") in ("private", "no") and bike not in BIKE_OK)


def contraflow(t) -> dict:
    tags = dict(t)
    bicycle_oneway = tags.get("oneway:bicycle")
    if bicycle_oneway in {"yes", "1", "true", "-1", "reverse"}:
        tags["oneway"] = bicycle_oneway
    elif bicycle_oneway in {"no", "0", "false"} or any(
        str(tags.get(key, "")).startswith("opposite")
        for key in ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")
    ):
        tags["oneway"] = "no"
        # OSMnx applies the roundabout rule even with an explicit oneway=no.
        if tags.get("junction") == "roundabout":
            tags.pop("junction")
    return tags


def step1_filter(out="data/interim/krk_bike_ways.osm", pbf=PBF):
    t0 = time.time()
    need = set()
    n = 0
    w = osmium.SimpleWriter(out, overwrite=True)
    fp = (
        osmium.FileProcessor(pbf)
        .with_filter(osmium.filter.KeyFilter("highway"))
        .with_locations()
    )
    for o in fp:
        if not o.is_way() or not keep(o.tags):
            continue
        if not any(
            n_.location.valid()
            and BBOX[0] <= n_.lon <= BBOX[2]
            and BBOX[1] <= n_.lat <= BBOX[3]
            for n_ in o.nodes
        ):
            continue
        w.add_way(o.replace(tags=contraflow(o.tags)))
        need.update(n_.ref for n_ in o.nodes)
        n += 1
    w.close()
    print(f"ways={n:,} nodes={len(need):,} {time.time() - t0:.0f}s")
    # węzły + drogi w jednym pliku (OSM XML: najpierw węzły)
    w = osmium.SimpleWriter("data/interim/krk_bike.osm", overwrite=True)
    for o in osmium.FileProcessor(pbf, osmium.osm.NODE):
        if o.id in need:
            w.add_node(o)
    for o in osmium.FileProcessor(out, osmium.osm.WAY):
        w.add_way(o)
    w.close()


def kraków_boundary(pbf=PBF) -> shapely.Polygon:
    # A) z PBF: relacja boundary=administrative, admin_level=8, name=Kraków (bez internetu)
    try:
        wkb = osmium.geom.WKBFactory()
        fp = (
            osmium.FileProcessor(pbf)
            .with_areas()
            .with_filter(osmium.filter.TagFilter(("boundary", "administrative")))
        )
        for o in fp:
            if (
                o.is_area()
                and o.tags.get("admin_level") == "8"
                and o.tags.get("name") == "Kraków"
            ):
                return shapely.from_wkb(wkb.create_multipolygon(o))
    except Exception as e:  # noqa: BLE001 - try the next boundary source
        print("boundary from PBF failed:", e)
    # B) Nominatim (inny serwer niż Overpass)
    try:
        import osmnx as ox

        return ox.geocode_to_gdf("Kraków, Poland").geometry.iloc[0]
    except Exception as e:  # noqa: BLE001 - explicit offline fallback
        print("boundary from Nominatim failed:", e)
    # C) prostokąt
    return shapely.box(19.79, 49.97, 20.22, 50.13)


def main():
    parser = argparse.ArgumentParser(
        description="Build the Krakow bicycle graph offline"
    )
    parser.add_argument("--pbf", default=PBF)
    parser.add_argument(
        "--reuse-osm",
        action="store_true",
        help="reuse the filtered XML; only when it matches current filter rules",
    )
    args = parser.parse_args()
    if not Path(args.pbf).is_file():
        parser.error(f"PBF file missing: {args.pbf}")
    started = time.perf_counter()
    for directory in ("data/interim", "data/processed"):
        Path(directory).mkdir(parents=True, exist_ok=True)
    if args.reuse_osm:
        if not Path("data/interim/krk_bike.osm").is_file():
            parser.error("filtered XML missing; run without --reuse-osm")
    else:
        step1_filter(pbf=args.pbf)
    import osmnx as ox

    boundary = kraków_boundary(args.pbf)
    boundary_path = Path("app/static/krakow_boundary.geojson")
    boundary_path.parent.mkdir(parents=True, exist_ok=True)
    boundary_path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {},
                "geometry": shapely.geometry.mapping(boundary.simplify(0.0005)),
            }
        ),
        encoding="utf-8",
    )
    G = ox.graph_from_xml(
        "data/interim/krk_bike.osm", bidirectional=False, simplify=True, retain_all=True
    )
    G = ox.truncate.truncate_graph_polygon(G, boundary, truncate_by_edge=True)
    G = ox.truncate.largest_component(
        G, strongly=True
    )  # silnie spójna: z każdego węzła da się wrócić → mniej NoRoute
    G = ox.project_graph(G, to_crs="EPSG:2180")
    print(f"nodes={G.number_of_nodes():,} edges={G.number_of_edges():,}")
    save_graph(G)
    print(f"build completed in {time.perf_counter() - started:.1f}s")


def first_tag(value: object) -> object:
    if isinstance(value, list):
        return min(value, key=str) if value else None
    return value


def save_graph(G, data_dir="data/processed") -> None:
    import osmnx as ox
    import scipy.sparse as sp
    from pyproj import Transformer

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    nodes, edges = ox.graph_to_gdfs(G)
    nodes = nodes.sort_index()
    for col in ("highway", "name"):
        edges[col] = edges[col].apply(first_tag) if col in edges else None

    # KRYTYCZNE: scipy.sparse SUMUJE duplikaty (u,v). Multigraf ma krawędzie równoległe → zostaw najkrótszą.
    edges = edges.reset_index().sort_values(["length", "u", "v", "key"])
    edges = edges.drop_duplicates(["u", "v"]).reset_index(drop=True)

    node_id = {osm: i for i, osm in enumerate(nodes.index)}
    edges["u_i"] = edges["u"].map(node_id).astype(np.int32)
    edges["v_i"] = edges["v"].map(node_id).astype(np.int32)
    edges["eid"] = np.arange(len(edges), dtype=np.int32)
    N, E = len(nodes), len(edges)

    base = sp.csr_matrix(
        (np.arange(1, E + 1), (edges["u_i"], edges["v_i"])), shape=(N, N)
    )
    perm = (base.data - 1).astype(np.int32)  # slot CSR → eid

    to_wgs = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
    nlon, nlat = to_wgs.transform(nodes["x"].to_numpy(), nodes["y"].to_numpy())
    mid = edges.geometry.interpolate(0.5, normalized=True)
    mlon, mlat = to_wgs.transform(mid.x.to_numpy(), mid.y.to_numpy())

    np.savez_compressed(
        data_dir / "graph.npz",
        indptr=base.indptr,
        indices=base.indices,
        perm=perm,
        node_x=nodes["x"].to_numpy(),
        node_y=nodes["y"].to_numpy(),
        node_lon=nlon,
        node_lat=nlat,
        edge_u=edges["u_i"].to_numpy(),
        edge_v=edges["v_i"].to_numpy(),
        edge_length_m=edges["length"].to_numpy(np.float32),
        edge_mid_lon=np.float32(mlon),
        edge_mid_lat=np.float32(mlat),
    )

    # geometrie WGS84, ZAWSZE w kierunku u→v
    geo = edges.set_geometry("geometry").to_crs("EPSG:4326").geometry
    coords, ux, uy = [], nlon[edges["u_i"]], nlat[edges["u_i"]]
    for g, x0, y0 in zip(geo, ux, uy):
        c = np.asarray(g.coords, dtype=np.float32)
        if np.hypot(*(c[0] - (x0, y0))) > np.hypot(*(c[-1] - (x0, y0))):
            c = c[::-1]  # odwróć, jeśli zaczyna się przy v
        coords.append(c)
    offs = np.cumsum([0] + [len(c) for c in coords])
    np.savez_compressed(
        data_dir / "edge_coords.npz", coords=np.vstack(coords), offs=offs
    )

    edges[["eid", "u_i", "v_i", "length", "highway", "name", "geometry"]].rename(
        columns={"u_i": "u", "v_i": "v", "length": "length_m"}
    ).to_parquet(data_dir / "edges.parquet")
    files = {}
    for name in ("graph.npz", "edge_coords.npz", "edges.parquet"):
        with (data_dir / name).open("rb") as artifact:
            files[name] = hashlib.file_digest(artifact, "sha256").hexdigest()
    manifest = {"format_version": 1, "nodes": N, "edges": E, "sha256": files}
    (data_dir / "graph_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"saved: N={N:,} E={E:,}")


if __name__ == "__main__":
    main()
