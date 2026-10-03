import subprocess
import sys
from pathlib import Path

import pytest

from app import config
from app.contract_checks import ContractError
from app.mocks import MockEnv, MockGraph, mock_exposure
from app.providers import build_modules, resolve


def cfg(**kw):
    return {**config.from_env(), "USE_MOCKS": False, "MOCK_MODULES": set(), "STRICT_MODULES": False, **kw}


def test_resolve_dotted_paths():
    assert resolve("app.mocks.graph:MockGraph") is MockGraph
    assert resolve("app.mocks:MockEnv.scenarios") is MockEnv.scenarios
    with pytest.raises(ModuleNotFoundError):
        resolve("app.nope:X")


def test_use_mocks_builds_everything_as_mock():
    m = build_modules(cfg(USE_MOCKS=True))
    assert m.status == {"graph": "mock", "shade": "mock", "env": "mock", "exposure": "mock"}
    assert m.exposure is mock_exposure and m.errors == {}


def test_real_module_used_and_others_mocked():
    m = build_modules(cfg(GRAPH_FACTORY="fake_modules:load_graph", MOCK_MODULES={"shade", "env", "exposure"}))
    assert m.status["graph"] == "real" and m.status["shade"] == "mock"
    assert m.shade.edge_tree_frac.shape == (m.graph.n_edges,)


def test_missing_real_modules_fall_back_to_mocks_with_reason():
    m = build_modules(cfg(
        GRAPH_FACTORY="fake_modules:load_graph",
        SHADE_FACTORY="fake_modules:load_shade_for_other_graph",
        ENV_FACTORY="fake_modules:missing_env",
        EXPOSURE_FN="app.env.not_written_yet:compute_edge_exposure",
    ))
    assert m.status == {"graph": "real", "shade": "mock (fallback)", "env": "mock (fallback)",
                        "exposure": "mock (fallback)"}
    assert "ContractError" in m.errors["shade"] and "edge_tree_frac" in m.errors["shade"]
    assert "FileNotFoundError" in m.errors["env"]
    assert "ModuleNotFoundError" in m.errors["exposure"]
    assert m.shade.edge_tree_frac.shape == (m.graph.n_edges,)


def test_strict_mode_raises_instead_of_fallback():
    with pytest.raises(ContractError):
        build_modules(cfg(
            STRICT_MODULES=True,
            GRAPH_FACTORY="fake_modules:load_graph",
            SHADE_FACTORY="fake_modules:load_shade_for_other_graph",
            MOCK_MODULES={"env", "exposure"},
        ))


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("USE_MOCKS", "true")
    monkeypatch.setenv("MOCK_MODULES", " shade, env ,")
    c = config.from_env()
    assert c["USE_MOCKS"] is True and c["MOCK_MODULES"] == {"shade", "env"}


def test_importing_contracts_stays_lightweight():
    """Roles 1-3 import app.contracts; that must not pull in Flask or pydantic."""
    code = "import sys, app.contracts; assert not {'flask', 'pydantic'} & set(sys.modules), sorted(sys.modules)"
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).parents[1])
