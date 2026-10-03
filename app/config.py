"""Configuration from environment variables (see .env.example); create_app() overrides win."""
from __future__ import annotations

import os


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _set(name: str) -> set[str]:
    return {x.strip() for x in os.getenv(name, "").split(",") if x.strip()}


def from_env() -> dict:
    return {
        "DATA_DIR": os.getenv("DATA_DIR", "data/processed"),
        "SCENARIO_DIR": os.getenv("SCENARIO_DIR", "scenarios"),
        "USE_MOCKS": _flag("USE_MOCKS"),
        "MOCK_MODULES": _set("MOCK_MODULES"),  # e.g. "shade,env"
        "STRICT_MODULES": _flag("STRICT_MODULES"),  # 1 = fail instead of falling back to mocks
        "WARMUP": _flag("WARMUP", "1"),
        "COST_CACHE_SIZE": int(os.getenv("COST_CACHE_SIZE", "32")),
        "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
        # Real implementations (roles 1-3); see app/providers.py for the call signatures.
        "GRAPH_FACTORY": os.getenv("GRAPH_FACTORY", "app.graph.routing:RoutingGraph.load"),
        "SHADE_FACTORY": os.getenv("SHADE_FACTORY", "app.shade.model:ShadeModel.load"),
        "ENV_FACTORY": os.getenv("ENV_FACTORY", "app.env.service:EnvironmentService"),
        "EXPOSURE_FN": os.getenv("EXPOSURE_FN", "app.env.exposure:compute_edge_exposure"),
    }
