from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

ORS_DIRECTIONS_URL = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson"


class OpenRouteServiceError(RuntimeError):
    """A safe, user-facing failure while requesting a route from ORS."""


@dataclass(frozen=True)
class WalkingRoute:
    coordinates: list[tuple[float, float]]
    distance_metres: float
    duration_seconds: float


def parse_walking_routes(payload: dict[str, Any]) -> list[WalkingRoute]:
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise OpenRouteServiceError("The routing provider did not return any routes.")

    routes: list[WalkingRoute] = []
    for feature in features[:3]:
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})
        summary = properties.get("summary", {})
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        try:
            parsed_coordinates = [(float(point[0]), float(point[1])) for point in coordinates]
            routes.append(
                WalkingRoute(
                    coordinates=parsed_coordinates,
                    distance_metres=float(summary["distance"]),
                    duration_seconds=float(summary["duration"]),
                )
            )
        except (IndexError, KeyError, TypeError, ValueError):
            continue

    if not routes:
        raise OpenRouteServiceError("The routing provider returned an invalid route format.")
    return routes


def request_walking_routes(
    *,
    start: tuple[float, float],
    destination: tuple[float, float],
    api_key: str,
    timeout_seconds: float,
) -> list[WalkingRoute]:
    payload = {
        "coordinates": [list(start), list(destination)],
        "instructions": False,
        "alternative_routes": {
            "target_count": 3,
            "weight_factor": 1.4,
            "share_factor": 0.6,
        },
    }
    try:
        response = requests.post(
            ORS_DIRECTIONS_URL,
            headers={"Authorization": api_key, "Accept": "application/geo+json"},
            json=payload,
            timeout=timeout_seconds,
        )
    except requests.RequestException as error:
        raise OpenRouteServiceError("The routing provider could not be reached.") from error

    if response.status_code >= 400:
        raise OpenRouteServiceError("The routing provider could not create a walking route.")

    try:
        return parse_walking_routes(response.json())
    except ValueError as error:
        raise OpenRouteServiceError("The routing provider returned invalid JSON.") from error
