from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["connected"]


class DataStatusResponse(BaseModel):
    status: Literal["available", "stale", "unavailable"]
    latest_data_at: datetime | None
    age_minutes: int | None
    stale_after_minutes: int
    message: str


class SensorResponse(BaseModel):
    location_id: int
    sensor_name: str
    latitude: float
    longitude: float
    status: str | None
    last_seen_at: datetime | None
    total_count: int | None
    crowd_level: Literal["low", "medium", "high"] | None


class GeoPoint(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class RouteScoreRequest(BaseModel):
    coordinates: list[GeoPoint] = Field(min_length=2, max_length=2_000)


class RouteScoreResponse(BaseModel):
    status: Literal["available", "stale", "unavailable"]
    crowd_level: Literal["low", "medium", "high"] | None
    crowd_score: int | None
    matched_sensor_count: int
    latest_data_at: datetime | None
    warning: str | None


CrowdLevel = Literal["low", "medium", "high"]
TransitMode = Literal["bus", "tram", "train", "coach"]


class TransitAccessPointResponse(BaseModel):
    access_point_id: str
    name: str
    mode: TransitMode
    source_mode: str
    latitude: float
    longitude: float
    distance_metres: float | None


class RoutesRequest(BaseModel):
    start: GeoPoint
    destination: GeoPoint
    max_crowd_level: CrowdLevel = "medium"


class RouteOption(BaseModel):
    route_id: int
    distance_metres: float
    duration_seconds: float
    coordinates: list[GeoPoint]
    data_status: Literal["available", "stale", "unavailable"]
    crowd_level: CrowdLevel | None
    crowd_score: int | None
    matched_sensor_count: int
    latest_data_at: datetime | None
    meets_crowd_threshold: bool | None
    recommended: bool
    warning: str | None


class RoutesResponse(BaseModel):
    status: Literal["available", "degraded"]
    requested_max_crowd_level: CrowdLevel
    recommended_route_id: int | None
    routes: list[RouteOption]
    warning: str | None
