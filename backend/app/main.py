from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_db
from app.etl import ingest
from app.geocoding import GeocodingError, is_in_melbourne_cbd, search_cbd_locations
from app.route_scoring import SensorReading, assess_route_segments, score_route
from app.routing import OpenRouteServiceError, request_walking_routes
from app.schemas import (
    DataStatusResponse,
    HealthResponse,
    LocationSearchResult,
    RouteOption,
    RouteScoreRequest,
    RouteScoreResponse,
    RoutesRequest,
    RoutesResponse,
    SensorResponse,
    TransitAccessPointResponse,
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
    configured_minutes = int(os.getenv("DATA_STALE_AFTER_MINUTES", "45"))
    if configured_minutes <= 0:
        raise RuntimeError("DATA_STALE_AFTER_MINUTES must be positive")
    return configured_minutes


def crowd_thresholds() -> tuple[int, int]:
    low_max = int(os.getenv("CROWD_LOW_MAX", "10"))
    medium_max = int(os.getenv("CROWD_MEDIUM_MAX", "30"))
    if low_max < 0 or medium_max < low_max:
        raise RuntimeError("Crowd thresholds are invalid")
    return low_max, medium_max


def load_sensor_rows(connection: psycopg.Connection[Any]) -> list[dict[str, Any]]:
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
        return cursor.fetchall()


def score_coordinates(
    coordinates: list[tuple[float, float]],
    connection: psycopg.Connection[Any],
) -> RouteScoreResponse:
    rows = load_sensor_rows(connection)
    if not rows:
        return RouteScoreResponse(
            status="unavailable",
            crowd_level=None,
            crowd_score=None,
            data_coverage_confidence=None,
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
            data_coverage_confidence=None,
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
            data_coverage_confidence=score.data_coverage_confidence,
            matched_sensor_count=0,
            latest_data_at=latest_data_at,
            warning="No pedestrian sensors cover this route.",
        )

    route_segments = assess_route_segments(
        coordinates,
        readings,
        sensor_radius_metres=int(os.getenv("ROUTE_SENSOR_RADIUS_METRES", "80")),
        low_max=low_max,
        medium_max=medium_max,
    )

    return RouteScoreResponse(
        status="available",
        crowd_level=score.crowd_level,
        crowd_score=score.crowd_score,
        data_coverage_confidence=score.data_coverage_confidence,
        matched_sensor_count=score.matched_sensor_count,
        latest_data_at=latest_data_at,
        warning=None,
        crowd_segments=[
            {
                "coordinates": [{"longitude": longitude, "latitude": latitude} for longitude, latitude in segment.coordinates],
                "crowd_level": segment.crowd_level,
                "crowd_score": segment.crowd_score,
                "matched_sensor_count": segment.matched_sensor_count,
            }
            for segment in route_segments
        ],
    )


def route_limit(level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[level]


def distance_in_metres(
    latitude_one: float,
    longitude_one: float,
    latitude_two: float,
    longitude_two: float,
) -> float:
    """Return the great-circle distance between two WGS84 coordinates."""
    latitude_delta = radians(latitude_two - latitude_one)
    longitude_delta = radians(longitude_two - longitude_one)
    haversine = sin(latitude_delta / 2) ** 2 + cos(radians(latitude_one)) * cos(radians(latitude_two)) * sin(longitude_delta / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(haversine))


@app.get("/api/v1/health", response_model=HealthResponse)
def health(connection: psycopg.Connection[Any] = Depends(get_db)) -> HealthResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
    return HealthResponse(status="ok", database="connected")


@app.post("/api/v1/internal/ingest")
def trigger_open_data_ingestion(x_etl_token: str | None = Header(default=None)) -> dict[str, str]:
    """Run one protected Open Data refresh for an external scheduler."""
    expected_token = os.getenv("ETL_TRIGGER_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=503, detail="ETL trigger is not configured on this server.")
    if not hmac.compare_digest(expected_token, x_etl_token or ""):
        raise HTTPException(status_code=401, detail="Invalid ETL trigger token.")

    ingest()
    return {"status": "completed"}


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


@app.get("/api/v1/location-search", response_model=list[LocationSearchResult])
def location_search(query: str = Query(min_length=3, max_length=120)) -> list[LocationSearchResult]:
    normalised_query = query.strip()
    if len(normalised_query) < 3:
        raise HTTPException(status_code=422, detail="Enter at least three non-space characters to search for a destination.")
    try:
        return [LocationSearchResult.model_validate(location) for location in search_cbd_locations(normalised_query)]
    except GeocodingError as error:
        raise HTTPException(status_code=503, detail="Location search is temporarily unavailable.") from error


@app.get("/api/v1/transit-access-points", response_model=list[TransitAccessPointResponse])
def transit_access_points(
    limit: int = Query(default=500, ge=1, le=800),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    radius_metres: int = Query(default=500, ge=50, le=2_000),
    connection: psycopg.Connection[Any] = Depends(get_db),
) -> list[TransitAccessPointResponse]:
    if (longitude is None) != (latitude is None):
        raise HTTPException(status_code=422, detail="Longitude and latitude must be supplied together.")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT access_point_id, name, mode, source_mode, latitude, longitude
            FROM transit_access_point
            ORDER BY mode, name, access_point_id
            """
        )
        rows = cursor.fetchall()

    access_points: list[TransitAccessPointResponse] = []
    for row in rows:
        distance_metres = None
        if longitude is not None and latitude is not None:
            distance_metres = distance_in_metres(latitude, longitude, float(row["latitude"]), float(row["longitude"]))
            if distance_metres > radius_metres:
                continue

        access_points.append(
            TransitAccessPointResponse(
                access_point_id=row["access_point_id"],
                name=row["name"],
                mode=row["mode"],
                source_mode=row["source_mode"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                distance_metres=round(distance_metres, 1) if distance_metres is not None else None,
            )
        )

    if longitude is not None and latitude is not None:
        access_points.sort(key=lambda access_point: access_point.distance_metres or 0)
    return access_points[:limit]


@app.post("/api/v1/route-score", response_model=RouteScoreResponse)
def route_score(
    request: RouteScoreRequest,
    connection: psycopg.Connection[Any] = Depends(get_db),
) -> RouteScoreResponse:
    coordinates = [(point.longitude, point.latitude) for point in request.coordinates]
    return score_coordinates(coordinates, connection)


@app.post("/api/v1/routes", response_model=RoutesResponse)
def routes(
    request: RoutesRequest,
    connection: psycopg.Connection[Any] = Depends(get_db),
) -> RoutesResponse:
    minimum_recommendation_coverage = 50.0

    if not is_in_melbourne_cbd(request.destination.longitude, request.destination.latitude):
        raise HTTPException(status_code=422, detail="The onboarding MVP currently supports destinations within Melbourne CBD.")

    api_key = os.getenv("ORS_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Routing is not configured on this server.")

    try:
        provider_routes = request_walking_routes(
            start=(request.start.longitude, request.start.latitude),
            destination=(request.destination.longitude, request.destination.latitude),
            api_key=api_key,
            timeout_seconds=float(os.getenv("ORS_TIMEOUT_SECONDS", "10")),
        )
    except OpenRouteServiceError as error:
        raise HTTPException(status_code=503, detail="The route service is temporarily unavailable.") from error

    options: list[RouteOption] = []
    for route_id, provider_route in enumerate(provider_routes, start=1):
        crowd = score_coordinates(provider_route.coordinates, connection)
        meets_threshold = (
            crowd.status == "available"
            and crowd.crowd_level is not None
            and route_limit(crowd.crowd_level) <= route_limit(request.max_crowd_level)
        )
        options.append(
            RouteOption(
                route_id=route_id,
                distance_metres=provider_route.distance_metres,
                duration_seconds=provider_route.duration_seconds,
                coordinates=[{"longitude": longitude, "latitude": latitude} for longitude, latitude in provider_route.coordinates],
                data_status=crowd.status,
                crowd_level=crowd.crowd_level,
                crowd_score=crowd.crowd_score,
                data_coverage_confidence=crowd.data_coverage_confidence,
                matched_sensor_count=crowd.matched_sensor_count,
                latest_data_at=crowd.latest_data_at,
                crowd_segments=crowd.crowd_segments,
                meets_crowd_threshold=meets_threshold if crowd.status == "available" else None,
                recommended=False,
                warning=crowd.warning,
            )
        )

    eligible_options = [option for option in options if option.meets_crowd_threshold]
    if eligible_options:
        highly_covered_options = [
            option
            for option in eligible_options
            if option.data_coverage_confidence is not None and option.data_coverage_confidence > minimum_recommendation_coverage
        ]
        recommendation_pool = highly_covered_options or eligible_options
        selected = min(
            recommendation_pool,
            key=lambda option: (route_limit(option.crowd_level or "high"), option.duration_seconds),
        )
        selected.recommended = True
        return RoutesResponse(
            status="available",
            requested_max_crowd_level=request.max_crowd_level,
            recommended_route_id=selected.route_id,
            routes=options,
            warning=None,
        )

    data_is_current = all(option.data_status == "available" for option in options)
    warning = (
        "No currently monitored route meets the selected crowd threshold."
        if data_is_current
        else "Walking routes are shown, but current crowd data is unavailable or outdated."
    )
    return RoutesResponse(
        status="available" if data_is_current else "degraded",
        requested_max_crowd_level=request.max_crowd_level,
        recommended_route_id=None,
        routes=options,
        warning=warning,
    )
