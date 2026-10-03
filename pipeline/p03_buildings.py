"""LoD1 footprints and the PLAN.md T1 building-height fallbacks."""

import logging
import math
import re
from glob import glob
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from lxml import etree
from pyproj import CRS
from shapely.geometry import MultiPolygon, Polygon

CRS_METRIC = "EPSG:2180"
LOG = logging.getLogger(__name__)
GML = "http://www.opengis.net/gml"
BUILDING_TAGS = tuple(
    f"{{http://www.opengis.net/citygml/building/{version}}}Building"
    for version in ("1.0", "2.0")
)


def _positive_number(value, *, units: bool = False) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    text = str(value).strip().lower().replace(",", ".")
    pattern = r"([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(m|ft|')?"
    match = re.fullmatch(pattern, text)
    if not match or (match[2] and not units):
        return None
    result = float(match[1])
    if match[2] in ("ft", "'"):
        result *= 0.3048
    return result if math.isfinite(result) and result > 0 else None


def building_height(tags: dict, primary_height=None) -> tuple[float, str]:
    """Return metres and provenance; the height raster supports up to 255 m."""
    for value, source in (
        (primary_height, "gugik_measuredHeight"),
        (tags.get("height"), "osm_height"),
    ):
        height = _positive_number(value, units=True)
        if height is not None and height <= 255:
            return height, source
    levels = _positive_number(tags.get("building:levels"))
    if levels is not None and levels * 3.2 + 1 <= 255:
        return levels * 3.2 + 1, "osm_levels_estimate"
    kind = str(tags.get("building"))
    defaults = {"house": 7.0, "apartments": 15.0, "commercial": 12.0}
    height = defaults.get(kind, 9.0)
    return height, f"default_{kind if kind in defaults else 'other'}"


def polygon_geometry(geometry):
    if geometry is None or geometry.is_empty:
        return None
    if not np.isfinite(shapely.get_coordinates(geometry)).all():
        return None
    geometry = shapely.force_2d(geometry)
    if not geometry.is_valid:
        geometry = shapely.make_valid(geometry)
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry if geometry.area > 0 else None
    if hasattr(geometry, "geoms"):
        parts = [polygon_geometry(part) for part in geometry.geoms]
        parts = [part for part in parts if part is not None]
        return shapely.union_all(parts) if parts else None
    return None


def metric_polygons(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.crs is None:
        raise ValueError("Input geometries must declare their CRS")
    frame = frame.to_crs(CRS_METRIC).copy()
    repaired = frame.geometry.map(polygon_geometry)
    invalid = repaired.isna()
    if invalid.any():
        LOG.warning("Omitting %d missing/non-polygon geometries", invalid.sum())
    frame.geometry = repaired
    return frame.loc[~invalid].reset_index(drop=True)


def empty_polygons() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[], crs=CRS_METRIC)


