import json
import zipfile

import geopandas as gpd
import httpx
import numpy as np
import pytest
from shapely.geometry import LineString, box, mapping

from app.shade.model import ShadeModel
from pipeline.p03_buildings import empty_polygons, prepare_buildings
from pipeline.shade_build import (
    build_artifacts,
    download_lod1,
    fetch_tall_green,
    main,
    preview_grid,
)
from scripts.shade_report import write_report


def test_msip_pagination_and_projection():
    offsets = []

    def respond(request):
        offset = int(request.url.params["resultOffset"])
        offsets.append(offset)
        features = (
            [
                {
                    "type": "Feature",
                    "properties": {"class_name": "200 Zieleń wysoka"},
                    "geometry": mapping(
                        box(
                            19.94 + offset * 0.001,
                            50.06,
                            19.941 + offset * 0.001,
                            50.061,
                        )
                    ),
                }
            ]
            if offset < 2
            else []
        )
        return httpx.Response(200, json={"features": features})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = fetch_tall_green(client=client)
    assert offsets == [0, 1, 2]
    assert len(result) == 2 and result.crs.to_epsg() == 2180
    assert result.height.tolist() == [12, 12]
    assert set(result.tree_source) == {"msip_2015_assumed_12m"}


@pytest.mark.parametrize("payload", [{"error": {"code": 500}}, {}, {"features": []}])
def test_msip_empty_or_failed_response(payload):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        if payload == {"features": []}:
            assert fetch_tall_green(client=client).empty
        else:
            with pytest.raises(ValueError):
                fetch_tall_green(client=client)


def test_msip_repeated_page_is_rejected():
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": mapping(box(19.94, 50.06, 19.941, 50.061)),
    }
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"features": [feature]})
            )
        ) as client,
        pytest.raises(ValueError, match="repeated"),
    ):
        fetch_tall_green(client=client)


@pytest.fixture
def local_data(tmp_path):
    edges = gpd.GeoDataFrame(
        {"eid": [0]},
        geometry=[LineString([(567000, 244000), (567040, 244000)])],
        crs=2180,
    )
    path = tmp_path / "input_edges.parquet"
    edges.to_parquet(path)
    buildings = prepare_buildings(
        gpd.GeoDataFrame(
            {"height": [20]}, geometry=[box(567000, 244005, 567020, 244025)], crs=2180
        )
    )
    return path, buildings


def test_pipeline_cache_covers_inputs_and_parameters(local_data, tmp_path):
    path, buildings = local_data
    output = tmp_path / "processed"
    trees = empty_polygons()
    assert build_artifacts(path, buildings, trees, output)
    assert not build_artifacts(path, buildings, trees, output)
    assert build_artifacts(path, buildings, trees, output, sample_step=20)
    buildings["height"] = 30
    assert build_artifacts(path, buildings, trees, output, sample_step=20)
    trees = gpd.GeoDataFrame(geometry=[box(567000, 243998, 567040, 244002)], crs=2180)
    assert build_artifacts(path, buildings, trees, output, sample_step=20)
    assert ShadeModel.load(output, 1).edge_tree_frac[0] == 1
    assert build_artifacts(path, buildings, trees, output, coarse=True)
    assert np.load(output / "shade.npy").shape == (1, 4, 4)


def test_cli_missing_sources_are_explicit(local_data, tmp_path, caplog):
    path, _ = local_data
    output = tmp_path / "processed"
    with pytest.raises(SystemExit):
        main(["--edges", str(path), "--output", str(output)])
    main(
        [
            "--edges",
            str(path),
            "--output",
            str(output),
            "--allow-missing-buildings",
            "--allow-missing-trees",
        ]
    )
    assert "Explicit fallback" in caplog.text
    metadata = json.loads((output / "shade_bins.json").read_text())["metadata"]
    assert metadata["missing_buildings"] and metadata["missing_trees"]


def test_source_outages_fall_back_to_local_osm(
    local_data, tmp_path, monkeypatch, caplog
):
    path, _ = local_data
    osm = gpd.GeoDataFrame(
        {"building": ["house"]},
        geometry=[box(567000, 244005, 567020, 244025)],
        crs=2180,
    )
    trees = gpd.GeoDataFrame(geometry=[box(567000, 243998, 567040, 244002)], crs=2180)
    monkeypatch.setattr("pipeline.shade_build.read_osm_pbf", lambda path: (osm, trees))

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("offline fixture")

    monkeypatch.setattr("pipeline.shade_build.download_lod1", unavailable)
    monkeypatch.setattr("pipeline.shade_build.fetch_tall_green", unavailable)
    output = tmp_path / "processed"
    main(
        [
            "--edges",
            str(path),
            "--output",
            str(output),
            "--osm-pbf",
            "mock.pbf",
            "--download",
        ]
    )
    assert "LoD1 unavailable" in caplog.text and "MSIP unavailable" in caplog.text
    assert ShadeModel.load(output, 1).edge_tree_frac[0] == 1


def test_preview_grid_and_report(local_data, tmp_path):
    grid = preview_grid((567000, 244000, 567100, 244100))
    assert len(grid) == 4 and grid.crs.to_epsg() == 2180
    path, buildings = local_data
    output = tmp_path / "processed"
    build_artifacts(path, buildings, empty_polygons(), output)
    report = write_report(output, output / "report.png", label="Synthetic fixture")
    assert (output / "report.png").stat().st_size > 1000
    assert len(report["times"]) == 2
    assert report["times"][1]["elevation_deg"] < report["times"][0]["elevation_deg"]


def test_lod1_cached_zip_without_network(tmp_path, monkeypatch):
    with zipfile.ZipFile(tmp_path / "lod1_1261.zip", "w") as archive:
        archive.writestr("tile/test.gml", "<CityModel/>")

    def no_network(*args, **kwargs):
        raise AssertionError("Cached archive must not be downloaded again")

    monkeypatch.setattr("httpx.stream", no_network)
    pattern = download_lod1(tmp_path)
    assert pattern.endswith("lod1/**/*.gml")
    assert (tmp_path / "lod1/tile/test.gml").read_text() == "<CityModel/>"


def test_preview_does_not_overwrite_production_artifacts():
    with pytest.raises(SystemExit):
        main(["--preview-grid", "566000", "243000", "566100", "243100"])
