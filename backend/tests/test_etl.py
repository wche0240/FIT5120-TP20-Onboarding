from datetime import datetime, timezone

import pytest

from app.etl import (
    clean_minute_counts,
    clean_sensor_locations,
    clean_transit_access_points,
    fetch_records,
    OpenDataRateLimitError,
    open_data_session,
)
from scripts.run_scheduled_ingest import rate_limit_delay_seconds, refresh_interval_seconds


def test_clean_sensor_locations_removes_duplicate_sensor_ids() -> None:
    rows = clean_sensor_locations(
        [
            {"location_id": 1, "sensor_name": "Old", "latitude": -37.81, "longitude": 144.96},
            {"location_id": 1, "sensor_name": "New", "latitude": -37.82, "longitude": 144.97},
        ]
    )
    assert rows == [(1, "New", None, -37.82, 144.97, None)]


def test_clean_minute_counts_removes_duplicate_composite_keys() -> None:
    rows = clean_minute_counts(
        [
            {
                "location_id": 1,
                "sensing_datetime": "2026-08-04 09:00:00",
                "direction_1": 25,
                "direction_2": 26,
                "total_of_directions": 51,
            },
            {
                "location_id": 1,
                "sensing_datetime": "2026-08-04 09:00:00",
                "direction_1": 10,
                "direction_2": 10,
                "total_of_directions": 20,
            },
        ],
        low_max=50,
        medium_max=150,
        city_timezone="Australia/Melbourne",
        lookback_minutes=0,
    )
    assert len(rows) == 1
    assert rows[0][4:] == (20, "low")


def test_clean_minute_counts_keeps_only_the_latest_hour() -> None:
    rows = clean_minute_counts(
        [
            {"location_id": 1, "sensing_datetime": "2026-08-04 08:59:00", "total_of_directions": 1},
            {"location_id": 1, "sensing_datetime": "2026-08-04 09:00:00", "total_of_directions": 2},
            {"location_id": 1, "sensing_datetime": "2026-08-04 10:00:00", "total_of_directions": 3},
        ],
        low_max=50,
        medium_max=150,
        city_timezone="Australia/Melbourne",
        lookback_minutes=60,
    )
    assert [row[4] for row in rows] == [2, 3]


def test_clean_transit_access_points_keeps_supported_cbd_stops() -> None:
    rows = clean_transit_access_points(
        {
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [144.9631, -37.8136]},
                    "properties": {"STOP_ID": "100", "STOP_NAME": "CBD Tram Stop", "MODE": "METRO TRAM"},
                },
                {
                    "geometry": {"type": "Point", "coordinates": [145.12, -37.7]},
                    "properties": {"STOP_ID": "101", "STOP_NAME": "Outside MVP area", "MODE": "METRO BUS"},
                },
                {
                    "geometry": {"type": "Point", "coordinates": [144.97, -37.815]},
                    "properties": {"STOP_ID": "102", "STOP_NAME": "Unsupported", "MODE": "FERRY"},
                },
            ]
        }
    )
    assert rows == [("tram:100", "CBD Tram Stop", "tram", "METRO TRAM", -37.8136, 144.9631)]


def test_open_data_session_retries_transient_provider_failures() -> None:
    session = open_data_session()
    retries = session.get_adapter("https://").max_retries

    assert retries.total == 4
    assert retries.connect == 4
    assert retries.read == 4
    assert retries.other == 4
    assert 429 not in retries.status_forcelist


def test_fetch_records_stops_before_the_provider_offset_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_offsets: list[int] = []

    class Response:
        def __init__(self, limit: int) -> None:
            self.limit = limit
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, int]]]:
            return {"results": [{"row": index} for index in range(self.limit)]}

    class Session:
        def get(self, _url: str, *, params: dict[str, int], timeout: int) -> Response:
            requested_offsets.append(params["offset"])
            return Response(params["limit"])

    monkeypatch.setattr("app.etl.open_data_session", lambda: Session())

    records = fetch_records("minute-counts", page_size=7_500, max_records=20_000)

    assert len(records) == 10_000
    assert requested_offsets == [0, 7_500]


def test_fetch_records_reports_the_provider_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 429

        @staticmethod
        def json() -> dict[str, str]:
            return {"reset_time": "2026-08-11T00:00:00Z"}

    class Session:
        @staticmethod
        def get(_url: str, *, params: dict[str, int], timeout: int) -> Response:
            return Response()

    monkeypatch.setattr("app.etl.open_data_session", lambda: Session())

    with pytest.raises(OpenDataRateLimitError, match="2026-08-11T00:00:00Z"):
        fetch_records("minute-counts", page_size=10, max_records=10)


def test_fetch_records_rejects_an_invalid_page_size() -> None:
    with pytest.raises(ValueError, match="ETL_PAGE_SIZE must be at least 1"):
        fetch_records("minute-counts", page_size=0, max_records=100)


def test_scheduler_defaults_to_a_fifteen_minute_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ETL_REFRESH_INTERVAL_MINUTES", raising=False)
    assert refresh_interval_seconds() == 15 * 60


def test_scheduler_rejects_a_non_positive_refresh_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETL_REFRESH_INTERVAL_MINUTES", "0")
    with pytest.raises(ValueError, match="at least 1 minute"):
        refresh_interval_seconds()


def test_scheduler_waits_until_provider_quota_reset() -> None:
    error = OpenDataRateLimitError("quota exhausted", reset_time="2026-08-11T00:00:00Z")
    current_time = datetime(2026, 8, 10, 23, 45, tzinfo=timezone.utc)

    assert rate_limit_delay_seconds(error, fallback_seconds=15 * 60, now=current_time) == 16 * 60


def test_scheduler_uses_normal_interval_without_a_future_quota_reset() -> None:
    error = OpenDataRateLimitError("quota exhausted", reset_time="invalid")

    assert rate_limit_delay_seconds(error, fallback_seconds=15 * 60) == 15 * 60
