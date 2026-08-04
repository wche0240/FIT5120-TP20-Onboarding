from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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
