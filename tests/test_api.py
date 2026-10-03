import json
from itertools import pairwise

import numpy as np
import pytest
from conftest import BLONIA, KAZIMIERZ, RYNEK

from app.contracts import NoRoute
from app.engine.metrics import METRIC_KEYS
from app.mocks import mock_exposure

HEAT = "heatwave_2025-07-03"


def post_route(client, points, **extra):
    return client.post("/api/route", json={"points": points, **extra})


def strict_json(response):
    """Browsers reject NaN/Infinity in JSON, so the tests do too."""
    def reject(token):
        raise AssertionError(f"non-JSON token {token}")

    return json.loads(response.get_data(as_text=True), parse_constant=reject)


# ---------- happy path / frontend contract (roles/04 §4.4, roles/05) ----------
def test_route_matches_frontend_contract(client):
    r = post_route(client, [RYNEK, BLONIA], scenario=HEAT, profile="standard")
    assert r.status_code == 200 and r.mimetype == "application/json"
    d = strict_json(r)
    assert [x["id"] for x in d["routes"]] == ["fastest", "eco"]
    for route in d["routes"]:
        assert {"label", "color", "geometry", "metrics", "segments", "avoids"} <= set(route)
        coords = route["geometry"]["coordinates"]
        assert route["geometry"]["type"] == "LineString" and len(coords) >= 2
        assert all(19.7 < lon < 20.3 and 49.9 < lat < 50.2 for lon, lat in coords)
        assert set(route["metrics"]) == set(METRIC_KEYS)
        segs = route["segments"]
        assert segs[0]["from"] == 0 and segs[-1]["to"] == len(coords) - 1
        assert all(a["to"] == b["from"] for a, b in pairwise(segs))
        assert all(0 <= s["discomfort"] <= 1 and s["reason"] in {"ok", "heat", "air", "uv"} for s in segs)
    assert {"same_route", "time_delta_min", "time_delta_pct", "pm25_dose_delta_pct", "shade_delta_pp",
            "heat_stress_delta_min"} <= set(d["comparison"])
    assert {"source", "temperature_c", "uv_index", "pm10", "timestamp"} <= set(d["conditions"])
    assert set(d["sun"]) == {"azimuth_deg", "elevation_deg"}
    assert d["timing_ms"]["total"] >= 0 and d["order"] == [0, 1]


def test_eco_trades_time_for_comfort_in_heatwave(client):
    d = post_route(client, [RYNEK, BLONIA], scenario=HEAT).get_json()
    fastest, eco = (x["metrics"] for x in d["routes"])
    assert eco["time_min"] >= fastest["time_min"]
    assert eco["avg_discomfort"] <= fastest["avg_discomfort"]


def test_route_starts_and_ends_near_requested_points(client):
    d = post_route(client, [RYNEK, BLONIA]).get_json()
    coords = d["routes"][0]["geometry"]["coordinates"]
    assert np.allclose(coords[0], [RYNEK["lon"], RYNEK["lat"]], atol=0.004)
    assert np.allclose(coords[-1], [BLONIA["lon"], BLONIA["lat"]], atol=0.004)


def test_via_point_is_visited(client):
    d = post_route(client, [RYNEK, BLONIA, KAZIMIERZ]).get_json()
    coords = np.array(d["routes"][0]["geometry"]["coordinates"])
    nearest = np.abs(coords - [BLONIA["lon"], BLONIA["lat"]]).sum(axis=1).min()
    assert nearest < 0.006


def test_optimize_order_keeps_ends_and_shortens_trip(client):
    far, near = {"lat": 50.0900, "lon": 20.0300}, {"lat": 50.0620, "lon": 19.9300}
    points = [RYNEK, far, near, {"lat": 50.0950, "lon": 20.0400}]
    plain = post_route(client, points).get_json()
    best = post_route(client, points, optimize_order=True).get_json()
    assert best["order"][0] == 0 and best["order"][-1] == 3 and sorted(best["order"]) == [0, 1, 2, 3]
    assert best["order"] == [0, 2, 1, 3]
    assert best["routes"][0]["metrics"]["time_min"] < plain["routes"][0]["metrics"]["time_min"]


