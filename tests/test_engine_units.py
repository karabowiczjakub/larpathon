from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.contracts import EdgeExposure, EnvironmentalContext
from app.engine import explain, metrics, ordering
from app.engine.costs import EdgeCostBuilder, EdgeCosts, context_key, time_bucket
from app.engine.variants import ECO, FASTEST
from app.profiles import PROFILES

TZ = ZoneInfo("Europe/Warsaw")
STANDARD = PROFILES["standard"]


def exposure(n, discomfort=None, reason=None, utci=30.0, pm25=10.0, uv=0.0, air=1.0):
    return EdgeExposure(
        utci_c=np.full(n, utci), air_index=np.full(n, air), pm25=np.full(n, pm25), uv_eff=np.full(n, uv),
        discomfort=np.zeros(n) if discomfort is None else np.asarray(discomfort, dtype=float),
        reason=np.full(n, -1, np.int8) if reason is None else np.asarray(reason, np.int8),
    )


def ctx(**kw):
    base = {"timestamp": datetime(2025, 7, 3, 14, tzinfo=TZ), "source": "mock", "temperature_c": 30.0, "humidity_pct": 30,
                "wind_ms": 2.0, "shortwave_wm2": 800, "dni_wm2": 800, "uv_index": 7.0, "pm25": 10.0, "pm10": 20.0, "no2": 15.0}
    return EnvironmentalContext(**{**base, **kw})


# ---------- explain ----------
def test_coord_spans_skip_shared_nodes():
    starts, ends = explain.edge_coord_spans(np.array([2, 3, 2]))
    assert starts.tolist() == [0, 1, 3] and ends.tolist() == [1, 3, 4]


def test_segments_merge_same_reason_with_inclusive_indices():
    segs = explain.segments(
        coord_counts=np.array([2, 3, 2, 2]),
        discomfort=np.array([0.2, 0.4, 0.9, 0.7]),
        reason=np.array([-1, -1, 0, 0]),
        time_s=np.array([10.0, 30.0, 10.0, 10.0]),
    )
    assert segs == [
        {"from": 0, "to": 3, "discomfort": 0.35, "reason": "ok"},
        {"from": 3, "to": 5, "discomfort": 0.8, "reason": "heat"},
    ]
    assert explain.segments(np.array([]), np.array([]), np.array([]), np.array([])) == []


def test_avoids_lists_named_bad_streets_by_length():
    names = np.array(["Main", "Main", "Side", None, "Park"], dtype=object)
    out = explain.avoids(
        reference_eids=np.array([0, 1, 2, 3]), eids=np.array([4]),
        discomfort=np.array([0.9, 0.8, 0.6, 0.9, 0.1]), reason=np.array([0, 1, 1, 0, -1]),
        edge_name=names, edge_length_m=np.array([100.0, 100.0, 50.0, 500.0, 10.0]),
    )
    assert out == ["Main (heat)", "Side (air)"]  # ties in reason: first seen wins
    assert explain.avoids(np.array([0]), np.array([0]), np.ones(1), np.zeros(1), names[:1], np.ones(1)) == []


# ---------- metrics ----------
def test_route_metrics_are_time_weighted():
    n = 4
    costs = EdgeCosts(
        time_s=np.array([60.0, 60.0, 120.0, 1.0]),
        shade=np.array([1.0, 0.0, 0.5, 0.0]),
        exposure=exposure(n, discomfort=[0.5, 0.5, 0.2, 1.0], utci=np.array([35.0, 20.0, 33.0, 40.0]),
                          uv=np.array([2.9, 7.3, 6.0, 9.0]), air=np.array([2.8, 3.9, 3.0, 5.0])),
        timing_ms={},
    )
    m = metrics.route_metrics(np.array([0, 1, 2]), costs, STANDARD, np.array([250.0, 250.0, 500.0, 5.0]))
    assert m["distance_m"] == 1000 and m["time_min"] == 4.0
    assert m["shade_pct"] == 50.0 and m["avg_discomfort"] == 3.5
    assert m["heat_stress_min"] == 3.0
    assert m["uv_high_min"] == 3.0  # sunny edge (7.3) and the one exactly at the WHO "high" threshold (6.0)
    assert m["air_poor_min"] == 3.0  # EAQI 3.9 (arterial NO2) and exactly 3.0; 2.8 is still "moderate"
    assert m["utci_avg_c"] == 30.2  # (35*60 + 20*60 + 33*120) / 240, weighted by riding time
    empty = metrics.route_metrics(np.array([], dtype=int), costs, STANDARD, np.ones(4))
    assert empty["air_poor_min"] == 0 and empty["utci_avg_c"] is None
    assert m["pm25_dose_ug"] == round(10.0 * STANDARD.ventilation_m3h * 240 / 3600, 2)
    assert metrics.route_metrics(np.array([], dtype=int), costs, STANDARD, np.ones(4))["time_min"] == 0


def test_compare_deltas_and_zero_safety():
    f = {"time_min": 10.0, "pm25_dose_ug": 4.0, "shade_pct": 20.0, "heat_stress_min": 5.0, "uv_high_min": 6.0,
         "air_poor_min": 4.0, "utci_avg_c": 38.4}
    e = {"time_min": 12.0, "pm25_dose_ug": 3.0, "shade_pct": 50.0, "heat_stress_min": 1.0, "uv_high_min": 2.5,
         "air_poor_min": 0.5, "utci_avg_c": 35.1}
    c = metrics.compare(f, e, same_route=False)
    assert c == {"same_route": False, "time_delta_min": 2.0, "time_delta_pct": 20.0, "pm25_dose_delta_pct": -25.0,
                 "shade_delta_pp": 30.0, "heat_stress_delta_min": -4.0, "uv_high_delta_min": -3.5,
                 "air_poor_delta_min": -3.5, "utci_delta_c": -3.3}
    assert metrics.compare({**f, "utci_avg_c": None}, e, False)["utci_delta_c"] == 0.0
    zero = dict.fromkeys(f, 0.0)
    assert metrics.compare(zero, zero, True)["time_delta_pct"] == 0.0
    assert metrics.compare({**f, "pm25_dose_ug": None}, e, False)["pm25_dose_delta_pct"] == 0.0


