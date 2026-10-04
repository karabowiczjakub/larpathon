"""Engine: orchestrates environment -> shade/exposure -> routing -> response. No module internals here."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime

import numpy as np

from ..contracts import EdgeExposure, EnvironmentalContext, PointOutsideArea, Route
from ..profiles import PROFILES, RiderProfile
from ..providers import Modules
from ..schemas import FACTORS, LayerQuery, RouteRequest, to_local
from . import explain, layers, metrics, ordering
from .costs import EdgeCostBuilder, EdgeCosts
from .variants import DEFAULT_VARIANTS, RouteVariant

log = logging.getLogger(__name__)
WARMUP_POINTS = ({"lat": 50.0614, "lon": 19.9366}, {"lat": 50.0540, "lon": 19.9350})
# A factor switched off in "advanced options" is fed to the fuzzy model as neutral: (exposure field, value)
NEUTRAL_INPUTS = {"heat": ("utci_c", 15.0), "air": ("air_index", 0.0), "uv": ("uv_eff", 0.0)}
# Trade-off slider: the profile's ECO weights times these, from barely slower to most comfortable
TRADEOFF_WEIGHTS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
TRADEOFF_MAX_EXTRA = 0.30   # longer detours buy too little (roles/04 §7: over +50% is absurd)
# Smallest gain worth one more step on the slider: 0.05 on the 0-10 discomfort scale, 2% of the dose
TRADEOFF_MIN_GAIN = {"discomfort": 0.005, "pm25_dose": 0.02}


@dataclass
class _Plan:
    """Everything a routing request needs before Dijkstra (shared by route and tradeoff)."""

    profile: RiderProfile
    ctx: EnvironmentalContext
    at: datetime
    costs: EdgeCosts            # full model: metrics, segments
    points: list[tuple[float, float]]
    order: list[int]
    factors: set[str]
    route_costs: EdgeCosts      # the chosen factors only: what the routes are picked on
    route_profile: RiderProfile


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
        plan = self._plan(req, timer)
        found = [(v, self._find(plan, v.cost(plan.route_costs, plan.route_profile))) for v in self.variants]
        timer.lap("routing")

        reference = found[0][1]
        routes = [
            self._describe(v, r, plan.costs, plan.profile, None if i == 0 else reference, plan.points,
                           plan.route_costs.exposure)
            for i, (v, r) in enumerate(found)
        ]
        same = np.array_equal(found[0][1].eids, found[1][1].eids)
        result = {
            "routes": routes,
            "comparison": metrics.compare(routes[0]["metrics"], routes[1]["metrics"], same),
            "order": plan.order,
            "factors": [f for f in FACTORS if f in plan.factors],
            "conditions": plan.ctx.summary(),
            "sun": self._sun(plan.at),
        }
        timer.lap("describe")
        result["timing_ms"] = timer.done()
        return result

    def tradeoff(self, req: RouteRequest) -> dict:
        """More comfortable routes for a range of ECO weights (Pareto front of time vs discomfort),
        so the rider picks how much extra time comfort is worth. Weight 1 is /api/route's route."""
        timer = _Timer()
        plan = self._plan(req, timer)
        fast_variant, eco_variant = self.variants[0], self.variants[1]
        fastest = self._find(plan, fast_variant.cost(plan.route_costs, plan.route_profile))
        seen = {np.asarray(fastest.eids).tobytes()}
        found, on_map = [], None
        for w in TRADEOFF_WEIGHTS:
            weighted = replace(plan.route_profile, eco_alpha=plan.route_profile.eco_alpha * w,
                               eco_air_weight=plan.route_profile.eco_air_weight * w)
            r = self._find(plan, eco_variant.cost(plan.route_costs, weighted))
            key = np.asarray(r.eids).tobytes()
            if w == 1.0:
                on_map = key  # what /api/route shows as "More comfortable"
            if key not in seen:
                seen.add(key)
                found.append((w, r, key))
        timer.lap("routing")

        # Asthma (and "air only") routes are chosen for cleaner air: rank them by the dose, the rest by discomfort
        axis = "pm25_dose" if plan.route_profile.eco_air_weight > 0 or plan.factors == {"air"} else "discomfort"
        fast_score = self._score(plan, fastest, axis)
        min_gain = TRADEOFF_MIN_GAIN[axis] * (fast_score[1] if axis == "pm25_dose" else 1.0)
        kept = _pareto(fast_score, [(w, r, self._score(plan, r, axis), key == on_map) for w, r, key in found], min_gain)
        reference = self._describe(fast_variant, fastest, plan.costs, plan.profile, None, plan.points,
                                   plan.route_costs.exposure)
        options, default = [], None
        for w, r, (_, score), shown in kept:
            route = self._describe(eco_variant, r, plan.costs, plan.profile, fastest, plan.points,
                                   plan.route_costs.exposure)
            if shown:
                default = len(options)
            options.append({"weight": w, "value": _axis_value(axis, score), "route": route,
                            "comparison": metrics.compare(reference["metrics"], route["metrics"], False)})
        timer.lap("describe")
        return {
            "axis": axis,
            "fastest": {**reference["metrics"], "value": _axis_value(axis, fast_score[1])},
            "options": options,
            "default_index": default,  # None: /api/route found no detour, the map shows the fastest route
            "timing_ms": timer.done(),
        }

    def warmup(self) -> None:
        t0 = time.perf_counter()
        try:
            self.route(RouteRequest(points=list(WARMUP_POINTS)))
            log.info("warmup ok in %.0f ms", (time.perf_counter() - t0) * 1000)
        except Exception:
            log.exception("warmup failed (the API still starts)")

    # ---------- helpers ----------
    def _plan(self, req: RouteRequest, timer: _Timer) -> _Plan:
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
        factors = set(req.factors)
        route_costs, route_profile = costs, profile
        if factors != set(FACTORS):
            route_costs = self._focus(costs, profile, factors)
            if "air" not in factors:
                route_profile = replace(profile, eco_air_weight=0.0)
        return _Plan(profile, ctx, at, costs, [points[i] for i in order], order, factors, route_costs, route_profile)

    @staticmethod
    def _score(plan: _Plan, route: Route, axis: str) -> tuple[float, float]:
        """(travel time [s], what the slider trades time for), unrounded so the front is exact. Discomfort is
        the one the route was chosen on (selected factors only), the dose is the real one."""
        e = np.asarray(route.eids, dtype=np.int64)
        t = plan.costs.time_s[e]
        total = float(t.sum())
        if axis == "pm25_dose":
            return total, float((np.asarray(plan.costs.exposure.pm25)[e] * t).sum() * plan.profile.ventilation_m3h / 3600)
        return total, float((t * np.asarray(plan.route_costs.exposure.discomfort)[e]).sum() / total) if total else 0.0

    def _find(self, plan: _Plan, edge_cost: np.ndarray) -> Route:
        try:
            return self.graph.route(plan.points, edge_cost)
        except PointOutsideArea as e:
            if e.index is not None and 0 <= e.index < len(plan.order):
                e.index = plan.order[e.index]  # report the point as the client numbered it
            raise

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

    def _focus(self, costs: EdgeCosts, profile: RiderProfile, factors: set[str]) -> EdgeCosts:
        """Costs for routing on the chosen factors only: the others are set neutral (comfortable 15 °C,
        clean air, no UV) and Role 2's fuzzy model is evaluated again. Metrics keep the full model."""
        from ..mocks import mock_discomfort

        exp = costs.exposure
        n = self.graph.n_edges
        inputs = {
            attr: np.asarray(getattr(exp, attr), dtype=np.float64) if name in factors else np.full(n, neutral)
            for name, (attr, neutral) in NEUTRAL_INPUTS.items()
        }
        discomfort_fn = self.modules.discomfort or mock_discomfort
        d = discomfort_fn(profile.id, inputs["utci_c"], inputs["air_index"], inputs["uv_eff"])
        d = np.clip(np.nan_to_num(np.asarray(d, dtype=np.float64)), 0.0, 1.0)
        reason = explain.dominant_reason(inputs["utci_c"], inputs["air_index"], inputs["uv_eff"])  # chosen ones
        return replace(costs, exposure=replace(exp, discomfort=d, air_index=inputs["air_index"], reason=reason))

    def _describe(
        self,
        variant: RouteVariant,
        route: Route,
        costs: EdgeCosts,
        profile: RiderProfile,
        reference: Route | None,
        points: list[tuple[float, float]],
        routed: EdgeExposure,
    ) -> dict:
        """Segments and metrics use the full model; "avoids" uses what the route was chosen on (factors)."""
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
                np.asarray(reference.eids, dtype=np.int64), eids, routed.discomfort, routed.reason,
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


