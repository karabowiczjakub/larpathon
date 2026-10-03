"""Engine: orchestrates environment -> shade/exposure -> routing -> response. No module internals here."""
from __future__ import annotations

import logging
import time
from datetime import datetime

import numpy as np

from ..contracts import PointOutsideArea, Route
from ..profiles import PROFILES, RiderProfile
from ..providers import Modules
from ..schemas import LayerQuery, RouteRequest, to_local
from . import explain, layers, metrics, ordering
from .costs import EdgeCostBuilder, EdgeCosts
from .variants import DEFAULT_VARIANTS, RouteVariant

log = logging.getLogger(__name__)
WARMUP_POINTS = ({"lat": 50.0614, "lon": 19.9366}, {"lat": 50.0540, "lon": 19.9350})


class UnknownScenario(ValueError):
    pass


class _Timer:
    def __init__(self) -> None:
        self.start = self._last = time.perf_counter()
        self.ms: dict[str, float] = {}

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.ms[name] = round((now - self._last) * 1000, 1)
        self._last = now

    def done(self) -> dict[str, float]:
        self.ms["total"] = round((time.perf_counter() - self.start) * 1000, 1)
        return self.ms


class Engine:
    def __init__(
        self,
        modules: Modules,
        variants: tuple[RouteVariant, ...] = DEFAULT_VARIANTS,
        profiles: dict[str, RiderProfile] = PROFILES,
        cache_size: int = 32,
    ):
        if len(variants) < 2:
            raise ValueError("Engine needs at least two route variants to compare")
        self.modules = modules
        self.graph, self.env, self.shade = modules.graph, modules.env, modules.shade
        self.variants = variants
        self.profiles = profiles
        self.costs = EdgeCostBuilder(modules.graph, modules.shade, modules.exposure, cache_size)

    # ---------- queries ----------
    def scenarios(self) -> list[dict]:
        return self.env.scenarios()

    def conditions(self, scenario: str, at: datetime | None) -> dict:
        self._check_scenario(scenario)
        ctx = self.env.get(scenario, at)
        return {**ctx.summary(), "sun": self._sun(_sun_time(scenario, at, ctx))}

    def shade_layer(self, q: LayerQuery) -> dict:
        """Shade and discomfort of the edges in a bbox, for a map overlay (roles/04 §4.4 stretch)."""
        self._check_scenario(q.scenario)
        ctx = self.env.get(q.scenario, q.at)
        at = _sun_time(q.scenario, q.at, ctx)
        costs = self.costs.build(ctx, at, self.profiles[q.profile])
        eids, truncated = layers.edges_in_bbox(self.graph.edge_mid_lonlat, self.graph.edge_length_m, q.bbox)
        return {**layers.feature_collection(self.graph, eids, costs), "truncated": truncated, "at": at.isoformat()}

    def health(self) -> dict:
        status = self.modules.status
        return {
            "ok": True,
            "mocks": any(s != "real" for s in status.values()),
            "modules": status,
            "errors": self.modules.errors,
            "edges": int(self.graph.n_edges),
            **self._live_status(),
        }

    # ---------- main flow ----------
    def route(self, req: RouteRequest) -> dict:
        timer = _Timer()
        self._check_scenario(req.scenario)
        profile = self.profiles[req.profile]
        ctx = self.env.get(req.scenario, req.depart_at)
        at = _sun_time(req.scenario, req.depart_at, ctx)
        timer.lap("env")

        costs = self.costs.build(ctx, at, profile)
        timer.ms.update(costs.timing_ms)
        timer.lap("costs")

        points = [(p.lat, p.lon) for p in req.points]
        order = self._order(points, costs, profile) if req.optimize_order else list(range(len(points)))
        points = [points[i] for i in order]
        try:
            found = [(v, self.graph.route(points, v.cost(costs, profile))) for v in self.variants]
        except PointOutsideArea as e:
            if e.index is not None and 0 <= e.index < len(order):
                e.index = order[e.index]  # report the point as the client numbered it
            raise
        timer.lap("routing")

        reference = found[0][1]
        routes = [
            self._describe(v, r, costs, profile, None if i == 0 else reference, points)
            for i, (v, r) in enumerate(found)
        ]
        same = np.array_equal(found[0][1].eids, found[1][1].eids)
        result = {
            "routes": routes,
            "comparison": metrics.compare(routes[0]["metrics"], routes[1]["metrics"], same),
            "order": order,
            "conditions": ctx.summary(),
            "sun": self._sun(at),
        }
        timer.lap("describe")
        result["timing_ms"] = timer.done()
        return result

    def warmup(self) -> None:
        t0 = time.perf_counter()
        try:
            self.route(RouteRequest(points=list(WARMUP_POINTS)))
            log.info("warmup ok in %.0f ms", (time.perf_counter() - t0) * 1000)
        except Exception:
            log.exception("warmup failed (the API still starts)")

    # ---------- helpers ----------
    def _check_scenario(self, scenario: str) -> None:
        known = {s["id"] for s in self.env.scenarios()}
        if scenario not in known:
            raise UnknownScenario(f"unknown scenario {scenario!r}, expected one of {sorted(known)}")

    def _order(self, points: list[tuple[float, float]], costs: EdgeCosts, profile: RiderProfile) -> list[int]:
        if len(points) <= 3:
            return list(range(len(points)))
        cost_matrix = getattr(self.graph, "cost_matrix", None)
        matrix = (
            cost_matrix(points, self.variants[0].cost(costs, profile))
            if callable(cost_matrix)
            else ordering.straight_line_matrix(points)
        )
        return ordering.best_order(np.asarray(matrix))

    def _describe(
        self,
        variant: RouteVariant,
        route: Route,
        costs: EdgeCosts,
        profile: RiderProfile,
        reference: Route | None,
        points: list[tuple[float, float]],
    ) -> dict:
        eids = np.asarray(route.eids, dtype=np.int64)
        exp = costs.exposure
        if len(eids):
            coords = self.graph.geometry(eids)
            segs = explain.segments(
                self.graph.coord_counts(eids), exp.discomfort[eids], exp.reason[eids], costs.time_s[eids]
            )
        else:  # all points snapped to the same node
            lat, lon = points[0]
            coords, segs = [[lon, lat], [lon, lat]], []
        avoided = (
            explain.avoids(
                np.asarray(reference.eids, dtype=np.int64), eids, exp.discomfort, exp.reason,
                self.graph.edge_name, self.graph.edge_length_m,
            )
            if reference is not None
            else []
        )
        return {
            "id": variant.id,
            "label": variant.label,
            "color": variant.color,
            "geometry": {"type": "LineString", "coordinates": coords},
            "metrics": metrics.route_metrics(eids, costs, profile, self.graph.edge_length_m),
            "segments": segs,
            "avoids": avoided,
        }

    def _sun(self, at: datetime) -> dict:
        s = self.shade.sun(at)
        return {"azimuth_deg": round(float(s.azimuth_deg), 1), "elevation_deg": round(float(s.elevation_deg), 1)}

    def _live_status(self) -> dict:
        """Age of live data; None unless the live feed is actually fresh (else Env serves a fallback)."""
        try:
            ctx = self.env.get("live", None)
        except Exception:
            log.warning("live environment unavailable for /health", exc_info=True)
            return {"live_source": None, "live_data_age_s": None}
        age = round(float(ctx.data_age_s), 1) if ctx.source in {"live", "mock"} else None
        return {"live_source": ctx.source, "live_data_age_s": age}


def _sun_time(scenario: str, at: datetime | None, ctx) -> datetime:
    """Moment for sun and shade. A scenario is one recorded day: keep the requested clock time, take the
    date from the conditions (Env does the same), so shade never mixes a July scenario with October sun."""
    day = to_local(ctx.timestamp)
    if at is None:
        return day
    if scenario == "live":
        return at
    return at.replace(year=day.year, month=day.month, day=day.day)
