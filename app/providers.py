"""Factory for the four role modules: real implementation or mock, chosen per module from config.

Real implementations are referenced by "module:attr" paths in config, so a role can move its code
without touching Backend. If a real module fails to load, its mock is used (unless STRICT_MODULES).
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .contract_checks import check_env, check_exposure_fn, check_graph, check_shade
from .contracts import EnvironmentServiceP, ExposureFn, RoutingGraphP, ShadeModelP

log = logging.getLogger(__name__)
MODULE_NAMES = ("graph", "shade", "env", "exposure")


@dataclass
class Modules:
    graph: RoutingGraphP
    shade: ShadeModelP
    env: EnvironmentServiceP
    exposure: ExposureFn
    status: dict[str, str] = field(default_factory=dict)  # name -> "real" | "mock" | "mock (fallback)"
    errors: dict[str, str] = field(default_factory=dict)  # name -> why the real module was not used


def resolve(path: str) -> Any:
    """'package.module:Attr.attr' -> object."""
    module_name, _, attr_path = path.partition(":")
    obj: Any = importlib.import_module(module_name)
    for attr in filter(None, attr_path.split(".")):
        obj = getattr(obj, attr)
    return obj


def _wants_mock(cfg: Mapping, name: str) -> bool:
    return bool(cfg["USE_MOCKS"]) or name in cfg["MOCK_MODULES"]


def _load(cfg: Mapping, name: str, real: Callable[[], Any], mock: Callable[[], Any], check: Callable[[Any], None],
          out: Modules) -> Any:
    if _wants_mock(cfg, name):
        obj = mock()
        check(obj)
        out.status[name] = "mock"
        return obj
    try:
        obj = real()
        check(obj)
        out.status[name] = "real"
        return obj
    except Exception as e:
        if cfg["STRICT_MODULES"]:
            raise
        if isinstance(e, (ModuleNotFoundError, FileNotFoundError)):  # code or artefacts not delivered yet
            log.warning("real %s module not available (%s), using mock", name, e)
        else:
            log.exception("real %s module failed to load, using mock", name)
        obj = mock()
        check(obj)
        out.status[name] = "mock (fallback)"
        out.errors[name] = f"{type(e).__name__}: {e}"
        return obj


def build_modules(cfg: Mapping) -> Modules:
    from . import mocks

    data_dir, scenario_dir = cfg["DATA_DIR"], cfg["SCENARIO_DIR"]
    out = Modules(graph=None, shade=None, env=None, exposure=None)  # type: ignore[arg-type]

    out.graph = _load(
        cfg, "graph",
        real=lambda: resolve(cfg["GRAPH_FACTORY"])(data_dir),
        mock=mocks.MockGraph,
        check=check_graph, out=out,
    )
    n = int(out.graph.n_edges)
    out.shade = _load(
        cfg, "shade",
        real=lambda: resolve(cfg["SHADE_FACTORY"])(data_dir, n_edges=n),
        mock=lambda: mocks.MockShade(out.graph),
        check=lambda s: check_shade(s, n), out=out,
    )
    out.env = _load(
        cfg, "env",
        real=lambda: resolve(cfg["ENV_FACTORY"])(scenario_dir, data_dir),
        mock=mocks.MockEnv,
        check=check_env, out=out,
    )
    out.exposure = _load(
        cfg, "exposure",
        real=lambda: resolve(cfg["EXPOSURE_FN"]),
        mock=lambda: mocks.mock_exposure,
        check=check_exposure_fn, out=out,
    )
    log.info("modules: %s", out.status)
    return out
