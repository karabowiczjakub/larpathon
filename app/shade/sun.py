"""Solar position for Kraków; pvlib azimuth is clockwise from north."""

import math
from datetime import datetime, timezone

import pandas as pd
from pvlib.solarposition import get_solarposition

from app.contracts import SunPosition

LAT, LON = 50.06, 19.94


def utc_time(at: datetime) -> datetime:
    if not isinstance(at, datetime) or pd.isna(at) or at.utcoffset() is None:
        raise ValueError("at must be a timezone-aware datetime")
    return at.astimezone(timezone.utc)


def sun_position(at: datetime) -> SunPosition:
    position = get_solarposition(
        pd.DatetimeIndex([utc_time(at)]), LAT, LON, method="nrel_numpy"
    ).iloc[0]
    azimuth = float(position["azimuth"])
    elevation = float(position["apparent_elevation"])
    if not math.isfinite(azimuth) or not math.isfinite(elevation):
        raise ValueError("pvlib returned a non-finite solar position")
    return SunPosition(azimuth, elevation)
