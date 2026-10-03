"""Explicit fallback for integration before shade artifacts are available."""

from datetime import datetime

import numpy as np

from app.contracts import SunPosition
from app.shade.sun import sun_position


class MockShade:
    def __init__(self, n_edges: int, tree_frac: np.ndarray | None = None):
        if n_edges < 0:
            raise ValueError("n_edges must be non-negative")
        values = (
            np.full(n_edges, 0.3, np.float32)
            if tree_frac is None
            else np.array(tree_frac, dtype=np.float32, copy=True)
        )
        if (
            values.shape != (n_edges,)
            or not np.isfinite(values).all()
            or np.any((values < 0) | (values > 1))
        ):
            raise ValueError("Expected tree fractions (E,) in [0, 1]")
        values.setflags(write=False)
        self.edge_tree_frac = values

    def sun(self, at: datetime) -> SunPosition:
        return sun_position(at)

    def edge_shade(self, at: datetime) -> np.ndarray:
        if self.sun(at).elevation_deg <= 0:
            return np.ones(len(self.edge_tree_frac), dtype=np.float32)
        return self.edge_tree_frac
