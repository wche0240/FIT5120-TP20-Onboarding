from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_db
from app.route_scoring import SensorReading, score_route
from app.schemas import (
    DataStatusResponse,
    HealthResponse,
    RouteScoreRequest,
    RouteScoreResponse,
    SensorResponse,
)

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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def stale_after_minutes() -> int:
    configured_minutes = int(os.getenv("DATA_STALE_AFTER_MINUTES", "30"))
    if configured_minutes <= 0:
        raise RuntimeError("DATA_STALE_AFTER_MINUTES must be positive")
    return configured_minutes


def crowd_thresholds() -> tuple[int, int]:
    low_max = int(os.getenv("CROWD_LOW_MAX", "50"))
    medium_max = int(os.getenv("CROWD_MEDIUM_MAX", "150"))
    if low_max < 0 or medium_max < low_max:
        raise RuntimeError("Crowd thresholds are invalid")
    return low_max, medium_max


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


@app.post("/api/v1/route-score", response_model=RouteScoreResponse)
def route_score(
    request: RouteScoreRequest,
    connection: psycopg.Connection[Any] = Depends(get_db),
) -> RouteScoreResponse:
    query = """
        SELECT
            sensor.location_id,
            sensor.latitude,
            sensor.longitude,
            latest.sensing_datetime AS last_seen_at,
            latest.total_count
        FROM sensor_location AS sensor
        JOIN LATERAL (
            SELECT sensing_datetime, total_count
            FROM pedestrian_minute_count
            WHERE location_id = sensor.location_id
            ORDER BY sensing_datetime DESC
            LIMIT 1
        ) AS latest ON TRUE
        WHERE sensor.status = 'A'
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    if not rows:
        return RouteScoreResponse(
            status="unavailable",
            crowd_level=None,
            crowd_score=None,
            matched_sensor_count=0,
            latest_data_at=None,
            warning="No pedestrian sensor data is available.",
        )

    latest_data_at = max(row["last_seen_at"] for row in rows)
    if latest_data_at.tzinfo is None:
        latest_data_at = latest_data_at.replace(tzinfo=timezone.utc)
    age_minutes = max(0, int((datetime.now(timezone.utc) - latest_data_at).total_seconds() // 60))
    if age_minutes > stale_after_minutes():
        return RouteScoreResponse(
            status="stale",
            crowd_level=None,
            crowd_score=None,
            matched_sensor_count=0,
            latest_data_at=latest_data_at,
            warning="Pedestrian data is outdated, so no route crowd score is shown.",
        )

    readings = [
        SensorReading(
            location_id=row["location_id"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            total_count=row["total_count"],
        )
        for row in rows
    ]
    coordinates = [(point.longitude, point.latitude) for point in request.coordinates]
    low_max, medium_max = crowd_thresholds()
    score = score_route(
        coordinates,
        readings,
        sensor_radius_metres=int(os.getenv("ROUTE_SENSOR_RADIUS_METRES", "80")),
        low_max=low_max,
        medium_max=medium_max,
    )

    if score.matched_sensor_count == 0:
        return RouteScoreResponse(
            status="unavailable",
            crowd_level=None,
            crowd_score=None,
            matched_sensor_count=0,
            latest_data_at=latest_data_at,
            warning="No pedestrian sensors cover this route.",
        )

    return RouteScoreResponse(
        status="available",
        crowd_level=score.crowd_level,
        crowd_score=score.crowd_score,
        matched_sensor_count=score.matched_sensor_count,
        latest_data_at=latest_data_at,
        warning=None,
    )
