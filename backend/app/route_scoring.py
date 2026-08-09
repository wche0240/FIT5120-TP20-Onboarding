from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
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
    data_coverage_confidence: float | None


@dataclass(frozen=True)
class RouteCrowdSegment:
    coordinates: list[tuple[float, float]]
    crowd_level: str | None
    crowd_score: int | None
    matched_sensor_ids: frozenset[int]

    @property
    def matched_sensor_count(self) -> int:
        return len(self.matched_sensor_ids)


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


def point_to_point_distance_metres(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
) -> float:
    """Return the great-circle distance between two WGS84 coordinates."""
    latitude_delta = radians(end_latitude - start_latitude)
    longitude_delta = radians(end_longitude - start_longitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(start_latitude)) * cos(radians(end_latitude)) * sin(longitude_delta / 2) ** 2
    )
    return EARTH_RADIUS_METRES * 2 * asin(sqrt(haversine))


def score_route(
    coordinates: list[tuple[float, float]],
    readings: Iterable[SensorReading],
    sensor_radius_metres: int,
    low_max: int,
    medium_max: int,
) -> RouteCrowdScore:
    """Use the busiest sensor near the route as a transparent, conservative score."""
    reading_list = list(readings)
    matched_counts: list[int] = []
    route_segments = list(zip(coordinates, coordinates[1:]))
    segment_lengths = [
        point_to_point_distance_metres(start_latitude, start_longitude, end_latitude, end_longitude)
        for (start_longitude, start_latitude), (end_longitude, end_latitude) in route_segments
    ]
    total_distance_metres = sum(segment_lengths)

    if total_distance_metres > 0:
        covered_distance_metres = sum(
            segment_length
            for segment_length, ((start_longitude, start_latitude), (end_longitude, end_latitude)) in zip(
                segment_lengths, route_segments
            )
            if any(
                point_to_segment_distance_metres(
                    reading.latitude,
                    reading.longitude,
                    start_latitude,
                    start_longitude,
                    end_latitude,
                    end_longitude,
                ) <= sensor_radius_metres
                for reading in reading_list
            )
        )
        data_coverage_confidence = round((covered_distance_metres / total_distance_metres) * 100, 1)
    else:
        data_coverage_confidence = None

    for reading in reading_list:
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
        return RouteCrowdScore(
            crowd_score=None,
            crowd_level=None,
            matched_sensor_count=0,
            data_coverage_confidence=data_coverage_confidence,
        )

    crowd_score = max(matched_counts)
    return RouteCrowdScore(
        crowd_score=crowd_score,
        crowd_level=classify_crowd_level(crowd_score, low_max, medium_max),
        matched_sensor_count=len(matched_counts),
        data_coverage_confidence=data_coverage_confidence,
    )


def assess_route_segments(
    coordinates: list[tuple[float, float]],
    readings: Iterable[SensorReading],
    sensor_radius_metres: int,
    low_max: int,
    medium_max: int,
) -> list[RouteCrowdSegment]:
    """Attach the latest nearby sensor reading to each route section.

    A section without a nearby official sensor remains unknown rather than being
    represented as low crowd. Adjacent sections at the same level are merged so
    the map receives a small, readable set of overlay polylines.
    """
    reading_list = list(readings)
    assessed_segments: list[RouteCrowdSegment] = []

    for start, end in zip(coordinates, coordinates[1:]):
        start_longitude, start_latitude = start
        end_longitude, end_latitude = end
        nearby_readings = [
            reading
            for reading in reading_list
            if point_to_segment_distance_metres(
                reading.latitude,
                reading.longitude,
                start_latitude,
                start_longitude,
                end_latitude,
                end_longitude,
            ) <= sensor_radius_metres
        ]

        crowd_score = max((reading.total_count for reading in nearby_readings), default=None)
        crowd_level = (
            classify_crowd_level(crowd_score, low_max, medium_max)
            if crowd_score is not None
            else None
        )
        sensor_ids = frozenset(reading.location_id for reading in nearby_readings)

        if assessed_segments and assessed_segments[-1].crowd_level == crowd_level:
            previous = assessed_segments[-1]
            assessed_segments[-1] = RouteCrowdSegment(
                coordinates=[*previous.coordinates, end],
                crowd_level=crowd_level,
                crowd_score=max(
                    (score for score in (previous.crowd_score, crowd_score) if score is not None),
                    default=None,
                ),
                matched_sensor_ids=previous.matched_sensor_ids | sensor_ids,
            )
            continue

        assessed_segments.append(
            RouteCrowdSegment(
                coordinates=[start, end],
                crowd_level=crowd_level,
                crowd_score=crowd_score,
                matched_sensor_ids=sensor_ids,
            )
        )

    return assessed_segments
