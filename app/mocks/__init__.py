"""Stand-ins for roles 1-3 (USE_MOCKS=1 or MOCK_MODULES=graph,shade,env,exposure)."""
from .env import MockEnv
from .exposure import mock_discomfort, mock_exposure
from .graph import MockGraph
from .shade import MockShade

__all__ = ["MockEnv", "MockGraph", "MockShade", "mock_discomfort", "mock_exposure"]
