"""Street heat map: Landsat processing (pipeline/heat_map_build.py) and its use in app/env/exposure.py."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from rasterio.transform import from_origin

from app.env import exposure as ex
from app.env.service import EnvironmentService
from pipeline import heat_map_build as hm

SCEN = Path(__file__).resolve().parents[1] / "scenarios"


class Graph:
    def __init__(self, n):
        self.edge_highway = np.array(["residential"] * n, dtype=object)
        self.edge_mid_lonlat = np.column_stack([np.linspace(19.9, 20.0, n), np.full(n, 50.05)])
        self.n_edges = n


@pytest.fixture
def heat_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "LUT_DIR", tmp_path)
    monkeypatch.setattr(ex, "_heat_warned", set())
    ex._graph_cache.clear()
    return tmp_path


def test_local_anomaly_keeps_the_block_and_drops_the_city_gradient():
    """A west-east trend (what the ~2 km weather model sees) is removed; a 300 m hot block stays."""
    _, x = np.mgrid[0:500, 0:500]
    field = 0.03 * x                                   # 15 °C across 15 km: city-scale trend
    field[245:255, 245:255] += 8.0                     # one hot block (300 m)
    local = hm.local_anomaly(field)
    assert local[250, 250] > 2.0                       # the block is still clearly warmer
    assert abs(local[250, 150]) < 0.1 and abs(local[250, 350]) < 0.1   # trend gone away from the block


def test_smooth_ignores_missing_pixels():
    values = np.full((50, 50), 2.0)
    values[20:30, 20:30] = np.nan                      # a cloud
    out = hm.smooth(values, 3)
    assert np.allclose(out[np.isfinite(out)], 2.0)


def test_sample_edges_reads_the_pixel_under_each_midpoint():
    transform = from_origin(560000, 250000, 30, 30)    # EPSG:2180 metres
    raster = np.zeros((100, 100), np.float32)
    raster[10, 20] = 5.0
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform(560000 + 20.5 * 30, 250000 - 10.5 * 30)
    got = hm.sample_edges(raster, transform, np.array([[lon, lat], [lon + 0.01, lat]]))
    assert got.tolist() == [5.0, 0.0]


def test_heat_map_warms_dense_blocks_and_cools_parks(heat_dir):
    np.savez(heat_dir / ex.HEAT_FILE, local_lst_anomaly_c=np.array([5.0, 0.0, -3.0], np.float32))
    env = EnvironmentService(SCEN, heat_dir, refresh=False)
    ctx = replace(env.get("heatwave_2025-07-03", None), weather_grid=(), wind_ms=1.0)
    g = Graph(3)
    e = g.n_edges
    exp = ex.compute_edge_exposure(ctx, np.zeros(e, np.float32), g, np.zeros(e, np.float32), "standard")
    assert exp.utci_c[0] > exp.utci_c[1] > exp.utci_c[2]           # block +1 °C air, park -0.6 °C air
    assert ex.street_heat(np.array([5.0, -3.0]), 1.0) == pytest.approx([1.0, -0.6])


def test_wind_weakens_and_caps_limit_the_street_heat():
    assert ex.street_heat(5.0, 8.0) == pytest.approx(0.3)           # strong wind: 30% of the calm value
    assert ex.street_heat(50.0, 0.5) == ex.HEAT_CAP_C               # never more than the cap


def test_missing_or_foreign_heat_map_changes_nothing(heat_dir):
    g = Graph(3)
    assert ex.edge_heat(g) == 0.0                                    # no file
    ex._graph_cache.clear()
    np.savez(heat_dir / ex.HEAT_FILE, local_lst_anomaly_c=np.zeros(7, np.float32))
    assert ex.edge_heat(g) == 0.0                                    # map of another graph
