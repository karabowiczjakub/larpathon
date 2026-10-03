"""Per-edge inputs for routing: travel time, shade and exposure (cached per conditions/time/profile)."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, fields, replace
from datetime import datetime

import numpy as np
from cachetools import LRUCache

from ..contract_checks import check_edge_exposure, check_edge_shade
from ..contracts import EdgeExposure, EnvironmentalContext
from ..profiles import RiderProfile

log = logging.getLogger(__name__)
TIME_BUCKET_MIN = 30
_VOLATILE_CTX_FIELDS = {"stations", "data_age_s"}  # do not change edge exposure


@dataclass(frozen=True)
class EdgeCosts:
    time_s: np.ndarray  # (E,) travel time at the profile speed
    shade: np.ndarray  # (E,) 0..1
    exposure: EdgeExposure
    timing_ms: dict  # {"shade": ..., "exposure": ...}; zeros on a cache hit


def time_bucket(at: datetime) -> str:
    minute = (at.minute // TIME_BUCKET_MIN) * TIME_BUCKET_MIN
    return at.replace(minute=minute, second=0, microsecond=0).isoformat()


def context_key(ctx: EnvironmentalContext) -> tuple:
    return tuple(getattr(ctx, f.name) for f in fields(ctx) if f.name not in _VOLATILE_CTX_FIELDS)


def _clean(arr, name: str, lo: float = 0.0, hi: float = 1.0) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float64)
    bad = ~np.isfinite(arr)
    if bad.any():
        log.warning("%s: %d non-finite values replaced", name, int(bad.sum()))
    out = np.clip(np.nan_to_num(arr, nan=lo, posinf=hi, neginf=lo), lo, hi)
    out.flags.writeable = False
    return out


class EdgeCostBuilder:
    def __init__(self, graph, shade_model, exposure_fn, cache_size: int = 32):
        self._graph = graph
        self._shade = shade_model
        self._exposure = exposure_fn
        self._cache: LRUCache = LRUCache(maxsize=cache_size)
        self._lock = threading.Lock()

    def build(self, ctx: EnvironmentalContext, at: datetime, profile: RiderProfile) -> EdgeCosts:
        key = (context_key(ctx), time_bucket(at), profile.id)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return replace(hit, timing_ms={"shade": 0.0, "exposure": 0.0})
        costs = self._compute(ctx, at, profile)
        with self._lock:
            self._cache[key] = costs
        return costs

    def _compute(self, ctx: EnvironmentalContext, at: datetime, profile: RiderProfile) -> EdgeCosts:
        n = self._graph.n_edges
        t0 = time.perf_counter()
        shade = np.asarray(self._shade.edge_shade(at))
        check_edge_shade(shade, n)
        shade = _clean(shade, "shade")
        t1 = time.perf_counter()
        exp = self._exposure(ctx, shade, self._graph, self._shade.edge_tree_frac, profile.id)
        check_edge_exposure(exp, n)
        arrays = {f.name: np.asarray(getattr(exp, f.name)) for f in fields(exp)}
        exp = replace(exp, **{**arrays, "discomfort": _clean(exp.discomfort, "discomfort")})
        t2 = time.perf_counter()
        time_s = np.asarray(self._graph.edge_length_m, dtype=np.float64) / profile.speed_ms
        time_s.flags.writeable = False
        return EdgeCosts(
            time_s=time_s,
            shade=shade,
            exposure=exp,
            timing_ms={"shade": _ms(t1 - t0), "exposure": _ms(t2 - t1)},
        )


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 1)
