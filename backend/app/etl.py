from __future__ import annotations

import argparse
import json
import logging
import os
import ssl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import psycopg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.crowd import classify_crowd_level

logger = logging.getLogger(__name__)

MINUTE_COUNTS_DATASET = "pedestrian-counting-system-past-hour-counts-per-minute"
SENSOR_LOCATIONS_DATASET = "pedestrian-counting-system-sensor-locations"
TRANSIT_STOPS_DATASET = "victorian-public-transport-stops"
CATALOGUE_RECORDS_URL = "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/{dataset}/records"
CATALOGUE_EXPORT_URL = "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/{dataset}/exports/json"
MAX_RECORDS_PAGE_SIZE = 100
MAX_OPEN_DATA_RECORDS = 10_000
ETL_LOCK_ID = 5_120_020
ETL_SCOPE_MINUTE = "minute"
ETL_SCOPE_REFERENCE = "reference"
ETL_SCOPE_ALL = "all"
ETL_SCOPES = frozenset({ETL_SCOPE_MINUTE, ETL_SCOPE_REFERENCE, ETL_SCOPE_ALL})
ETLScope = Literal["minute", "reference", "all"]
TRANSIT_STOPS_URL = (
    "https://opendata.transport.vic.gov.au/dataset/6d36dfd9-8693-4552-8a03-05eb29a391fd/"
    "resource/a2cba0b0-bddc-4b87-b495-2b6b7013af6e/download/public_transport_stops.geojson"
)
CBD_BOUNDS = {"minimum_longitude": 144.94, "maximum_longitude": 144.99, "minimum_latitude": -37.825, "maximum_latitude": -37.80}


class OpenDataRateLimitError(RuntimeError):
    """Raised when the City of Melbourne rejects an Open Data request due to rate limiting."""

    def __init__(self, message: str, *, reset_time: str | None = None) -> None:
        super().__init__(message)
        self.reset_time = reset_time


class ETLAlreadyRunningError(RuntimeError):
    """Raised when another ingestion holds the database-backed job lock."""


class ETLRefreshError(RuntimeError):
    """Raised after one or more independent refreshes fail during an all-data run."""


