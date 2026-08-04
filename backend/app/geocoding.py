from __future__ import annotations

import os
import time
from functools import lru_cache
from threading import Lock
from typing import Any

import requests

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
CBD_MINIMUM_LONGITUDE = 144.94
CBD_MAXIMUM_LONGITUDE = 144.99
CBD_MINIMUM_LATITUDE = -37.825
CBD_MAXIMUM_LATITUDE = -37.80
_request_lock = Lock()
_last_request_at = 0.0


class GeocodingError(RuntimeError):
    pass


def is_in_melbourne_cbd(longitude: float, latitude: float) -> bool:
    return CBD_MINIMUM_LONGITUDE <= longitude <= CBD_MAXIMUM_LONGITUDE and CBD_MINIMUM_LATITUDE <= latitude <= CBD_MAXIMUM_LATITUDE


@lru_cache(maxsize=100)
def search_cbd_locations(query: str) -> tuple[dict[str, Any], ...]:
    """Search only after a user submits a query; never use this as autocomplete."""
    global _last_request_at

    with _request_lock:
        minimum_interval = float(os.getenv("GEOCODER_MIN_INTERVAL_SECONDS", "1"))
        wait_seconds = minimum_interval - (time.monotonic() - _last_request_at)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        response = requests.get(
            os.getenv("GEOCODER_SEARCH_URL", NOMINATIM_SEARCH_URL),
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 5,
                "countrycodes": "au",
                "viewbox": f"{CBD_MINIMUM_LONGITUDE},{CBD_MAXIMUM_LATITUDE},{CBD_MAXIMUM_LONGITUDE},{CBD_MINIMUM_LATITUDE}",
                "bounded": 1,
            },
            headers={"User-Agent": "SensoryWay-FIT5120-Onboarding/0.1 (educational project)"},
            timeout=float(os.getenv("GEOCODER_TIMEOUT_SECONDS", "8")),
        )
        _last_request_at = time.monotonic()

    try:
        response.raise_for_status()
        matches = response.json()
    except (requests.RequestException, ValueError) as error:
        raise GeocodingError("Location search is temporarily unavailable.") from error

    if not isinstance(matches, list):
        raise GeocodingError("Location search returned an unexpected response.")

    locations: list[dict[str, Any]] = []
    for match in matches:
        try:
            latitude = float(match["lat"])
            longitude = float(match["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not is_in_melbourne_cbd(longitude, latitude):
            continue

        display_name = str(match.get("display_name") or "").strip()
        name = str(match.get("name") or display_name.split(",")[0]).strip()
        if not name or not display_name:
            continue
        locations.append(
            {
                "name": name,
                "display_name": display_name,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    return tuple(locations)
