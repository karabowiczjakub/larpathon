import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

from app.shade.model import ShadeModel
from pipeline.p03_buildings import empty_polygons, prepare_buildings
from pipeline.p04_height_raster import build_height_raster
from pipeline.p05_shade import (
    compute_shade_table,
    edge_points,
    make_sampler,
    read_height_raster,
    save_shade_artifacts,
    shaded_points,
)


def edges_of(*geometries, crs=2180):
    return gpd.GeoDataFrame(
        {"eid": np.arange(len(geometries))}, geometry=list(geometries), crs=crs
    )


def test_sampler_floors_negative_coordinates():
    sample = make_sampler(np.full((2, 2), 20, np.uint8), from_origin(0, 4, 2, 2))
    values = sample(np.array([-0.1, 0, 3.9, 4, 1]), np.array([3, 4.1, 0.1, 3, 0]))
    assert values.tolist() == [0, 0, 20, 0, 0]


@pytest.mark.parametrize(
    "azimuth, building_bounds",
    [
        (0, (-2, 8, 2, 12)),
        (90, (8, -2, 12, 2)),
        (180, (-2, -12, 2, -8)),
        (270, (-12, -2, -8, 2)),
    ],
)
def test_shadow_direction_and_known_height(azimuth, building_bounds):
    bld = gpd.GeoDataFrame({"height": [12]}, geometry=[box(*building_bounds)], crs=2180)
    height, _, tr = build_height_raster(bld, empty_polygons(), (-150, -150, 150, 150))
    sample = make_sampler(height, tr)
    # At 8 m, a 45-degree ray is at 9.5 m, below the 12 m building.
    assert shaded_points(np.array([0]), np.array([0]), sample, azimuth, 45)[0]
    assert not shaded_points(np.array([0]), np.array([0]), sample, azimuth + 180, 45)[0]
    assert not shaded_points(np.array([0]), np.array([0]), sample, azimuth, 65)[0]


def test_low_sun_and_maximum_distance():
    bld = gpd.GeoDataFrame({"height": [255]}, geometry=[box(122, -4, 128, 4)], crs=2180)
    height, _, tr = build_height_raster(bld, empty_polygons(), (-150, -150, 150, 150))
    sample = make_sampler(height, tr)
    assert not shaded_points(np.array([0]), np.array([0]), sample, 90, 1e-12)[0]
    assert shaded_points(np.array([4]), np.array([0]), sample, 90, 1e-12)[0]
    assert shaded_points(np.array([0]), np.array([0]), sample, 90, -1)[0]


def test_deduplication_respects_actual_geometry():
    line = LineString([(0, 0), (0, 60)])
    other = LineString([(0, 0), (30, 30), (0, 60)])
    edges = edges_of(line, LineString(list(line.coords)[::-1]), other)
    edges["u"] = [1, 2, 1]
    edges["v"] = [2, 1, 2]
    _, _, owner, representatives = edge_points(edges)
    assert representatives.tolist() == [0, 0, 2]
    assert set(owner) == {0, 2}


def test_edge_crs_and_eid():
    edges = edges_of(LineString([(19.94, 50.06), (19.941, 50.06)]), crs=4326)
    px, py, _, _ = edge_points(edges)
    assert len(px) >= 4
    assert px.min() > 500_000 and py.min() > 200_000
    edges["eid"] = 3
    with pytest.raises(ValueError, match="eid"):
        edge_points(edges)


def test_fraction_determinism_and_tree_building_separation():
    bld = gpd.GeoDataFrame({"height": [20]}, geometry=[box(0, 0, 10, 20)], crs=2180)
    trees = gpd.GeoDataFrame(geometry=[box(40, 0, 50, 20)], crs=2180)
    height, tree, tr = build_height_raster(bld, trees, (-150, -150, 200, 200))
    edges = edges_of(
        LineString([(5, 1), (5, 19)]),
        LineString([(45, 1), (45, 19)]),
        LineString([(0, 1), (20, 1)]),
        LineString([(100, 80), (100, 100)]),
    )
    a, canopy = compute_shade_table(edges, height, tr, tree, chunk=1)
    b, _ = compute_shade_table(edges, height, tr, tree, chunk=100)
    np.testing.assert_array_equal(a, b)
    assert a.shape == (4, 16, 8) and a.dtype == np.uint8
    assert (a[0] == 255).all() and (a[1] == 255).all()
    assert a[2, 0, -1] == 128  # Exactly one of two equal-length cells is shaded.
    assert (a[3] == 0).all()
    assert canopy.tolist() == [0, 1, 0, 0]


def test_empty_invalid_edges_preserve_rows(caplog):
    edges = edges_of(None, LineString([(0, 0), (0, 0)]))
    height = np.zeros((10, 10), np.uint8)
    shade, tree = compute_shade_table(edges, height, from_origin(0, 20, 2, 2), height)
    assert shade.shape == (2, 16, 8) and not shade.any() and not tree.any()
    assert "zero daytime shade" in caplog.text
    empty, _ = compute_shade_table(edges_of(), height, from_origin(0, 20, 2, 2), height)
    assert empty.shape == (0, 16, 8)


def test_offline_artifact_roundtrip_and_graph_change(tmp_path):
    edges = edges_of(LineString([(0, 0), (10, 0)]))
    path = tmp_path / "edges.parquet"
    edges.to_parquet(path)
    height, tree, tr = build_height_raster(
        prepare_buildings(empty_polygons()), empty_polygons(), (-150, -150, 150, 150)
    )
    table, fraction = compute_shade_table(edges, height, tr, tree)
    save_shade_artifacts(tmp_path, table, fraction, path)
    assert ShadeModel.load(tmp_path, 1).edge_tree_frac.tolist() == [0]
    edges.geometry = [LineString([(10, 0), (20, 0)])]
    edges.to_parquet(path)
    with pytest.raises(ValueError, match="Graph changed"):
        ShadeModel.load(tmp_path, 1)


def test_reject_nonmetric_raster(tmp_path):
    path = tmp_path / "height.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(19, 50, 0.1, 0.1),
    ) as dst:
        dst.write(np.zeros((2, 2), np.uint8), 1)
    with pytest.raises(ValueError, match="2180"):
        read_height_raster(path)