def _pareto(fastest: tuple[float, float], found: list[tuple], min_gain: float) -> list[tuple]:
    """Routes that buy comfort with time, quickest first; items are (weight, route, (time_s, score), on_map).
    Each slower one must beat every quicker one (and the fastest) by min_gain and be at most
    TRADEOFF_MAX_EXTRA longer. The route already on the map always stays, so the slider starts there."""
    fast_time, best = fastest
    keep = []
    for w, r, (t, score), on_map in sorted(found, key=lambda x: x[2]):
        if on_map or (score <= best - min_gain and t <= fast_time * (1 + TRADEOFF_MAX_EXTRA)):
            keep.append((w, r, (t, score), on_map))
            best = min(best, score)
    return keep


def _axis_value(axis: str, value: float) -> float:
    return round(value * 10, 2) if axis == "discomfort" else round(value, 2)  # 0-10 scale / µg


def _sun_time(scenario: str, at: datetime | None, ctx) -> datetime:
    """Moment for sun and shade. A scenario is one recorded day: keep the requested clock time, take the
    date from the conditions (Env does the same), so shade never mixes a July scenario with October sun."""
    day = to_local(ctx.timestamp)
    if at is None:
        return day
    if scenario == "live":
        return at
    return at.replace(year=day.year, month=day.month, day=day.day)
