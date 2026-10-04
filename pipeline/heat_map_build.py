"""Street heat map from Landsat 8/9 surface temperature (offline, once per graph).

Why: the weather grid (DMI HARMONIE-AROME, ~2 km) already carries the city-scale heat island and the
valley, so this map keeps only what the model cannot see: a dense block against a park in the same
neighbourhood. Surface temperature is not air temperature; app/env/exposure.py turns it into a small,
capped air-temperature correction.

    python -m pipeline.heat_map_build        # needs internet (Microsoft Planetary Computer, no key)

Output: data/processed/edge_heat.npz (local_lst_anomaly_c per eid) + edge_heat.json (scenes, settings).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin, rowcol
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds
from scipy.ndimage import gaussian_filter

LOG = logging.getLogger(__name__)
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX_WGS = (19.79, 49.96, 20.22, 50.13)           # as the shade build
CRS = "EPSG:2180"
RES_M = 30.0                                       # Landsat thermal is delivered at 30 m
SUMMERS = "2022-06-01/2025-08-31"
MONTHS = (6, 7, 8)
MAX_CLOUD = 10                                     # % of the scene
MAX_SCENES = 12
MIN_VALID_SCENES = 3                               # per pixel, otherwise no value
LOCAL_SIGMA_M = 150.0                              # street neighbourhood
MODEL_SIGMA_M = 1500.0                             # what the ~2 km weather model already resolves
# QA_PIXEL bits (Landsat Collection 2): 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow, 5 snow
QA_BAD = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
ST_SCALE, ST_OFFSET = 0.00341802, 149.0            # lwir11 DN -> Kelvin


def target_grid() -> tuple[rasterio.Affine, tuple[int, int]]:
    left, bottom, right, top = transform_bounds("EPSG:4326", CRS, *BBOX_WGS)
    width, height = int(np.ceil((right - left) / RES_M)), int(np.ceil((top - bottom) / RES_M))
    return from_origin(left, top, RES_M, RES_M), (height, width)


def find_scenes(limit: int = MAX_SCENES) -> list:
    import planetary_computer
    import pystac_client

    catalog = pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = catalog.search(collections=["landsat-c2-l2"], bbox=BBOX_WGS, datetime=SUMMERS,
                           query={"eo:cloud_cover": {"lt": MAX_CLOUD}, "platform": {"in": ["landsat-8", "landsat-9"]}})
    summer = [i for i in items.items() if i.datetime.month in MONTHS]
    return sorted(summer, key=lambda i: i.properties["eo:cloud_cover"])[:limit]


def scene_anomaly(item, transform, shape) -> np.ndarray:
    """Surface temperature minus that day's city median, on the target grid; NaN where cloudy or no data."""
    out = []
    for asset in ("lwir11", "qa_pixel"):
        with rasterio.open(item.assets[asset].href) as src:
            bounds = transform_bounds("EPSG:4326", src.crs, *BBOX_WGS)
            win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            data = src.read(1, window=win, boundless=True, fill_value=0)
            dst = np.zeros(shape, dtype=np.float64 if asset == "lwir11" else np.uint16)
            reproject(data, dst, src_transform=src.window_transform(win), src_crs=src.crs,
                      dst_transform=transform, dst_crs=CRS, resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
            out.append(dst)
    dn, qa = out
    lst = np.where((dn > 0) & ((qa & QA_BAD) == 0), dn * ST_SCALE + ST_OFFSET - 273.15, np.nan)
    return lst - np.nanmedian(lst)


def smooth(values: np.ndarray, sigma_px: float) -> np.ndarray:
    """Gaussian blur that ignores NaN (normalised convolution)."""
    valid = np.isfinite(values)
    num = gaussian_filter(np.where(valid, values, 0.0), sigma_px, mode="nearest")
    den = gaussian_filter(valid.astype(np.float64), sigma_px, mode="nearest")
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), np.nan)


def local_anomaly(anomaly: np.ndarray) -> np.ndarray:
    """Neighbourhood (~150 m) minus the ~1.5 km background: only what the weather model cannot see."""
    return smooth(anomaly, LOCAL_SIGMA_M / RES_M) - smooth(anomaly, MODEL_SIGMA_M / RES_M)


def sample_edges(raster: np.ndarray, transform, mid_lonlat: np.ndarray) -> np.ndarray:
    x, y = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(mid_lonlat[:, 0], mid_lonlat[:, 1])
    rows, cols = rowcol(transform, np.asarray(x), np.asarray(y))
    rows = np.clip(np.asarray(rows), 0, raster.shape[0] - 1)
    cols = np.clip(np.asarray(cols), 0, raster.shape[1] - 1)
    values = raster[rows, cols]
    return np.nan_to_num(values, nan=0.0).astype(np.float32)


def edge_midpoints(data_dir: Path) -> np.ndarray:
    with np.load(data_dir / "graph.npz") as z:
        return np.column_stack([z["edge_mid_lon"], z["edge_mid_lat"]]).astype(np.float64)


def build(data_dir: Path) -> dict:
    transform, shape = target_grid()
    items = find_scenes()
    if len(items) < MIN_VALID_SCENES:
        raise RuntimeError(f"only {len(items)} cloud-free summer scenes found")
    stack = []
    for item in items:
        stack.append(scene_anomaly(item, transform, shape))
        LOG.info("scene %s: %.0f%% of Kraków usable", item.id, 100 * np.isfinite(stack[-1]).mean())
    stack = np.stack(stack)
    count = np.isfinite(stack).sum(axis=0)
    median = np.where(count >= MIN_VALID_SCENES, np.nanmedian(np.where(count >= MIN_VALID_SCENES, stack, 0.0), axis=0), np.nan)
    local = local_anomaly(median)
    mid = edge_midpoints(data_dir)
    per_edge = sample_edges(local, transform, mid)
    np.savez_compressed(data_dir / "edge_heat.npz", local_lst_anomaly_c=per_edge)
    with (data_dir / "edges.parquet").open("rb") as f:
        edges_sha = hashlib.file_digest(f, "sha256").hexdigest()
    meta = {
        "scenes": [{"id": i.id, "date": i.datetime.date().isoformat(), "cloud_pct": i.properties["eo:cloud_cover"]} for i in items],
        "crs": CRS, "res_m": RES_M, "local_sigma_m": LOCAL_SIGMA_M, "model_sigma_m": MODEL_SIGMA_M,
        "min_valid_scenes": MIN_VALID_SCENES, "edges": len(per_edge), "edges_sha256": edges_sha,
        "per_edge_c": {q: round(float(np.percentile(per_edge, p)), 2) for q, p in (("p5", 5), ("p50", 50), ("p95", 95))},
    }
    (data_dir / "edge_heat.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    meta = build(args.data)
    print(json.dumps({k: meta[k] for k in ("edges", "per_edge_c")}, indent=1), f"scenes: {len(meta['scenes'])}")


if __name__ == "__main__":
    main()
