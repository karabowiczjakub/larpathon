"""Offline ray-marching from PLAN.md §7.5; no graph mutation."""

import hashlib
import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import shapely

from pipeline.p03_buildings import CRS_METRIC

AZ = np.arange(0, 360, 22.5)
EL = np.array([5, 10, 15, 20, 30, 40, 50, 65])
STEP, MAXD, EYE = 2.0, 120.0, 1.5
D = np.arange(STEP, MAXD + STEP, STEP)
for _constant in (AZ, EL, D):
    _constant.setflags(write=False)
LOG = logging.getLogger(__name__)


def metric_edges(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if edges.crs is None:
        raise ValueError("Edges must declare their CRS")
    if "eid" not in edges or not np.array_equal(edges.eid, np.arange(len(edges))):
        raise ValueError("Edge rows must be ordered by contiguous eid = 0..E-1")
    return edges.to_crs(CRS_METRIC)


def make_sampler(height: np.ndarray, transform):
    if (
        height.ndim != 2
        or height.dtype != np.uint8
        or not height.size
        or transform.a <= 0
        or transform.e >= 0
        or transform.b != 0
        or transform.d != 0
        or not np.isfinite(tuple(transform)).all()
    ):
        raise ValueError("Expected north-up uint8 metric height raster")

    def sample(xs, ys):
        xs, ys = np.broadcast_arrays(np.asarray(xs), np.asarray(ys))
        col = np.floor((xs - transform.c) / transform.a)
        row = np.floor((ys - transform.f) / transform.e)
        inside = (
            (row >= 0) & (row < height.shape[0]) & (col >= 0) & (col < height.shape[1])
        )
        result = np.zeros(xs.shape, dtype=np.uint8)
        result[inside] = height[row[inside].astype(int), col[inside].astype(int)]
        return result

    return sample


def shaded_points(px, py, sample, azimuth: float, elevation: float) -> np.ndarray:
    """Trace toward the sun; buildings cast shadows in the opposite direction."""
    if not np.isfinite([azimuth, elevation]).all():
        raise ValueError("Solar angles must be finite")
    px, py = np.broadcast_arrays(np.asarray(px), np.asarray(py))
    if elevation <= 0:
        return np.ones(px.shape, dtype=bool)
    angle = np.radians(azimuth % 360)
    need = EYE + D * np.tan(np.radians(np.clip(elevation, 5, 90)))
    xs = px[..., None] + D * np.sin(angle)
    ys = py[..., None] + D * np.cos(angle)
    return (sample(xs, ys) > need).any(axis=-1) | (sample(px, py) >= 3)


def edge_points(edges: gpd.GeoDataFrame, step: float = 15.0):
    """Deduplicate identical geometry in either direction, never merely (u, v)."""
    if not np.isfinite(step) or step <= 0:
        raise ValueError("Sampling step must be positive metres")
    edges = metric_edges(edges)
    representatives, pts, owners = {}, [], []
    eid_to_rep = np.arange(len(edges))
    skipped = 0
    for eid, geometry in enumerate(edges.geometry):
        if (
            geometry is None
            or geometry.is_empty
            or not geometry.is_valid
            or geometry.geom_type != "LineString"
            or geometry.length <= 0
            or not np.isfinite(shapely.get_coordinates(geometry)).all()
        ):
            skipped += 1
            continue
        key = shapely.normalize(shapely.force_2d(geometry)).wkb
        if key in representatives:
            eid_to_rep[eid] = representatives[key]
            continue
        representatives[key] = eid
        # Equal-length cells and their midpoints give equal sample weights.
        n = max(2, int(np.ceil(geometry.length / step)))
        fractions = (np.arange(n) + 0.5) / n
        pts.append(shapely.line_interpolate_point(geometry, fractions, normalized=True))
        owners.append(np.full(n, eid, dtype=np.int64))
    if skipped:
        LOG.warning("%d invalid/empty edges receive zero daytime shade", skipped)
    points = np.concatenate(pts) if pts else np.array([], dtype=object)
    owner = np.concatenate(owners) if owners else np.array([], dtype=np.int64)
    return shapely.get_x(points), shapely.get_y(points), owner, eid_to_rep


def compute_shade_table(
    edges: gpd.GeoDataFrame,
    height: np.ndarray,
    transform,
    tree_height: np.ndarray,
    *,
    chunk: int = 20_000,
    sample_step: float = 15.0,
    az: np.ndarray = AZ,
    el: np.ndarray = EL,
) -> tuple[np.ndarray, np.ndarray]:
    if chunk < 1 or tree_height.shape != height.shape:
        raise ValueError("Invalid chunk size or incompatible tree raster")
    az, el = np.asarray(az, dtype=float), np.asarray(el, dtype=float)
    if (
        az.ndim != 1
        or el.ndim != 1
        or not len(az)
        or not len(el)
        or not np.isfinite(az).all()
        or not np.isfinite(el).all()
        or np.any(np.diff(az) <= 0)
        or np.any(np.diff(el) <= 0)
        or az[0] < 0
        or az[-1] >= 360
        or el[0] < 5
        or el[-1] >= 90
    ):
        raise ValueError("Invalid solar bins")
    sample, tree_sample = (
        make_sampler(height, transform),
        make_sampler(tree_height, transform),
    )
    px, py, owner, rep = edge_points(edges, sample_step)
    counts = np.maximum(np.bincount(owner, minlength=len(edges)), 1)
    canopy = tree_sample(px, py) >= 3
    tree = (np.bincount(owner, weights=canopy, minlength=len(edges)) / counts)[rep]
    table = np.zeros((len(edges), len(az), len(el)), dtype=np.uint8)
    for i, azimuth in enumerate(az):
        for j, elevation in enumerate(el):
            shaded = np.empty(len(px), dtype=bool)
            for start in range(0, len(px), chunk):
                stop = start + chunk
                shaded[start:stop] = shaded_points(
                    px[start:stop], py[start:stop], sample, azimuth, elevation
                )
            fraction = np.bincount(owner, weights=shaded, minlength=len(edges)) / counts
            table[:, i, j] = np.round(fraction * 255).astype(np.uint8)
        LOG.info("Shade azimuth %.1f complete", azimuth)
    return table[rep], tree.astype(np.float32)


def read_height_raster(path: str | Path):
    with rasterio.open(path) as src:
        if src.crs is None or src.crs.to_epsg() != 2180:
            raise ValueError("Height raster must be EPSG:2180")
        height, transform = src.read(1), src.transform
    make_sampler(height, transform)
    return height, transform


def save_shade_artifacts(
    directory: str | Path,
    table: np.ndarray,
    tree: np.ndarray,
    edges_path: str | Path,
    *,
    az=AZ,
    el=EL,
    metadata: dict | None = None,
) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with Path(edges_path).open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    np.save(directory / "shade.npy", table)
    np.save(directory / "edge_tree_frac.npy", tree)
    bins = {
        "az": np.asarray(az).tolist(),
        "el": np.asarray(el).tolist(),
        "edges_sha256": fingerprint,
        "crs": CRS_METRIC,
        "step_m": STEP,
        "max_distance_m": MAXD,
        "eye_height_m": EYE,
        "metadata": metadata or {},
    }
    (directory / "shade_bins.json").write_text(json.dumps(bins, indent=2) + "\n")
