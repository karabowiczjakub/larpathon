"""All four REAL modules (roles 1-3) loaded from artefacts through the backend config, like `make dev`.

The artefacts are a tiny network written in the formats of roles/04 §4.2: from A to B either along a sunny
arterial road or through a shaded park, so FASTEST and ECO must differ.
"""
import json
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyproj import Transformer
from scipy.sparse import csr_matrix

from app import create_app

SCEN = Path(__file__).resolve().parents[1] / "scenarios"
NODES = [(50.0600, 19.9300), (50.0612, 19.9315), (50.0588, 19.9315), (50.0600, 19.9330)]  # (lat, lon)
A, B = ({"lat": lat, "lon": lon} for lat, lon in (NODES[0], NODES[3]))
STREETS = [(0, 1, "primary", 140.0, "Al. Krasińskiego"), (1, 3, "primary", 140.0, "Al. Krasińskiego"),
           (0, 2, "cycleway", 150.0, "Park Jordana"), (2, 3, "cycleway", 150.0, "Park Jordana")]
EDGES = [e for u, v, *rest in STREETS for e in ((u, v, *rest), (v, u, *rest))]  # both directions
HEAT, SMOG = "heatwave_2025-07-03", "smog_2025-01-20"


def write_artefacts(out: Path) -> None:
    lat, lon = np.array(NODES).T
    x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(lon, lat)
    u, v = np.array([e[0] for e in EDGES]), np.array([e[1] for e in EDGES])
    eid = np.arange(len(EDGES))
    mid_lon, mid_lat = (lon[u] + lon[v]) / 2, (lat[u] + lat[v]) / 2
    csr = csr_matrix((eid + 1, (u, v)), shape=(len(NODES), len(NODES)))
    csr.sort_indices()
    np.savez(out / "graph.npz", indptr=csr.indptr, indices=csr.indices, perm=csr.data - 1, node_x=x, node_y=y,
             node_lon=lon, node_lat=lat, edge_u=u, edge_v=v, edge_length_m=np.array([e[3] for e in EDGES]),
             edge_mid_lon=mid_lon, edge_mid_lat=mid_lat)
    coords = np.stack([np.column_stack([lon[u], lat[u]]), np.column_stack([mid_lon, mid_lat]),
                       np.column_stack([lon[v], lat[v]])], axis=1).reshape(-1, 2)  # 3 points per edge
    np.savez(out / "edge_coords.npz", coords=coords, offs=np.arange(0, 3 * len(EDGES) + 1, 3))
    pd.DataFrame({"eid": eid, "u": u, "v": v, "length_m": [e[3] for e in EDGES],
                  "highway": [e[2] for e in EDGES], "name": [e[4] for e in EDGES]}).to_parquet(out / "edges.parquet")

    park = np.array([e[2] == "cycleway" for e in EDGES])
    az, el = list(range(0, 360, 45)), [5.0, 30.0, 60.0]
    table = np.zeros((len(EDGES), len(az), len(el)), np.uint8)
    table[park] = 255
    np.save(out / "shade.npy", table)
    np.save(out / "edge_tree_frac.npy", np.where(park, 0.9, 0.0).astype(np.float32))
    (out / "shade_bins.json").write_text(json.dumps({"az": az, "el": el}))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data = tmp_path_factory.mktemp("processed")
    write_artefacts(data)
    app = create_app({
        "DATA_DIR": str(data), "SCENARIO_DIR": str(SCEN), "USE_MOCKS": False, "MOCK_MODULES": set(),
        "STRICT_MODULES": True, "WARMUP": False, "ENV_FACTORY": "fake_modules:offline_env",
    })
    return app.test_client()


def post_route(client, points, **extra):
    return client.post("/api/route", json={"points": points, **extra})


def test_health_reports_every_module_real(client):
    d = client.get("/api/health").get_json()
    assert d["modules"] == dict.fromkeys(("graph", "shade", "env", "exposure"), "real")
    assert d["mocks"] is False and d["edges"] == len(EDGES)
    assert d["live_source"] == "fallback" and d["live_data_age_s"] is None   # no live data cached


@pytest.mark.parametrize(("scenario", "reason"), [(HEAT, "heat"), (SMOG, "air")])
def test_eco_takes_the_park_instead_of_the_arterial(client, scenario, reason):
    r = post_route(client, [A, B], scenario=scenario)
    assert r.status_code == 200
    d = r.get_json()
    fastest, eco = d["routes"]
    assert fastest["metrics"]["distance_m"] == 280 and eco["metrics"]["distance_m"] == 300
    assert eco["metrics"]["avg_discomfort"] < fastest["metrics"]["avg_discomfort"]
    assert eco["avoids"] == [f"Al. Krasińskiego ({reason})"]
    assert d["comparison"]["same_route"] is False and d["comparison"]["time_delta_min"] > 0
    assert d["conditions"]["source"] == "scenario"
    for route in d["routes"]:
        coords, segs = route["geometry"]["coordinates"], route["segments"]
        assert len(coords) == 5                                          # 2 edges × 3 points, shared node once
        assert coords[0] == pytest.approx([A["lon"], A["lat"]]) and coords[-1] == pytest.approx([B["lon"], B["lat"]])
        assert segs[0]["from"] == 0 and segs[-1]["to"] == len(coords) - 1
        assert all(a["to"] == b["from"] for a, b in pairwise(segs))
    assert fastest["segments"][0]["reason"] == reason


