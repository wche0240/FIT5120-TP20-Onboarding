from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_db
from app.schemas import DataStatusResponse, HealthResponse, SensorResponse

app = FastAPI(
    title="SensoryWay API",
    version="0.1.0",
    description="Epic 1 pedestrian-data API for sensory-aware route planning.",
)

allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


def stale_after_minutes() -> int:
    configured_minutes = int(os.getenv("DATA_STALE_AFTER_MINUTES", "30"))
    if configured_minutes <= 0:
        raise RuntimeError("DATA_STALE_AFTER_MINUTES must be positive")
    return configured_minutes


@app.get("/api/v1/health", response_model=HealthResponse)
def health(connection: psycopg.Connection[Any] = Depends(get_db)) -> HealthResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
    return HealthResponse(status="ok", database="connected")


@app.get("/api/v1/data-status", response_model=DataStatusResponse)
def data_status(connection: psycopg.Connection[Any] = Depends(get_db)) -> DataStatusResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT MAX(sensing_datetime) AS latest_data_at FROM pedestrian_minute_count")
        latest_row = cursor.fetchone()

    limit_minutes = stale_after_minutes()
    latest_data_at = latest_row["latest_data_at"] if latest_row else None
    if latest_data_at is None:
        return DataStatusResponse(
            status="unavailable",
            latest_data_at=None,
            age_minutes=None,
            stale_after_minutes=limit_minutes,
            message="Pedestrian data is unavailable.",
        )

    if latest_data_at.tzinfo is None:
        latest_data_at = latest_data_at.replace(tzinfo=timezone.utc)
    age_minutes = max(0, int((datetime.now(timezone.utc) - latest_data_at).total_seconds() // 60))
    status = "available" if age_minutes <= limit_minutes else "stale"
    message = "Pedestrian data is available." if status == "available" else "Pedestrian data is outdated."
    return DataStatusResponse(
        status=status,
        latest_data_at=latest_data_at,
        age_minutes=age_minutes,
        stale_after_minutes=limit_minutes,
        message=message,
    )


@app.get("/api/v1/sensors", response_model=list[SensorResponse])
def sensors(
    limit: int = Query(default=200, ge=1, le=500),
    connection: psycopg.Connection[Any] = Depends(get_db),
) -> list[SensorResponse]:
    query = """
        SELECT
            sensor.location_id,
            sensor.sensor_name,
            sensor.latitude,
            sensor.longitude,
            sensor.status,
            latest.sensing_datetime AS last_seen_at,
            latest.total_count,
            latest.crowd_level
        FROM sensor_location AS sensor
        LEFT JOIN LATERAL (
            SELECT sensing_datetime, total_count, crowd_level
            FROM pedestrian_minute_count
            WHERE location_id = sensor.location_id
            ORDER BY sensing_datetime DESC
            LIMIT 1
        ) AS latest ON TRUE
        ORDER BY sensor.location_id
        LIMIT %s
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (limit,))
        return [SensorResponse.model_validate(row) for row in cursor.fetchall()]
