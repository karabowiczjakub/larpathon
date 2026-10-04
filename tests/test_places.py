"""Place search (app/places.py) and /api/places: Photon is faked, no network."""
import httpx
import pytest

from app import create_app
from app.places import PlaceSearch, describe, describe_point


def feature(lon, lat, **props):
    return {"geometry": {"coordinates": [lon, lat]}, "properties": {"city": "Kraków", **props}}


RYNEK = [
    feature(19.9371, 50.0615, name="Rynek Główny", osm_key="place", osm_value="square", district="Stare Miasto"),
    feature(19.9390, 50.0620, name="Rynek Główny", osm_key="highway", osm_value="living_street", district="Stare Miasto"),
    feature(19.9378, 50.0620, name="Rynek Podziemny", osm_key="tourism", osm_value="museum", street="Rynek Główny",
            housenumber="1", locality="Stare Miasto"),
    feature(21.0122, 52.2297, name="Rynek Główny", osm_key="place", osm_value="square", city="Warszawa"),  # outside
]


class Photon:
    """Records the calls; answers with `features`, or fails with `error`."""

    def __init__(self, features=(), error=None):
        self.features, self.error, self.calls = list(features), error, []

    def __call__(self, url, params, timeout, headers):
        self.calls.append((url, params))
        if self.error:
            raise self.error
        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"features": self.features}, request=request)


def test_search_names_dedupes_and_keeps_to_krakow():
    photon = Photon(RYNEK)
    out = PlaceSearch("https://photon.test", get=photon).search("  rynek   glowny ", near=(50.06, 19.94))
    assert out["available"] is True
    assert [(r["name"], r["kind"], r["detail"]) for r in out["results"]] == [
        ("Rynek Główny", "square", "Stare Miasto"),
        ("Rynek Podziemny", "museum", "Rynek Główny 1, Stare Miasto"),
    ]
    url, params = photon.calls[0]
    assert url == "https://photon.test/api/" and params["q"] == "rynek glowny"
    assert params["bbox"] == "19.75,49.95,20.25,50.15" and (params["lat"], params["lon"]) == (50.06, 19.94)


def test_search_is_cached_and_ignores_a_map_centre_outside_krakow():
    photon = Photon(RYNEK)
    places = PlaceSearch(get=photon)
    places.search("Rynek glowny", near=(52.2, 21.0))
    places.search("rynek glowny", near=(52.2, 21.0))
    assert len(photon.calls) == 1 and "lat" not in photon.calls[0][1]


def test_provider_failure_is_reported_and_retried():
    photon = Photon(error=httpx.ConnectError("offline"))
    places = PlaceSearch(get=photon)
    assert places.search("wawel") == {"results": [], "available": False}
    assert places.reverse(50.06, 19.94) == {"place": None, "available": False}
    places.search("wawel")
    assert len(photon.calls) == 3                                   # failures are not cached


def test_addresses_and_kinds():
    house = feature(19.93, 50.08, street="Rusznikarska", housenumber="17", osm_key="building", osm_value="yes",
                    locality="Krowodrza Górka")
    assert describe(house) | {"lat": 0, "lon": 0} == {"name": "Rusznikarska 17", "kind": "address",
                                                      "detail": "Krowodrza Górka", "lat": 0, "lon": 0}
    stop = feature(19.95, 50.07, name="Dworzec Główny", osm_key="highway", osm_value="bus_stop")
    assert describe(stop)["kind"] == "bus stop"
    assert describe(feature(20.06, 49.98, name="Wieliczka", osm_key="place", osm_value="town", city="Wieliczka"))["detail"] == ""
    assert describe(feature(19.9, 50.0)) is None                     # nothing to call it


def test_a_clicked_point_is_named_by_its_address():
    bar = feature(19.945, 50.051, name="Volver.", osm_value="bar", street="Nowa", locality="Kazimierz")
    assert (describe_point(bar)["name"], describe_point(bar)["detail"]) == ("Nowa", "Kazimierz")
    square = feature(20.037, 50.072, name="Plac Centralny", locality="Nowa Huta")
    assert describe_point(square)["name"] == "Plac Centralny"


@pytest.fixture
def places_client(mock_modules):
    photon = Photon(RYNEK)
    app = create_app({"WARMUP": False}, modules=mock_modules, places=PlaceSearch(get=photon))
    return app.test_client(), photon


def test_places_endpoints(places_client):
    client, photon = places_client
    d = client.get("/api/places?q=rynek&lat=50.06&lon=19.94").get_json()
    assert d["available"] and d["results"][0]["name"] == "Rynek Główny"
    assert client.get("/api/places?q=r").status_code == 400          # too short to search
    r = client.get("/api/places/reverse?lat=50.0615&lon=19.9371").get_json()
    assert r["place"]["name"] == "Rynek Główny" and photon.calls[-1][0].endswith("/reverse")
    assert client.get("/api/places/reverse?lat=52.2&lon=21.0").status_code == 400   # outside Kraków