def test_same_start_and_end_returns_empty_route(client):
    d = post_route(client, [RYNEK, RYNEK]).get_json()
    assert d["comparison"]["same_route"] is True
    for route in d["routes"]:
        assert len(route["geometry"]["coordinates"]) == 2 and route["metrics"]["distance_m"] == 0


def test_naive_depart_at_is_krakow_time(client):
    d = post_route(client, [RYNEK, BLONIA], scenario=HEAT, depart_at="2025-07-03T22:00:00").get_json()
    assert d["conditions"]["timestamp"] == "2025-07-03T22:00:00+02:00"
    assert d["sun"]["elevation_deg"] < 0


def test_profiles_change_travel_time(client):
    times = {
        p: post_route(client, [RYNEK, BLONIA], profile=p).get_json()["routes"][0]["metrics"]["time_min"]
        for p in ("athlete", "standard", "senior")
    }
    assert times["athlete"] < times["standard"] < times["senior"]


def test_concurrent_requests_match_sequential(client):
    """waitress serves requests from threads; Engine and modules must not share per-request state."""
    from concurrent.futures import ThreadPoolExecutor

    app = client.application
    jobs = [(scenario, profile) for scenario in (HEAT, "smog_2025-01-20", "live")
            for profile in ("standard", "asthma", "athlete")] * 2

    def run(job):
        r = post_route(app.test_client(), [RYNEK, BLONIA, KAZIMIERZ], scenario=job[0], profile=job[1])
        d = r.get_json()
        return [x["geometry"]["coordinates"] for x in d["routes"]], [x["metrics"] for x in d["routes"]]

    expected = [run(job) for job in jobs]
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(run, jobs)) == expected


# ---------- errors: always JSON ----------
@pytest.mark.parametrize("body", [
    {"points": []},
    {"points": [RYNEK]},
    {"points": [RYNEK] * 6},
    {"points": [{"lat": 52.2, "lon": 21.0}, RYNEK]},
    {"points": [RYNEK, {"lat": "x", "lon": 19.9}]},
    {"points": [RYNEK, BLONIA], "profile": "cyborg"},
    {"points": [RYNEK, BLONIA], "depart_at": "tomorrow"},
    {"points": [RYNEK, BLONIA], "scenario": "volcano"},
    [RYNEK, BLONIA],
])
def test_invalid_requests_return_400(client, body):
    r = client.post("/api/route", json=body)
    assert r.status_code == 400
    assert strict_json(r)["error"] == "validation"


def test_malformed_json_returns_400(client):
    r = client.post("/api/route", data="{not json", content_type="application/json")
    assert r.status_code == 400 and r.get_json()["error"] == "validation"


def test_point_far_from_network_returns_422_with_index(client):
    r = post_route(client, [RYNEK, {"lat": 50.145, "lon": 20.24}])
    assert r.status_code == 422
    d = r.get_json()
    assert d["error"] == "point_outside_area" and d["detail"]["index"] == 1


class _NoRouteGraph:
    def __init__(self, graph):
        self._graph = graph

    def __getattr__(self, name):
        return getattr(self._graph, name)

    def route(self, points, edge_cost):
        raise NoRoute("no path between point 0 and 1")


def test_no_route_returns_404(make_client, mock_graph):
    r = post_route(make_client(graph=_NoRouteGraph(mock_graph)), [RYNEK, BLONIA])
    assert r.status_code == 404 and r.get_json()["error"] == "no_route"


def test_module_crash_returns_json_500(make_client):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    r = post_route(make_client(exposure=broken), [RYNEK, BLONIA])
    assert r.status_code == 500 and r.get_json() == {"error": "internal"}


def test_contract_violation_returns_500(make_client):
    def wrong_shape(ctx, shade, graph, tree_frac, profile):
        exp = mock_exposure(ctx, shade, graph, tree_frac, profile)
        return exp.__class__(**{**exp.__dict__, "discomfort": exp.discomfort[:10]})

    r = post_route(make_client(exposure=wrong_shape), [RYNEK, BLONIA])
    assert r.status_code == 500


