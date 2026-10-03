"""Validation of HTTP input (pydantic). Engine receives only validated objects."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from .profiles import DEFAULT_PROFILE, PROFILES

TZ = ZoneInfo("Europe/Warsaw")
# Coarse service area; the exact 300 m check against the network is done by the graph (422).
LAT_RANGE = (49.95, 50.15)
LON_RANGE = (19.75, 20.25)
MAX_POINTS = 5


def to_local(dt: datetime | None) -> datetime | None:
    """Naive times are Kraków local time; aware times are converted to it."""
    if dt is None:
        return None
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


class Point(BaseModel):
    lat: float = Field(ge=LAT_RANGE[0], le=LAT_RANGE[1])
    lon: float = Field(ge=LON_RANGE[0], le=LON_RANGE[1])


class RouteRequest(BaseModel):
    points: list[Point] = Field(min_length=2, max_length=MAX_POINTS)
    scenario: str = "live"
    depart_at: datetime | None = None
    profile: str = DEFAULT_PROFILE
    optimize_order: bool = False

    @field_validator("depart_at")
    @classmethod
    def _local_time(cls, v: datetime | None) -> datetime | None:
        return to_local(v)

    @field_validator("profile")
    @classmethod
    def _known_profile(cls, v: str) -> str:
        if v not in PROFILES:
            raise ValueError(f"unknown profile, expected one of {sorted(PROFILES)}")
        return v


class ConditionsQuery(BaseModel):
    scenario: str = "live"
    at: datetime | None = None

    @field_validator("at")
    @classmethod
    def _local_time(cls, v: datetime | None) -> datetime | None:
        return to_local(v)
