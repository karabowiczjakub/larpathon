import dataclasses

import pytest

from app import create_app, mocks
from app.providers import MODULE_NAMES, Modules

RYNEK = {"lat": 50.0614, "lon": 19.9366}
BLONIA = {"lat": 50.0675, "lon": 19.8728}
KAZIMIERZ = {"lat": 50.0510, "lon": 19.9450}


@pytest.fixture(scope="session")
def mock_graph():
    return mocks.MockGraph()


@pytest.fixture(scope="session")
def mock_modules(mock_graph):
    return Modules(
        graph=mock_graph,
        shade=mocks.MockShade(mock_graph),
        env=mocks.MockEnv(),
        exposure=mocks.mock_exposure,
        status=dict.fromkeys(MODULE_NAMES, "mock"),
    )


@pytest.fixture
def make_client(mock_modules):
    """make_client(graph=..., exposure=...) swaps single modules for fakes."""

    def make(**swap):
        modules = dataclasses.replace(mock_modules, **swap)
        return create_app({"WARMUP": False}, modules=modules).test_client()

    return make


@pytest.fixture
def client(make_client):
    return make_client()
