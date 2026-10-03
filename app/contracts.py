"""Shade contracts from roles/04_backend_integration.md."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float  # Clockwise from north.
    elevation_deg: float


class ShadeModelP(Protocol):
    edge_tree_frac: np.ndarray

    def sun(self, at: datetime) -> SunPosition: ...

    def edge_shade(self, at: datetime) -> np.ndarray: ...