class TLS12HTTPAdapter(HTTPAdapter):
    """Use TLS 1.2 for the City of Melbourne Open Data service."""

    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any) -> None:
        context = ssl.create_default_context()
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        pool_kwargs["ssl_context"] = context
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def open_data_session() -> requests.Session:
    """Return a resilient session for external public-data providers."""
    retries = Retry(
        total=4,
        connect=4,
        read=4,
        other=4,
        backoff_factor=1,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", TLS12HTTPAdapter(max_retries=retries))

    api_key = os.getenv("CITY_OPEN_DATA_API_KEY", "").strip()
    if api_key:
        session.headers["Authorization"] = f"Apikey {api_key}"
    return session


def validate_scope(scope: str) -> ETLScope:
    """Validate the public ETL scope without accepting arbitrary datasets or functions."""
    if scope not in ETL_SCOPES:
        allowed = ", ".join(sorted(ETL_SCOPES))
        raise ValueError(f"ETL scope must be one of: {allowed}.")
    return scope  # type: ignore[return-value]


def _rate_limit_error(response: Any, *, dataset: str, endpoint: str) -> OpenDataRateLimitError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    reset_time = payload.get("reset_time") if isinstance(payload, dict) else None
    reset_hint = f" The provider reports a reset time of {reset_time}." if reset_time else ""
    return OpenDataRateLimitError(
        f"City of Melbourne Open Data rate limit reached for dataset '{dataset}' via {endpoint}.{reset_hint}",
        reset_time=reset_time if isinstance(reset_time, str) else None,
    )


def _raise_for_open_data_response(response: Any, *, dataset: str, endpoint: str) -> None:
    if response.status_code == 429:
        raise _rate_limit_error(response, dataset=dataset, endpoint=endpoint)
    try:
        response.raise_for_status()
    except requests.RequestException as error:
        status_code = getattr(error.response, "status_code", "no response")
        raise RuntimeError(
            f"City of Melbourne request failed for dataset '{dataset}' via {endpoint} (status {status_code})."
        ) from error


def fetch_records(
    dataset: str,
    page_size: int,
    max_records: int,
    order_by: str | None = None,
    where: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch a records-endpoint fallback snapshot using only supported page sizes."""
    if not 1 <= page_size <= MAX_RECORDS_PAGE_SIZE:
        raise ValueError(f"ETL_PAGE_SIZE must be between 1 and {MAX_RECORDS_PAGE_SIZE} for the records endpoint.")
    if max_records < 1:
        raise ValueError("ETL_MAX_RECORDS must be at least 1.")

    records: list[dict[str, Any]] = []
    snapshot_limit = min(max_records, MAX_OPEN_DATA_RECORDS - 1)
    offset = 0
    url = CATALOGUE_RECORDS_URL.format(dataset=dataset)
    session = open_data_session()

    logger.info(
        "Fetching City of Melbourne records dataset '%s' with page size %s (up to %s records).",
        dataset,
        page_size,
        snapshot_limit,
    )
    while len(records) < snapshot_limit:
        limit = min(page_size, snapshot_limit - len(records))
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if order_by:
            params["order_by"] = order_by
        if where:
            params["where"] = where

        response = session.get(url, params=params, timeout=30)
        _raise_for_open_data_response(response, dataset=dataset, endpoint="records")
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError(f"City of Melbourne records response for '{dataset}' was not valid JSON.") from error
        page = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(page, list):
            raise RuntimeError(f"City of Melbourne records response for '{dataset}' did not contain a results list.")
        if not page:
            break
        records.extend(page)
        if len(page) < limit:
            break
        offset += len(page)

    logger.info("Fetched %s record(s) from City of Melbourne records dataset '%s'.", len(records), dataset)
    return records


def parse_export_records(payload: Any, dataset: str) -> list[dict[str, Any]]:
    """Normalise JSON export responses without assuming they use the records wrapper."""
    if isinstance(payload, list) and all(isinstance(record, dict) for record in payload):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "records"):
            records = payload.get(key)
            if isinstance(records, list) and all(isinstance(record, dict) for record in records):
                return records
    raise RuntimeError(f"City of Melbourne JSON export for '{dataset}' had an unsupported response shape.")


def fetch_export_records(dataset: str, order_by: str | None = None) -> list[dict[str, Any]]:
    """Fetch one JSON export, avoiding repeated records-endpoint pagination."""
    url = CATALOGUE_EXPORT_URL.format(dataset=dataset)
    params: dict[str, str] = {}
    if order_by:
        params["order_by"] = order_by
    response = open_data_session().get(url, params=params, timeout=90)
    _raise_for_open_data_response(response, dataset=dataset, endpoint="exports/json")
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(f"City of Melbourne JSON export for '{dataset}' was not valid JSON.") from error
    records = parse_export_records(payload, dataset)
    logger.info("Fetched %s record(s) from City of Melbourne JSON export '%s'.", len(records), dataset)
    return records


def archive_raw_records(dataset: str, records: Any, data_dir: Path) -> None:
    """Archive source payloads only when explicitly enabled for a persistent local data directory."""
    if os.getenv("ARCHIVE_RAW_RECORDS", "false").lower() not in {"1", "true", "yes"}:
        return
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = raw_dir / f"{dataset}_{timestamp}.json"
    destination.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def normalise_columns(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    return frame


def clean_sensor_locations(records: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    frame = normalise_columns(records)
    required = {"location_id", "sensor_name", "latitude", "longitude"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Sensor dataset is missing expected fields: {sorted(missing)}")

    for column in ("location_id", "latitude", "longitude"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["location_id", "sensor_name", "latitude", "longitude"])
    frame = frame.drop_duplicates(subset=["location_id"], keep="last")
    frame["location_id"] = frame["location_id"].astype(int)

    description = frame.get("sensor_description", pd.Series([None] * len(frame)))
    status = frame.get("status", pd.Series([None] * len(frame)))
    return [
        (
            row.location_id,
            row.sensor_name,
            description.iloc[index],
            float(row.latitude),
            float(row.longitude),
            status.iloc[index],
        )
        for index, row in enumerate(frame.itertuples(index=False))
    ]


def clean_minute_counts(
    records: list[dict[str, Any]],
    low_max: int,
    medium_max: int,
    city_timezone: str,
    lookback_minutes: int = 60,
) -> list[tuple[Any, ...]]:
    frame = normalise_columns(records)
    required = {"location_id", "sensing_datetime"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Minute-count dataset is missing expected fields: {sorted(missing)}")

    for column in ("location_id", "direction_1", "direction_2", "total_of_directions"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["location_id"] = pd.to_numeric(frame["location_id"], errors="coerce")
    timestamps = pd.to_datetime(frame["sensing_datetime"], errors="coerce")
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(city_timezone, ambiguous="NaT", nonexistent="NaT")
    else:
        timestamps = timestamps.dt.tz_convert(city_timezone)
    frame["sensing_datetime"] = timestamps

    directions = frame.reindex(columns=["direction_1", "direction_2"]).fillna(0).sum(axis=1)
    totals = frame.get("total_of_directions", directions).fillna(directions)
    frame["total_count"] = totals
    frame = frame.dropna(subset=["location_id", "sensing_datetime", "total_count"])
    frame = frame[frame["total_count"] >= 0]
    if frame.empty:
        raise ValueError("Minute-count snapshot contains no usable records.")

    newest_timestamp = frame["sensing_datetime"].max()
    window_start = newest_timestamp - timedelta(minutes=int(lookback_minutes))
    frame = frame[frame["sensing_datetime"] >= window_start]
    frame = frame.drop_duplicates(subset=["location_id", "sensing_datetime"], keep="last")
    frame["location_id"] = frame["location_id"].astype(int)
    frame["total_count"] = frame["total_count"].astype(int)

    rows: list[tuple[Any, ...]] = []
    for row in frame.itertuples(index=False):
        direction_1 = None if pd.isna(getattr(row, "direction_1", None)) else int(row.direction_1)
        direction_2 = None if pd.isna(getattr(row, "direction_2", None)) else int(row.direction_2)
        rows.append(
            (
                row.location_id,
                row.sensing_datetime.to_pydatetime(),
                direction_1,
                direction_2,
                row.total_count,
                classify_crowd_level(row.total_count, low_max, medium_max),
            )
        )
    return rows


def transit_mode(source_mode: object) -> str | None:
    normalised = str(source_mode or "").upper()
    if "TRAM" in normalised:
        return "tram"
    if "TRAIN" in normalised:
        return "train"
    if "BUS" in normalised:
        return "bus"
    if "COACH" in normalised:
        return "coach"
    return None


def clean_transit_access_points(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Keep map-ready public-transport stops within the onboarding MVP CBD boundary."""
    clean_rows: dict[str, tuple[Any, ...]] = {}
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2:
            continue
        try:
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
        except (TypeError, ValueError):
            continue
        if not (
            CBD_BOUNDS["minimum_longitude"] <= longitude <= CBD_BOUNDS["maximum_longitude"]
            and CBD_BOUNDS["minimum_latitude"] <= latitude <= CBD_BOUNDS["maximum_latitude"]
        ):
            continue

        source_mode = str(properties.get("MODE") or "").strip()
        mode = transit_mode(source_mode)
        stop_id = str(properties.get("STOP_ID") or "").strip()
        name = str(properties.get("STOP_NAME") or "").strip()
        if mode and stop_id and name:
            access_point_id = f"{mode}:{stop_id}"
            clean_rows[access_point_id] = (access_point_id, name, mode, source_mode, latitude, longitude)
    return list(clean_rows.values())


def start_refresh(conn: psycopg.Connection[Any], dataset: str, source_url: str) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO data_refresh_log (dataset_name, source_url, status)
            VALUES (%s, %s, 'running')
            RETURNING refresh_id
            """,
            (dataset, source_url),
        )
        return int(cursor.fetchone()[0])


def finish_refresh(
    conn: psycopg.Connection[Any], refresh_id: int, status: str, received: int, upserted: int, error: str | None = None
) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE data_refresh_log
            SET completed_at = NOW(), status = %s, records_received = %s,
                records_upserted = %s, error_message = %s
            WHERE refresh_id = %s
            """,
            (status, received, upserted, error, refresh_id),
        )


def upsert_sensor_locations(conn: psycopg.Connection[Any], rows: list[tuple[Any, ...]]) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO sensor_location
                (location_id, sensor_name, sensor_description, latitude, longitude, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (location_id) DO UPDATE SET
                sensor_name = EXCLUDED.sensor_name,
                sensor_description = EXCLUDED.sensor_description,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                status = EXCLUDED.status,
                updated_at = NOW()
            """,
            rows,
        )


def upsert_minute_counts(conn: psycopg.Connection[Any], rows: list[tuple[Any, ...]]) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO pedestrian_minute_count
                (location_id, sensing_datetime, direction_1, direction_2, total_count, crowd_level)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (location_id, sensing_datetime) DO UPDATE SET
                direction_1 = EXCLUDED.direction_1,
                direction_2 = EXCLUDED.direction_2,
                total_count = EXCLUDED.total_count,
                crowd_level = EXCLUDED.crowd_level,
                source_fetched_at = NOW()
            """,
            rows,
        )


def upsert_transit_access_points(conn: psycopg.Connection[Any], rows: list[tuple[Any, ...]]) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO transit_access_point
                (access_point_id, name, mode, source_mode, latitude, longitude, source_dataset)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (access_point_id) DO UPDATE SET
                name = EXCLUDED.name,
                mode = EXCLUDED.mode,
                source_mode = EXCLUDED.source_mode,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                source_dataset = EXCLUDED.source_dataset,
                source_fetched_at = NOW(),
                updated_at = NOW()
            """,
            [(*row, TRANSIT_STOPS_DATASET) for row in rows],
        )


def prune_expired_minute_counts(conn: psycopg.Connection[Any], retention_minutes: int) -> int:
    if retention_minutes < 60:
        raise ValueError("MINUTE_RETENTION_MINUTES must be at least 60.")
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM pedestrian_minute_count WHERE sensing_datetime < NOW() - (%s * INTERVAL '1 minute')",
            (retention_minutes,),
        )
        return cursor.rowcount


def sensor_locations_exist(conn: psycopg.Connection[Any]) -> bool:
    with conn.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM sensor_location)")
        return bool(cursor.fetchone()[0])


def reference_refresh_due(conn: psycopg.Connection[Any], interval_hours: int) -> bool:
    """Return whether either static source lacks a recent successful refresh."""
    if interval_hours < 1:
        raise ValueError("REFERENCE_REFRESH_INTERVAL_HOURS must be at least 1.")
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT dataset_name)
            FROM data_refresh_log
            WHERE dataset_name = ANY(%s)
              AND status = 'succeeded'
              AND completed_at >= NOW() - (%s * INTERVAL '1 hour')
            """,
            ([SENSOR_LOCATIONS_DATASET, TRANSIT_STOPS_DATASET], interval_hours),
        )
        successful_sources = int(cursor.fetchone()[0])
    return successful_sources < 2