def prepare_buildings(
    osm: gpd.GeoDataFrame,
    lod1: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame:
    """LoD1 overrides intersecting OSM footprints; unmatched OSM fills gaps."""
    osm = metric_polygons(osm)
    primary = metric_polygons(lod1) if lod1 is not None else empty_polygons()
    rows, matched = [], set()
    index = osm.sindex
    for _, building in primary.iterrows():
        candidates = index.query(building.geometry, predicate="intersects")
        overlaps = [
            (int(i), building.geometry.intersection(osm.geometry.iloc[i]).area)
            for i in candidates
        ]
        overlaps = [(i, area) for i, area in overlaps if area > 0]
        matched.update(i for i, _ in overlaps)
        best = (
            max(overlaps, key=lambda item: (item[1], -item[0]))[0] if overlaps else None
        )
        tags = osm.iloc[best].to_dict() if best is not None else {}
        height, source = building_height(tags, building.get("measured_height"))
        rows.append(
            {
                "geometry": building.geometry,
                "height": height,
                "height_source": source,
                "footprint_source": "gugik_lod1_2024",
            }
        )
    for i, building in osm.iterrows():
        if i in matched:
            continue
        height, source = building_height(building.to_dict())
        rows.append(
            {
                "geometry": building.geometry,
                "height": height,
                "height_source": source,
                "footprint_source": "osm",
            }
        )
    if not rows:
        return gpd.GeoDataFrame(
            {"height": [], "height_source": [], "footprint_source": []},
            geometry=[],
            crs=CRS_METRIC,
        )
    return gpd.GeoDataFrame(rows, crs=CRS_METRIC)


def _ring(element) -> np.ndarray | None:
    if element is None or not element.text:
        return None
    try:
        values = np.array(element.text.split(), dtype=float).reshape(-1, 3)
    except ValueError:
        return None
    if len(values) < 4 or not np.isfinite(values).all():
        return None
    return values


def _footprint(element):
    surfaces = []
    for polygon in element.iter(f"{{{GML}}}Polygon"):
        exterior = _ring(polygon.find(f".//{{{GML}}}exterior//{{{GML}}}posList"))
        if exterior is None or np.ptp(exterior[:, 2]) > 1e-6:
            continue
        holes = [
            _ring(ring)
            for ring in polygon.findall(f".//{{{GML}}}interior//{{{GML}}}posList")
        ]
        geometry = polygon_geometry(
            Polygon(
                exterior[:, :2], [ring[:, :2] for ring in holes if ring is not None]
            )
        )
        if geometry is not None:
            surfaces.append((float(exterior[0, 2]), geometry))
    if not surfaces:
        return None
    lowest = min(z for z, _ in surfaces)
    return shapely.union_all([g for z, g in surfaces if abs(z - lowest) < 1e-6])


def parse_lod1(pattern: str = "data/raw/lod1/**/*.gml") -> gpd.GeoDataFrame:
    files = sorted(glob(str(pattern), recursive=True))
    if not files:
        raise FileNotFoundError(f"No LoD1 files matching {pattern}")
    rows, skipped = [], 0
    checked_crs = set()
    for filename in files:
        for event, element in etree.iterparse(
            filename, events=("start", "end"), resolve_entities=False, no_network=True
        ):
            if event == "start":
                srs = element.get("srsName")
                if srs and srs not in checked_crs:
                    if CRS.from_user_input(srs).to_epsg() != 2180:
                        raise ValueError(f"LoD1 must use EPSG:2180, found {srs}")
                    checked_crs.add(srs)
                dimension = element.get("srsDimension")
                if dimension is not None and dimension != "3":
                    raise ValueError("LoD1 must contain three-dimensional coordinates")
                continue
            if element.tag not in BUILDING_TAGS:
                continue
            geometry = _footprint(element)
            if geometry is None:
                skipped += 1
            else:
                height = element.find("{*}measuredHeight")
                value = height.text if height is not None else None
                if height is not None and height.get("uom", "m") not in ("m", "#m"):
                    value = None
                rows.append({"geometry": geometry, "measured_height": value})
            element.clear()
            parent = element.getparent()
            if parent is not None:
                while parent.getprevious() is not None:
                    del parent.getparent()[0]
    if skipped:
        LOG.warning("Skipped %d LoD1 buildings without valid horizontal base", skipped)
    if not rows:
        return gpd.GeoDataFrame({"measured_height": []}, geometry=[], crs=CRS_METRIC)
    return gpd.GeoDataFrame(rows, crs=CRS_METRIC)


def read_osm_pbf(
    path: str | Path,
    bbox: tuple[float, float, float, float] = (19.79, 49.96, 20.22, 50.13),
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Offline OSM fallback: buildings, tree crowns and forest/park polygons."""
    import osmium

    factory = osmium.geom.WKBFactory()
    buildings, trees = [], []
    area_of_interest = shapely.box(*bbox)

    class Handler(osmium.SimpleHandler):
        def node(self, node):
            if node.tags.get("natural") == "tree" and node.location.valid():
                point = shapely.Point(node.location.lon, node.location.lat)
                if not area_of_interest.covers(point):
                    return
                trees.append(
                    {
                        "geometry": point,
                        "tree_source": "osm_tree",
                        "height": 10.0,
                    }
                )

        def area(self, area):
            tags = dict(area.tags)
            is_building = tags.get("building") not in (None, "no")
            is_green = (
                tags.get("landuse") in ("forest", "park")
                or tags.get("leisure") == "park"
            )
            if not is_building and not is_green:
                return
            try:
                geometry = shapely.from_wkb(factory.create_multipolygon(area))
            except RuntimeError:
                LOG.warning("Skipping incomplete OSM area %s", area.id)
                return
            if not geometry.intersects(area_of_interest):
                return
            if is_building:
                buildings.append({**tags, "geometry": geometry})
            if is_green:
                trees.append(
                    {
                        "geometry": geometry,
                        "tree_source": "osm_forest_park",
                        "height": 12.0,
                    }
                )

    Handler().apply_file(str(path), locations=True)
    bld = (
        gpd.GeoDataFrame(buildings, crs=4326).to_crs(CRS_METRIC)
        if buildings
        else empty_polygons()
    )
    tree = (
        gpd.GeoDataFrame(trees, crs=4326).to_crs(CRS_METRIC)
        if trees
        else empty_polygons()
    )
    if not tree.empty:
        points = tree.geom_type == "Point"
        tree.loc[points, "geometry"] = tree.loc[points].geometry.buffer(3)
    return bld, tree
