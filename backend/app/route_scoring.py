from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sqrt
from typing import Iterable

from app.crowd import classify_crowd_level

EARTH_RADIUS_METRES = 6_371_000


@dataclass(frozen=True)
class SensorReading:
    location_id: int
    latitude: float
    longitude: float
    total_count: int


@dataclass(frozen=True)
class RouteCrowdScore:
    crowd_score: int | None
    crowd_level: str | None
    matched_sensor_count: int


def point_to_segment_distance_metres(
    latitude: float,
    longitude: float,
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
) -> float:
    """Approximate the distance from a sensor point to a short route segment."""
    reference_latitude = radians((latitude + start_latitude + end_latitude) / 3)

    def project(point_latitude: float, point_longitude: float) -> tuple[float, float]:
        return (
            EARTH_RADIUS_METRES * radians(point_longitude) * cos(reference_latitude),
            EARTH_RADIUS_METRES * radians(point_latitude),
        )

    point_x, point_y = project(latitude, longitude)
    start_x, start_y = project(start_latitude, start_longitude)
    end_x, end_y = project(end_latitude, end_longitude)
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    segment_length_squared = delta_x**2 + delta_y**2

    if segment_length_squared == 0:
        return sqrt((point_x - start_x) ** 2 + (point_y - start_y) ** 2)

    position = ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / segment_length_squared
    position = min(1.0, max(0.0, position))
    closest_x = start_x + position * delta_x
    closest_y = start_y + position * delta_y
    return sqrt((point_x - closest_x) ** 2 + (point_y - closest_y) ** 2)


def score_route(
    coordinates: list[tuple[float, float]],
    readings: Iterable[SensorReading],
    sensor_radius_metres: int,
    low_max: int,
    medium_max: int,
) -> RouteCrowdScore:
    """Use the busiest sensor near the route as a transparent, conservative score."""
    matched_counts: list[int] = []
    route_segments = list(zip(coordinates, coordinates[1:]))

    for reading in readings:
        for (start_longitude, start_latitude), (end_longitude, end_latitude) in route_segments:
            distance = point_to_segment_distance_metres(
                reading.latitude,
                reading.longitude,
                start_latitude,
                start_longitude,
                end_latitude,
                end_longitude,
            )
            if distance <= sensor_radius_metres:
                matched_counts.append(reading.total_count)
                break

    if not matched_counts:
        return RouteCrowdScore(crowd_score=None, crowd_level=None, matched_sensor_count=0)

    crowd_score = max(matched_counts)
    return RouteCrowdScore(
        crowd_score=crowd_score,
        crowd_level=classify_crowd_level(crowd_score, low_max, medium_max),
        matched_sensor_count=len(matched_counts),
    )