def test_nan_from_modules_never_breaks_json(make_client):
    def nan_exposure(ctx, shade, graph, tree_frac, profile):
        exp = mock_exposure(ctx, shade, graph, tree_frac, profile)
        pm25 = np.full_like(exp.pm25, np.nan)
        disc = exp.discomfort.copy()
        disc[::3] = np.nan
        return exp.__class__(**{**exp.__dict__, "pm25": pm25, "discomfort": disc})

    r = post_route(make_client(exposure=nan_exposure), [RYNEK, BLONIA], scenario=HEAT)
    assert r.status_code == 200
    d = strict_json(r)
    assert d["routes"][0]["metrics"]["pm25_dose_ug"] is None


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.get_json()["error"] == "not_found"


def test_wrong_method_is_json_405(client):
    r = client.delete("/api/route")
    assert r.status_code == 405 and r.get_json()["error"] == "method_not_allowed"
    assert client.get("/api/route").get_json()["error"] in {"not_found", "method_not_allowed"}


# ---------- other endpoints ----------
def test_scenarios(client):
    d = client.get("/api/scenarios").get_json()
    ids = [s["id"] for s in d]
    assert ids[0] == "live" and HEAT in ids and "smog_2025-01-20" in ids
    assert all("default_at" in s for s in d if s["id"] != "live")


def test_conditions_default_and_at(client):
    d = client.get(f"/api/conditions?scenario={HEAT}").get_json()
    assert d["temperature_c"] == 34.5 and d["sun"]["elevation_deg"] > 30
    night = client.get(f"/api/conditions?scenario={HEAT}&at=2025-07-03T23:00:00%2B02:00").get_json()
    assert night["sun"]["elevation_deg"] < 0 and night["uv_index"] == 0


@pytest.mark.parametrize("query", ["scenario=volcano", "at=yesterday"])
def test_conditions_bad_query_400(client, query):
    assert client.get(f"/api/conditions?{query}").status_code == 400


def test_health(client, mock_graph):
    d = client.get("/api/health").get_json()
    assert d["ok"] is True and d["mocks"] is True
    assert d["edges"] == mock_graph.n_edges
    assert set(d["modules"]) == {"graph", "shade", "env", "exposure"}


def test_shade_layer_is_geojson_inside_bbox(client):
    bbox = (19.92, 50.05, 19.95, 50.07)
    r = client.get(f"/api/layers/shade?bbox={','.join(map(str, bbox))}&scenario={HEAT}&profile=asthma")
    assert r.status_code == 200
    d = strict_json(r)
    assert d["type"] == "FeatureCollection" and d["truncated"] is False and 0 < len(d["features"]) < 5000
    assert d["at"] == "2025-07-03T14:00:00+02:00"
    eids = [f["properties"]["eid"] for f in d["features"]]
    assert len(eids) == len(set(eids))
    for f in d["features"]:
        p, coords = f["properties"], f["geometry"]["coordinates"]
        assert 0 <= p["shade"] <= 1 and 0 <= p["discomfort"] <= 1 and p["reason"] in {"ok", "heat", "air", "uv"}
        assert len(coords) >= 2
        mid = np.mean([coords[0], coords[-1]], axis=0)
        assert bbox[0] <= mid[0] <= bbox[2] and bbox[1] <= mid[1] <= bbox[3]


def test_shade_layer_keeps_one_direction_and_caps_features(client):
    d = client.get("/api/layers/shade?bbox=19.79,49.97,20.22,50.13").get_json()
    assert d["truncated"] is True and len(d["features"]) == 5000


@pytest.mark.parametrize("query", ["", "bbox=19.9,50.0,20.0", "bbox=a,b,c,d", "bbox=19.95,50.06,19.90,50.07",
                                   "bbox=19.9,50.0,20.0,50.1&profile=cyborg", "bbox=19.9,50.0,20.0,50.1&scenario=volcano"])
def test_shade_layer_bad_query_400(client, query):
    r = client.get(f"/api/layers/shade?{query}")
    assert r.status_code == 400 and r.get_json()["error"] == "validation"
