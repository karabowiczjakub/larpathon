"""Run explicitly: python -m pipeline.shade_build --help."""

import argparse
import hashlib
import json
import logging
import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
from lxml import etree
from shapely.geometry import LineString

from pipeline.p03_buildings import (
    CRS_METRIC,
    empty_polygons,
    metric_polygons,
    parse_lod1,
    prepare_buildings,
    read_osm_pbf,
)
from pipeline.p04_height_raster import build_height_raster
from pipeline.p05_shade import (
    AZ,
    EL,
    EYE,
    MAXD,
    STEP,
    compute_shade_table,
    metric_edges,
    save_shade_artifacts,
)

LOD1_URL = "https://opendata.geoportal.gov.pl/InneDane/Budynki3D/LOD1/2024/12/1261.zip"
MSIP_URL = (
    "https://msip.um.krakow.pl/arcgis/rest/services/MONIT-AIR/"
    "WS_MA_Mapa_Zieleni_2015/MapServer/0/query"
)
BBOX_WGS = (19.79, 49.96, 20.22, 50.13)
LOG = logging.getLogger(__name__)


def download_lod1(directory: str | Path) -> str:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "lod1_1261.zip"
    if not archive.exists():
        partial = archive.with_suffix(".part")
        with httpx.stream(
            "GET", LOD1_URL, timeout=120, follow_redirects=True
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as stream:
                for chunk in response.iter_bytes():
                    stream.write(chunk)
        partial.replace(archive)
    target = directory / "lod1"
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if not member.filename.lower().endswith(".gml"):
                continue
            relative = Path(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid LoD1 archive path")
            output = target / relative
            if output.exists() and output.stat().st_size == member.file_size:
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return str(target / "**/*.gml")


def fetch_tall_green(
    bbox: tuple = BBOX_WGS,
    *,
    client: httpx.Client | None = None,
) -> gpd.GeoDataFrame:
    if client is None:
        with httpx.Client(timeout=60) as owned_client:
            return fetch_tall_green(bbox, client=owned_client)
    parts, offset = [], 0
    previous = None
    while True:
        response = client.get(
            MSIP_URL,
            params={
                "where": "class_name LIKE '200%'",
                "geometry": ",".join(map(str, bbox)),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "class_name",
                "outSR": 4326,
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": 1000,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload or "features" not in payload:
            raise ValueError("MSIP returned an error instead of features")
        features = payload["features"]
        if not features:
            break
        fingerprint = hashlib.sha256(
            json.dumps(features, sort_keys=True).encode()
        ).hexdigest()
        if fingerprint == previous:
            raise ValueError("MSIP pagination repeated a page")
        previous = fingerprint
        parts.append(gpd.GeoDataFrame.from_features(features, crs=4326))
        offset += len(features)
    if not parts:
        return empty_polygons()
    trees = metric_polygons(
        gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326)
    )
    trees["height"] = 12.0
    trees["tree_source"] = "msip_2015_assumed_12m"
    return trees


def preview_grid(bounds: tuple, step: float = 50.0) -> gpd.GeoDataFrame:
    """Temporary metre-long sample segments; these eid are NOT routing eid."""
    x0, y0, x1, y1 = bounds
    if (
        not np.isfinite(bounds).all()
        or x1 <= x0
        or y1 <= y0
        or not np.isfinite(step)
        or step <= 0
    ):
        raise ValueError("Invalid preview bounds or step in metres")
    geometry = [
        LineString([(x - 0.5, y), (x + 0.5, y)])
        for y in np.arange(y0, y1, step)
        for x in np.arange(x0, x1, step)
    ]
    return gpd.GeoDataFrame(
        {"eid": np.arange(len(geometry))}, geometry=geometry, crs=CRS_METRIC
    )


def _cache_key(edges_path, buildings, trees, settings) -> str:
    with Path(edges_path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256")
    digest.update(json.dumps(settings, sort_keys=True).encode())
    for frame in (buildings, trees):
        digest.update(str(len(frame)).encode())
        for geometry in frame.geometry:
            digest.update(geometry.wkb)
        for column in ("height", "height_source", "footprint_source", "tree_source"):
            if column in frame:
                digest.update(frame[column].to_json().encode())
    return digest.hexdigest()


def build_artifacts(
    edges_path: str | Path,
    buildings: gpd.GeoDataFrame,
    trees: gpd.GeoDataFrame,
    output: str | Path,
    *,
    sample_step: float = 15,
    coarse: bool = False,
    force: bool = False,
    preview: bool = False,
) -> bool:
    """Return False for a validated cache hit, True after rebuilding."""
    from app.shade.model import ShadeModel

    output, edges_path = Path(output), Path(edges_path)
    edges = metric_edges(gpd.read_parquet(edges_path))
    if edges.empty or not np.isfinite(edges.total_bounds).all():
        raise ValueError("At least one valid edge is required to define raster bounds")
    bounds = edges.total_bounds + np.array([-150, -150, 150, 150])
    buildings, trees = metric_polygons(buildings), metric_polygons(trees)
    if "height" not in trees:
        trees["height"] = 12.0
        if "tree_source" not in trees:
            trees["tree_source"] = "assumed_12m"
    elif "tree_source" not in trees:
        trees["tree_source"] = "provided_height"
    az = np.arange(0, 360, 90) if coarse else AZ
    el = np.array([5, 15, 30, 65]) if coarse else EL
    settings = {
        "version": 1,
        "crs": CRS_METRIC,
        "bounds": bounds.tolist(),
        "sample_step_m": sample_step,
        "az": az.tolist(),
        "el": el.tolist(),
        "eye_m": EYE,
        "ray_step_m": STEP,
        "max_distance_m": MAXD,
        "raster_resolution_m": 2,
        "preview_grid": preview,
    }
    key = _cache_key(edges_path, buildings, trees, settings)
    bins_file = output / "shade_bins.json"
    if not force and bins_file.exists():
        try:
            bins = json.loads(bins_file.read_text())
            rasters_exist = all(
                (output / name).exists() for name in ("heights_2m.tif", "trees_2m.tif")
            )
            if bins.get("metadata", {}).get("build_key") == key and rasters_exist:
                ShadeModel.load(output, len(edges))
                LOG.info("Shade cache hit")
                return False
        except (ValueError, OSError, KeyError):
            LOG.warning("Incomplete shade cache; rebuilding")
    output.mkdir(parents=True, exist_ok=True)
    # Keep the exact graph artifact alongside the LUT for startup verification.
    if edges_path.resolve() != (output / "edges.parquet").resolve():
        shutil.copyfile(edges_path, output / "edges.parquet")
    buildings.to_parquet(output / "buildings.parquet")
    trees.to_parquet(output / "trees.parquet")
    height, canopy, transform = build_height_raster(
        buildings, trees, tuple(bounds), output / "heights_2m.tif"
    )
    table, tree_fraction = compute_shade_table(
        edges, height, transform, canopy, sample_step=sample_step, az=az, el=el
    )
    settings.update(
        {
            "build_key": key,
            "building_count": len(buildings),
            "tree_polygon_count": len(trees),
            "height_sources": buildings.height_source.value_counts().to_dict()
            if "height_source" in buildings
            else {"provided": len(buildings)},
            "tree_sources": trees.tree_source.value_counts().to_dict()
            if "tree_source" in trees
            else {},
            "missing_buildings": buildings.empty,
            "missing_trees": trees.empty,
        }
    )
    save_shade_artifacts(
        output, table, tree_fraction, edges_path, az=az, el=el, metadata=settings
    )
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--edges", type=Path, default=Path("data/processed/edges.parquet")
    )
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--lod1", help="Local CityGML glob (quote it)")
    parser.add_argument(
        "--osm-pbf", type=Path, help="Local OSM fallback, no graph processing"
    )
    parser.add_argument("--osm-buildings", type=Path, help="OSM-tagged GeoParquet")
    parser.add_argument(
        "--buildings", type=Path, help="Previously prepared buildings.parquet"
    )
    parser.add_argument(
        "--trees", type=Path, help="Local tree GeoParquet in a declared CRS"
    )
    parser.add_argument(
        "--download", action="store_true", help="Explicitly fetch LoD1 and MSIP"
    )
    parser.add_argument("--allow-missing-buildings", action="store_true")
    parser.add_argument("--allow-missing-trees", action="store_true")
    parser.add_argument(
        "--sample-step", type=float, default=15, help="Metres; use 20 if slow"
    )
    parser.add_argument("--coarse", action="store_true", help="Emergency 4 x 4 LUT")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--preview-grid",
        nargs=4,
        type=float,
        metavar=("X0", "Y0", "X1", "Y1"),
        help="EPSG:2180 bounds for temporary 50 m grid; use a separate output",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.preview_grid:
        if args.output.resolve() == Path("data/processed").resolve():
            parser.error(
                "--preview-grid requires a separate --output (not data/processed)"
            )
        args.output.mkdir(parents=True, exist_ok=True)
        args.edges = args.output / "edges.parquet"
        preview_grid(tuple(args.preview_grid)).to_parquet(args.edges)
    if not args.edges.exists():
        parser.error(
            "Missing edges.parquet: use MockShade or --preview-grid until Role 1 publishes it"
        )

    osm, osm_trees = empty_polygons(), empty_polygons()
    if args.osm_pbf:
        osm, osm_trees = read_osm_pbf(args.osm_pbf)
    if args.osm_buildings:
        osm = gpd.read_parquet(args.osm_buildings)
    lod1 = None
    if args.lod1 or args.download:
        try:
            pattern = args.lod1 or download_lod1(args.raw)
            lod1 = parse_lod1(pattern)
        except (
            httpx.HTTPError,
            OSError,
            ValueError,
            etree.XMLSyntaxError,
            zipfile.BadZipFile,
        ) as exc:
            LOG.warning("LoD1 unavailable; using OSM fallback: %s", exc)
    prepared = args.buildings or args.output / "buildings.parquet"
    if args.buildings or (
        not args.lod1 and not args.download and osm.empty and prepared.exists()
    ):
        buildings = gpd.read_parquet(prepared)
    else:
        buildings = prepare_buildings(osm, lod1)
    trees_path = args.trees or args.output / "trees.parquet"
    trees = osm_trees
    if trees_path.exists():
        trees = gpd.read_parquet(trees_path)
    elif args.trees:
        parser.error(f"Missing tree file: {args.trees}")
    elif args.download:
        try:
            trees = fetch_tall_green()
            if trees.empty:
                LOG.warning("MSIP has no tree features; using OSM fallback")
                trees = osm_trees
        except (httpx.HTTPError, ValueError) as exc:
            LOG.warning("MSIP unavailable; using OSM fallback: %s", exc)
    for name, frame, allowed in (
        ("buildings", buildings, args.allow_missing_buildings),
        ("trees", trees, args.allow_missing_trees),
    ):
        if frame.empty:
            if not allowed:
                parser.error(f"No {name}; provide local data or --allow-missing-{name}")
            LOG.warning("Explicit fallback: no %s in the shade model", name)
    build_artifacts(
        args.edges,
        buildings,
        trees,
        args.output,
        sample_step=args.sample_step,
        coarse=args.coarse,
        force=args.force,
        preview=bool(args.preview_grid),
    )


if __name__ == "__main__":
    main()
