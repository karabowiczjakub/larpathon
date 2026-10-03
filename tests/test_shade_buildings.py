import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from pipeline.p03_buildings import (
    building_height,
    empty_polygons,
    metric_polygons,
    parse_lod1,
    prepare_buildings,
    read_osm_pbf,
)
from pipeline.p04_height_raster import build_height_raster


@pytest.mark.parametrize(
    "tags, primary, expected, source",
    [
        ({"height": "10", "building:levels": "4"}, "20", 20, "gugik_measuredHeight"),
        ({"height": "10 m"}, None, 10, "osm_height"),
        ({"height": "10,5"}, -1, 10.5, "osm_height"),
        ({"height": "10 ft"}, None, 3.048, "osm_height"),
        ({"height": "NaN", "building:levels": "4"}, None, 13.8, "osm_levels_estimate"),
        ({"height": "-8", "building": "house"}, None, 7, "default_house"),
        ({"height": "inf", "building": "apartments"}, None, 15, "default_apartments"),
        ({"height": "9999", "building": "commercial"}, None, 12, "default_commercial"),
        ({"height": "12;18", "building:levels": "-2"}, None, 9, "default_other"),
        ({"height": True, "building:levels": "10000"}, None, 9, "default_other"),
        ({}, None, 9, "default_other"),
        ({"building": "retail"}, None, 9, "default_other"),  # PLAN overrides role note.
    ],
)
def test_height_hierarchy(tags, primary, expected, source):
    height, provenance = building_height(tags, primary)
    assert height == pytest.approx(expected)
    assert provenance == source


def test_polygon_repair_multipart_and_bad_geometries():
    bow = Polygon([(0, 0), (4, 4), (4, 0), (0, 4), (0, 0)])
    multi = MultiPolygon([box(10, 0, 12, 2), box(14, 0, 16, 2)])
    data = gpd.GeoDataFrame(
        geometry=[bow, multi, None, LineString([(0, 0), (1, 1)])], crs=2180
    )
    result = metric_polygons(data)
    assert len(result) == 2
    assert result.is_valid.all()
    assert result.geometry.iloc[1].area == 8


def test_projection_boundary():
    osm = gpd.GeoDataFrame(
        {"building": ["house"]}, geometry=[box(19.94, 50.06, 19.941, 50.061)], crs=4326
    )
    result = prepare_buildings(osm)
    assert result.crs.to_epsg() == 2180
    assert 7000 < result.geometry.iloc[0].area < 9000
    assert osm.crs.to_epsg() == 4326
    with pytest.raises(ValueError, match="CRS"):
        prepare_buildings(osm.set_crs(None, allow_override=True))


def test_lod1_overrides_osm_and_preserves_fallbacks():
    osm = gpd.GeoDataFrame(
        {"height": [11, 12, None], "building": ["yes", "yes", "house"]},
        geometry=[box(0, 0, 4, 4), box(10, 0, 14, 4), box(20, 0, 24, 4)],
        crs=2180,
    )
    primary = gpd.GeoDataFrame(
        {"measured_height": [21, None]},
        geometry=[box(0, 0, 4, 4), box(10, 0, 14, 4)],
        crs=2180,
    )
    result = prepare_buildings(osm, primary)
    assert result.height.tolist() == [21, 12, 7]
    assert result.height_source.tolist() == [
        "gugik_measuredHeight",
        "osm_height",
        "default_house",
    ]


def test_empty_buildings_and_raster(tmp_path):
    bld = prepare_buildings(empty_polygons())
    height, trees, _ = build_height_raster(
        bld, empty_polygons(), (0, 0, 10, 10), tmp_path / "heights_2m.tif"
    )
    assert not height.any() and not trees.any()
    assert height.dtype == np.uint8


def test_raster_keeps_trees_separate_and_tallest_obstacle(tmp_path):
    import rasterio

    bld = gpd.GeoDataFrame(
        {"height": [20, 5]}, geometry=[box(0, 0, 6, 6), box(0, 0, 6, 6)], crs=2180
    )
    tree = gpd.GeoDataFrame(geometry=[box(4, 0, 10, 6)], crs=2180)
    height, canopy, transform = build_height_raster(
        bld, tree, (0, 0, 10, 10), tmp_path / "heights_2m.tif"
    )
    assert height[3, 0] == 20 and canopy[3, 0] == 0
    assert height[3, 2] == 20 and canopy[3, 2] == 12
    assert height[3, 4] == 12
    assert transform.a == 2 and transform.e == -2
    with rasterio.open(tmp_path / "heights_2m.tif") as src:
        assert src.crs.to_epsg() == 2180
        np.testing.assert_array_equal(src.read(1), height)


def citygml(srs="urn:ogc:def:crs:EPSG::2180"):
    def surface(z):
        return f"""<gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>
        10 20 {z} 20 20 {z} 20 30 {z} 10 30 {z} 10 20 {z}
        </gml:posList></gml:LinearRing></gml:exterior></gml:Polygon>"""

    return f'''<CityModel xmlns:gml="http://www.opengis.net/gml"
    xmlns:bldg="http://www.opengis.net/citygml/building/2.0" srsName="{srs}">
    <member><bldg:Building><bldg:measuredHeight uom="m">12.5</bldg:measuredHeight>
    {surface(212.5)}{surface(200)}</bldg:Building></member>
    <member><bldg:Building/></member></CityModel>'''


def test_lod1_parser_lowest_surface(tmp_path, caplog):
    path = tmp_path / "fixture.gml"
    path.write_text(citygml())
    parsed = parse_lod1(str(path))
    assert len(parsed) == 1
    assert parsed.geometry.iloc[0].equals(box(10, 20, 20, 30))
    result = prepare_buildings(empty_polygons(), parsed)
    assert result.height.iloc[0] == 12.5
    assert "Skipped 1" in caplog.text


def test_lod1_wrong_crs_and_missing_file(tmp_path):
    path = tmp_path / "fixture.gml"
    path.write_text(citygml("EPSG:4326"))
    with pytest.raises(ValueError, match="2180"):
        parse_lod1(str(path))
    with pytest.raises(FileNotFoundError):
        parse_lod1(str(tmp_path / "absent.gml"))


def test_osm_fallback_with_local_extract(tmp_path):
    path = tmp_path / "small.osm"
    path.write_text("""<osm version="0.6">
    <node id="1" lat="50.06" lon="19.94"/>
    <node id="2" lat="50.06" lon="19.9401"/>
    <node id="3" lat="50.0601" lon="19.9401"/>
    <node id="4" lat="50.0601" lon="19.94"/>
    <node id="5" lat="50.061" lon="19.94"><tag k="natural" v="tree"/></node>
    <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="building" v="house"/><tag k="building:levels" v="2"/></way></osm>""")
    bld, trees = read_osm_pbf(path)
    assert len(bld) == 1 and len(trees) == 1
    assert prepare_buildings(bld).height.iloc[0] == 7.4
    assert trees.crs.to_epsg() == 2180
    assert 28 < trees.geometry.iloc[0].area < 29