def test_heatwave_shade_lowers_heat_and_uv(client):
    fastest, eco = (x["metrics"] for x in post_route(client, [A, B], scenario=HEAT).get_json()["routes"])
    assert fastest["shade_pct"] == 0 and eco["shade_pct"] == 100
    assert fastest["heat_stress_min"] > eco["heat_stress_min"]
    assert fastest["uv_high_min"] > 0 and eco["uv_high_min"] == 0  # the park is fully shaded
    assert fastest["utci_avg_c"] > eco["utci_avg_c"] + 5               # and feels several degrees cooler


def test_smog_arterial_counts_as_poor_air(client):
    """NO2 at the arterial (x2.3 by the GIOŚ road calibration) pushes EAQI to "poor"; the park path stays below."""
    fastest, eco = (x["metrics"] for x in post_route(client, [A, B], scenario=SMOG).get_json()["routes"])
    assert fastest["air_poor_min"] == fastest["time_min"] and eco["air_poor_min"] == 0


def test_scenario_hour_uses_the_scenario_day_for_sun_and_shade(client):
    """The slider hour on another date still means 14:00 on 3 July 2025 (sun ~59°, not January's ~15°)."""
    d = post_route(client, [A, B], scenario=HEAT, depart_at="2026-01-15T14:00:00+01:00").get_json()
    assert d["conditions"]["timestamp"] == "2025-07-03T14:00:00+02:00"
    assert d["sun"]["elevation_deg"] > 50
    assert d["routes"][1]["metrics"]["shade_pct"] == 100
    c = client.get(f"/api/conditions?scenario={HEAT}&at=2026-01-15T14:00:00%2B01:00").get_json()
    assert c["sun"] == d["sun"] and c["temperature_c"] == d["conditions"]["temperature_c"]


def test_point_far_from_the_network_is_422_with_index(client):
    r = post_route(client, [A, {"lat": 50.0700, "lon": 19.9600}], scenario=HEAT)
    assert r.status_code == 422
    assert r.get_json()["detail"]["index"] == 1


def test_far_point_index_is_reported_in_request_order(client):
    """The real graph has no cost_matrix: order is by straight line, routing then sees [A, park, far, B]."""
    far, park = {"lat": 50.0700, "lon": 19.9600}, {"lat": NODES[2][0], "lon": NODES[2][1]}
    r = post_route(client, [A, far, park, B], scenario=HEAT, optimize_order=True)
    assert r.status_code == 422 and r.get_json()["detail"]["index"] == 1


def test_factors_choose_what_the_healthier_route_avoids(client):
    """Smog at dusk: only the air differs between the arterial and the park, so without "air" ECO == FASTEST."""
    every = post_route(client, [A, B], scenario=SMOG).get_json()
    assert every["comparison"]["same_route"] is False and every["routes"][1]["metrics"]["distance_m"] == 300
    no_air = post_route(client, [A, B], scenario=SMOG, factors=["heat", "uv"]).get_json()
    assert no_air["factors"] == ["heat", "uv"] and no_air["comparison"]["same_route"] is True
    air_only = post_route(client, [A, B], scenario=SMOG, factors=["air"]).get_json()
    assert air_only["routes"][1]["metrics"]["distance_m"] == 300
    assert air_only["routes"][1]["avoids"] == ["Al. Krasińskiego (air)"]
    heat_only = post_route(client, [A, B], scenario=HEAT, factors=["heat"]).get_json()
    assert heat_only["routes"][1]["avoids"] == ["Al. Krasińskiego (heat)"]
    # the cards keep the full model: the same "poor air" facts whichever factors were chosen
    assert no_air["routes"][0]["metrics"] == every["routes"][0]["metrics"]


def test_same_start_and_end(client):
    d = post_route(client, [A, A], scenario=SMOG).get_json()
    assert d["comparison"]["same_route"] is True
    assert all(r["metrics"]["distance_m"] == 0 for r in d["routes"])


def test_shade_layer_on_real_modules(client):
    d = client.get(f"/api/layers/shade?bbox=19.92,50.05,19.94,50.07&scenario={HEAT}").get_json()
    props = {f["properties"]["eid"]: f["properties"] for f in d["features"]}
    assert len(props) == len(STREETS)                                    # one feature per two-way street
    for p in props.values():
        assert p["shade"] == (1.0 if p["name"] == "Park Jordana" else 0.0)
    assert all(len(f["geometry"]["coordinates"]) == 3 for f in d["features"])
