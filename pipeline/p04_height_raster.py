"""Rasterize obstacles in metres and keep tree cover separate from buildings."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine, from_origin

from pipeline.p03_buildings import CRS_METRIC, metric_polygons

RES = 2.0


def _rasterize(frame, shape, transform):
    if frame.empty:
        return np.zeros(shape, dtype=np.uint8)
    heights = frame["height"].to_numpy(dtype=float)
    if not np.isfinite(heights).all() or np.any((heights <= 0) | (heights > 255)):
        raise ValueError("Obstacle heights must be finite metres in (0, 255]")
    shapes = ((frame.geometry.iloc[i], int(heights[i])) for i in np.argsort(heights))
    return rasterize(
        shapes, out_shape=shape, transform=transform, fill=0, dtype="uint8"
    )


def build_height_raster(
    buildings: gpd.GeoDataFrame,
    trees: gpd.GeoDataFrame,
    bounds: tuple[float, float, float, float],
    out: str | Path | None = None,
) -> tuple[np.ndarray, np.ndarray, Affine]:
    """Bounds use EPSG:2180 x/y; returns height, tree-only height, transform."""
    x0, y0, x1, y1 = bounds
    if not np.isfinite(bounds).all() or x1 <= x0 or y1 <= y0:
        raise ValueError("Invalid metric raster bounds")
    shape = (int(np.ceil((y1 - y0) / RES)), int(np.ceil((x1 - x0) / RES)))
    transform = from_origin(x0, y1, RES, RES)
    buildings, trees = metric_polygons(buildings), metric_polygons(trees)
    if "height" not in trees:
        trees["height"] = 12.0
    height = _rasterize(buildings, shape, transform)
    tree_height = _rasterize(trees, shape, transform)
    np.maximum(height, tree_height, out=height)
    if out is not None:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        for target, values in (
            (path, height),
            (path.with_name("trees_2m.tif"), tree_height),
        ):
            with rasterio.open(
                target,
                "w",
                driver="GTiff",
                width=shape[1],
                height=shape[0],
                count=1,
                dtype="uint8",
                crs=CRS_METRIC,
                transform=transform,
                compress="deflate",
            ) as dst:
                dst.write(values, 1)
    return height, tree_height, transform
