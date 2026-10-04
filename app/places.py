"""Place search for the waypoint box: "rynek glowny" -> Rynek Główny (lat, lon), and a street name for a
clicked point. Adapter over Photon (komoot, OpenStreetMap data, no key, made for search-as-you-type);
another provider only needs the same two methods. Never raises: a provider failure is reported as
"available": False and the rider can still click the map."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import httpx
from cachetools import TTLCache

from .schemas import LAT_RANGE, LON_RANGE

log = logging.getLogger(__name__)
PHOTON_URL = "https://photon.komoot.io"
USER_AGENT = "BiKing/1.0 (HackYeah Krakow bike routing demo)"  # headers are ASCII only
TIMEOUT_S = 4.0
MAX_RESULTS = 6
CACHE_TTL_S = 3600


def _inside(lat: float, lon: float) -> bool:
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]


def _area(p: dict) -> list[str]:
    """Neighbourhood, and the town when it is not Kraków (the box also covers its neighbours)."""
    out = [p.get("locality") or p.get("district")]
    if p.get("city") and p.get("city") != "Kraków":
        out.append(p["city"])
    return [x for x in out if x]


def _address(p: dict) -> str | None:
    return " ".join(x for x in (p.get("street"), p.get("housenumber")) if x) or None


def _kind(p: dict) -> str:
    """What it is, to tell apart hits with one name (Wawel: the hill, a sweet shop, a bus stop)."""
    key, value = p.get("osm_key"), p.get("osm_value") or ""
    if key == "highway":
        return "bus stop" if value in {"bus_stop", "platform"} else "street"
    if key == "building" or value in {"yes", "house"}:
        return "address" if p.get("housenumber") else ""
    return value.replace("_", " ")


def describe(feature: dict) -> dict | None:
    """A search hit: its own name (place, street or address), what it is and where."""
    p = feature.get("properties", {})
    address = _address(p)
    name = p.get("name") or address
    if not name:
        return None
    lon, lat = feature["geometry"]["coordinates"][:2]
    detail = [address] if p.get("name") and address and address != name else []
    detail += [a for a in _area(p) if a != name]
    return {"name": name, "kind": _kind(p), "detail": ", ".join(detail), "lat": round(lat, 6), "lon": round(lon, 6)}


def describe_point(feature: dict) -> dict | None:
    """A clicked point is named by its address: the nearest object may be a bar or a monument."""
    p = feature.get("properties", {})
    name = _address(p) or p.get("name")
    if not name:
        return None
    lon, lat = feature["geometry"]["coordinates"][:2]
    return {"name": name, "detail": ", ".join(a for a in _area(p) if a != name), "lat": round(lat, 6), "lon": round(lon, 6)}


class PlaceSearch:
    def __init__(self, base_url: str = PHOTON_URL, get: Callable[..., httpx.Response] = httpx.get) -> None:
        self.base_url = base_url.rstrip("/")
        self._get = get
        self._cache: TTLCache = TTLCache(maxsize=1024, ttl=CACHE_TTL_S)
        self._lock = threading.Lock()

    def search(self, q: str, near: tuple[float, float] | None = None) -> dict:
        q = " ".join(q.split())
        params = {"q": q, "limit": MAX_RESULTS + 4,
                  "bbox": f"{LON_RANGE[0]},{LAT_RANGE[0]},{LON_RANGE[1]},{LAT_RANGE[1]}"}
        if near and _inside(*near):  # prefer hits near the map centre
            params.update(lat=round(near[0], 3), lon=round(near[1], 3))
        features = self._fetch("/api/", params, key=("search", q.lower(), params.get("lat"), params.get("lon")))
        if features is None:
            return {"results": [], "available": False}
        results, seen = [], set()
        for f in features:
            hit = describe(f)
            key = hit and (hit["name"], hit["detail"])   # "Rynek Główny" is a square and two streets
            if hit and _inside(hit["lat"], hit["lon"]) and key not in seen:
                seen.add(key)
                results.append(hit)
        return {"results": results[:MAX_RESULTS], "available": True}

    def reverse(self, lat: float, lon: float) -> dict:
        params = {"lat": round(lat, 5), "lon": round(lon, 5), "limit": 1}
        features = self._fetch("/reverse", params, key=("reverse", round(lat, 4), round(lon, 4)))
        if features is None:
            return {"place": None, "available": False}
        place = next((p for p in map(describe_point, features) if p), None)
        return {"place": place, "available": True}

    def _fetch(self, path: str, params: dict, key: tuple) -> list | None:
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        try:
            r = self._get(self.base_url + path, params=params, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            features = r.json().get("features", [])
        except (httpx.HTTPError, ValueError, AttributeError):
            log.warning("place search unavailable (%s)", path, exc_info=True)
            return None  # not cached: the next keystroke tries again
        with self._lock:
            self._cache[key] = features
        return features