# ---------- variants ----------
def test_eco_cost_formula():
    costs = EdgeCosts(time_s=np.array([10.0, 10.0]), shade=np.zeros(2),
                      exposure=exposure(2, discomfort=[0.0, 1.0]), timing_ms={})
    assert FASTEST.cost(costs, STANDARD).tolist() == [10.0, 10.0]
    assert ECO.cost(costs, STANDARD).tolist() == [10.0, 10.0 * (1 + STANDARD.eco_alpha)]


def test_asthma_eco_cost_weighs_exposure_to_polluted_air():
    """Same discomfort everywhere: only the asthma profile pays for time spent in worse air (NO2 at an arterial)."""
    air = np.array([2.0, 2.0, 2.0, 4.0])
    costs = EdgeCosts(time_s=np.full(4, 10.0), shade=np.zeros(4), exposure=exposure(4, discomfort=[0.5] * 4, air=air),
                      timing_ms={})
    asthma = PROFILES["asthma"]
    cost = ECO.cost(costs, asthma)
    # twice the median air index (+1 exposure) and one EAQI band above the cleaner streets (+1 hotspot)
    assert cost[3] == pytest.approx(cost[0] + 10.0 * asthma.eco_air_weight * 2)
    assert ECO.cost(costs, STANDARD).tolist() == [10.0] * 4                    # other profiles: unchanged
    nan_air = replace(costs, exposure=exposure(4, discomfort=[0.5] * 4, air=np.array([np.nan, 2.0, 2.0, 2.0])))
    assert np.isfinite(ECO.cost(nan_air, asthma)).all()


def test_eco_cost_ignores_the_unavoidable_city_baseline():
    """Smog everywhere (D 0.8) with one arterial (D 0.9): only the arterial's excess costs extra."""
    disc = [0.8] * 9 + [0.9]
    costs = EdgeCosts(time_s=np.full(10, 10.0), shade=np.zeros(10), exposure=exposure(10, discomfort=disc),
                      timing_ms={})
    cost = ECO.cost(costs, STANDARD)
    assert cost[:9].tolist() == [10.0] * 9
    assert cost[9] == pytest.approx(10.0 * (1 + STANDARD.eco_alpha * 0.5))
    uniform = replace(costs, exposure=exposure(10, discomfort=[0.85] * 10))
    assert ECO.cost(uniform, STANDARD).tolist() == FASTEST.cost(uniform, STANDARD).tolist()


# ---------- ordering ----------
def test_best_order_fixed_ends():
    pts = [(50.0, 19.90), (50.0, 19.99), (50.0, 19.93), (50.0, 20.00)]
    order = ordering.best_order(ordering.straight_line_matrix(pts))
    assert order == [0, 2, 1, 3]
    assert ordering.best_order(np.zeros((3, 3))) == [0, 1, 2]


def test_straight_line_matrix_metres():
    d = ordering.straight_line_matrix([(50.0, 19.9), (50.01, 19.9)])
    assert d[0, 0] == 0 and abs(d[0, 1] - 1112) < 5


# ---------- cost builder ----------
class _Graph:
    n_edges = 3
    edge_length_m = np.array([100.0, 200.0, 300.0])


class _Shade:
    edge_tree_frac = np.zeros(3)

    def __init__(self):
        self.calls = 0

    def edge_shade(self, at):
        self.calls += 1
        return np.array([0.5, np.nan, 2.0])


def test_cost_builder_caches_and_sanitizes():
    shade = _Shade()
    seen = []

    def exp_fn(c, s, g, t, profile):
        seen.append(s.copy())
        return exposure(3, discomfort=[np.nan, 0.5, 7.0])

    b = EdgeCostBuilder(_Graph(), shade, exp_fn)
    at = datetime(2025, 7, 3, 14, 5, tzinfo=TZ)
    first = b.build(ctx(), at, STANDARD)
    assert first.shade.tolist() == [0.5, 0.0, 1.0] and seen[0].tolist() == [0.5, 0.0, 1.0]
    assert first.exposure.discomfort.tolist() == [0.0, 0.5, 1.0]
    assert np.allclose(first.time_s, np.array([100, 200, 300]) / STANDARD.speed_ms)
    with pytest.raises(ValueError):
        first.time_s[0] = 1  # cached arrays are read-only

    again = b.build(ctx(data_age_s=99.0), at.replace(minute=25), STANDARD)
    assert shade.calls == 1 and again.timing_ms == {"shade": 0.0, "exposure": 0.0}
    b.build(ctx(), at.replace(minute=35), STANDARD)
    b.build(ctx(temperature_c=31.0), at, STANDARD)
    b.build(ctx(), at, PROFILES["asthma"])
    assert shade.calls == 4


def test_time_bucket_and_context_key():
    at = datetime(2025, 7, 3, 14, 47, 12, tzinfo=TZ)
    assert time_bucket(at) == "2025-07-03T14:30:00+02:00"
    assert context_key(ctx()) == context_key(replace(ctx(), data_age_s=500.0))
    assert context_key(ctx()) != context_key(ctx(pm25=11.0))