@contextmanager
def ingestion_lock(conn: psycopg.Connection[Any]) -> Iterator[None]:
    """Use a session advisory lock so schedulers and manual calls cannot overlap."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (ETL_LOCK_ID,))
        acquired = bool(cursor.fetchone()[0])
    if not acquired:
        raise ETLAlreadyRunningError("An Open Data ingestion is already running.")
    try:
        yield
    finally:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (ETL_LOCK_ID,))


RefreshWork = Callable[[], tuple[int, int]]


def run_refresh(
    conn: psycopg.Connection[Any], dataset: str, source_url: str, work: RefreshWork
) -> tuple[int, int]:
    """Persist refresh logs even when the source request or database write fails."""
    refresh_id = start_refresh(conn, dataset, source_url)
    conn.commit()
    try:
        received, upserted = work()
    except OpenDataRateLimitError as error:
        conn.rollback()
        finish_refresh(conn, refresh_id, "rate_limited", 0, 0, str(error))
        conn.commit()
        raise
    except Exception as error:
        conn.rollback()
        finish_refresh(conn, refresh_id, "failed", 0, 0, str(error))
        conn.commit()
        raise
    else:
        finish_refresh(conn, refresh_id, "succeeded", received, upserted)
        conn.commit()
        return received, upserted


def ingest_sensor_locations(conn: psycopg.Connection[Any], data_dir: Path) -> tuple[int, int]:
    source_url = CATALOGUE_EXPORT_URL.format(dataset=SENSOR_LOCATIONS_DATASET)

    def work() -> tuple[int, int]:
        records = fetch_export_records(SENSOR_LOCATIONS_DATASET)
        archive_raw_records(SENSOR_LOCATIONS_DATASET, records, data_dir)
        rows = clean_sensor_locations(records)
        upsert_sensor_locations(conn, rows)
        return len(records), len(rows)

    return run_refresh(conn, SENSOR_LOCATIONS_DATASET, source_url, work)


def ingest_minute_counts(
    conn: psycopg.Connection[Any],
    data_dir: Path,
    *,
    low_max: int,
    medium_max: int,
    city_timezone: str,
    lookback_minutes: int,
    retention_minutes: int,
) -> tuple[int, int]:
    source_url = CATALOGUE_EXPORT_URL.format(dataset=MINUTE_COUNTS_DATASET)

    def work() -> tuple[int, int]:
        records = fetch_export_records(MINUTE_COUNTS_DATASET, order_by="sensing_datetime desc")
        archive_raw_records(MINUTE_COUNTS_DATASET, records, data_dir)
        rows = clean_minute_counts(records, low_max, medium_max, city_timezone, lookback_minutes)
        upsert_minute_counts(conn, rows)
        deleted = prune_expired_minute_counts(conn, retention_minutes)
        logger.info("Pruned %s expired minute-count record(s).", deleted)
        return len(records), len(rows)

    return run_refresh(conn, MINUTE_COUNTS_DATASET, source_url, work)


def ingest_transit_access_points(conn: psycopg.Connection[Any], data_dir: Path) -> tuple[int, int]:
    def work() -> tuple[int, int]:
        response = open_data_session().get(TRANSIT_STOPS_URL, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Public transport stop response was not a JSON object.")
        archive_raw_records(TRANSIT_STOPS_DATASET, payload, data_dir)
        rows = clean_transit_access_points(payload)
        upsert_transit_access_points(conn, rows)
        return len(payload.get("features", [])), len(rows)

    return run_refresh(conn, TRANSIT_STOPS_DATASET, TRANSIT_STOPS_URL, work)


def ingest_reference_data(conn: psycopg.Connection[Any], data_dir: Path) -> None:
    """Refresh relatively static sensor and public-transport reference data."""
    ingest_sensor_locations(conn, data_dir)
    ingest_transit_access_points(conn, data_dir)


def ingest(scope: str = ETL_SCOPE_ALL) -> None:
    """Run only the validated ETL scope requested by a scheduler or operator."""
    scope = validate_scope(scope)
    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    low_max = int(os.getenv("CROWD_LOW_MAX", "10"))
    medium_max = int(os.getenv("CROWD_MEDIUM_MAX", "30"))
    city_timezone = os.getenv("CITY_TIMEZONE", "Australia/Melbourne")
    lookback_minutes = int(os.getenv("MINUTE_LOOKBACK_MINUTES", "60"))
    retention_minutes = int(os.getenv("MINUTE_RETENTION_MINUTES", "90"))
    reference_interval_hours = int(os.getenv("REFERENCE_REFRESH_INTERVAL_HOURS", "24"))
    errors: list[Exception] = []

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with ingestion_lock(conn):
            sensor_locations_ready = sensor_locations_exist(conn)
            if scope in {ETL_SCOPE_REFERENCE, ETL_SCOPE_ALL}:
                try:
                    ingest_reference_data(conn, data_dir)
                    sensor_locations_ready = True
                except Exception as error:
                    # The sensor refresh may have succeeded before the independent
                    # transit refresh failed, so re-check before deciding whether
                    # the minute foreign-key import can proceed.
                    sensor_locations_ready = sensor_locations_exist(conn)
                    errors.append(error)
                    logger.exception("Reference-data refresh failed")

            if scope in {ETL_SCOPE_MINUTE, ETL_SCOPE_ALL}:
                should_refresh_reference = not sensor_locations_ready or reference_refresh_due(
                    conn, reference_interval_hours
                )
                if scope == ETL_SCOPE_MINUTE and should_refresh_reference:
                    logger.info(
                        "Reference data is missing or older than %s hour(s); refreshing it before minute ingestion.",
                        reference_interval_hours,
                    )
                    try:
                        ingest_reference_data(conn, data_dir)
                        sensor_locations_ready = True
                    except Exception as error:
                        errors.append(error)
                        logger.exception("Reference refresh failed; minute ingestion will continue only if sensor locations exist")
                        sensor_locations_ready = sensor_locations_exist(conn)
                if sensor_locations_ready:
                    try:
                        ingest_minute_counts(
                            conn,
                            data_dir,
                            low_max=low_max,
                            medium_max=medium_max,
                            city_timezone=city_timezone,
                            lookback_minutes=lookback_minutes,
                            retention_minutes=retention_minutes,
                        )
                    except Exception as error:
                        errors.append(error)
                        logger.exception("Minute-count refresh failed")

    if errors:
        if scope != ETL_SCOPE_ALL and len(errors) == 1:
            raise errors[0]
        raise ETLRefreshError("One or more ETL refreshes failed; inspect data_refresh_log and service logs.") from errors[0]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Refresh SensoryWay Open Data.")
    parser.add_argument("--scope", choices=sorted(ETL_SCOPES), default=ETL_SCOPE_ALL)
    args = parser.parse_args(argv)
    ingest(args.scope)
    print(f"Open-data {args.scope} ingestion completed successfully.")


if __name__ == "__main__":
    main()
