from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import requests

from app.crowd import classify_crowd_level

MINUTE_COUNTS_DATASET = "pedestrian-counting-system-past-hour-counts-per-minute"
SENSOR_LOCATIONS_DATASET = "pedestrian-counting-system-sensor-locations"
CATALOGUE_URL = "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/{dataset}/records"


def fetch_records(
    dataset: str, page_size: int, max_records: int, order_by: str | None = None
) -> list[dict[str, Any]]:
    """Fetch a bounded dataset snapshot from the City of Melbourne API."""
    records: list[dict[str, Any]] = []
    offset = 0
    url = CATALOGUE_URL.format(dataset=dataset)

    while len(records) < max_records:
        limit = min(page_size, max_records - len(records))
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if order_by:
            params["order_by"] = order_by
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        page = response.json().get("results", [])
        if not page:
            break
        records.extend(page)
        if len(page) < limit:
            break
        offset += len(page)

    return records


def archive_raw_records(dataset: str, records: list[dict[str, Any]], data_dir: Path) -> None:
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
    newest_timestamp = frame["sensing_datetime"].max()
    oldest_timestamp = frame["sensing_datetime"].min()
    required_coverage = timedelta(minutes=int(lookback_minutes))
    if newest_timestamp - oldest_timestamp < required_coverage:
        raise ValueError(
            f"Minute-count snapshot covers only {newest_timestamp - oldest_timestamp}; expected at least {required_coverage}."
        )
    window_start = newest_timestamp - required_coverage
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


def ingest() -> None:
    database_url = os.environ["DATABASE_URL"]
    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    page_size = int(os.getenv("ETL_PAGE_SIZE", "100"))
    max_records = int(os.getenv("ETL_MAX_RECORDS", "20000"))
    low_max = int(os.getenv("CROWD_LOW_MAX", "50"))
    medium_max = int(os.getenv("CROWD_MEDIUM_MAX", "150"))
    city_timezone = os.getenv("CITY_TIMEZONE", "Australia/Melbourne")
    lookback_minutes = int(os.getenv("MINUTE_LOOKBACK_MINUTES", "60"))

    sensor_url = CATALOGUE_URL.format(dataset=SENSOR_LOCATIONS_DATASET)
    minute_url = CATALOGUE_URL.format(dataset=MINUTE_COUNTS_DATASET)

    with psycopg.connect(database_url) as conn:
        sensor_refresh = start_refresh(conn, SENSOR_LOCATIONS_DATASET, sensor_url)
        minute_refresh = start_refresh(conn, MINUTE_COUNTS_DATASET, minute_url)
        try:
            sensor_records = fetch_records(SENSOR_LOCATIONS_DATASET, page_size, max_records)
            archive_raw_records(SENSOR_LOCATIONS_DATASET, sensor_records, data_dir)
            sensor_rows = clean_sensor_locations(sensor_records)
            upsert_sensor_locations(conn, sensor_rows)
            finish_refresh(conn, sensor_refresh, "succeeded", len(sensor_records), len(sensor_rows))

            minute_records = fetch_records(
                MINUTE_COUNTS_DATASET,
                page_size,
                max_records,
                order_by="sensing_datetime desc",
            )
            archive_raw_records(MINUTE_COUNTS_DATASET, minute_records, data_dir)
            minute_rows = clean_minute_counts(
                minute_records,
                low_max,
                medium_max,
                city_timezone,
                lookback_minutes,
            )
            upsert_minute_counts(conn, minute_rows)
            finish_refresh(conn, minute_refresh, "succeeded", len(minute_records), len(minute_rows))
            conn.commit()
        except Exception as error:
            finish_refresh(conn, sensor_refresh, "failed", 0, 0, str(error))
            finish_refresh(conn, minute_refresh, "failed", 0, 0, str(error))
            conn.commit()
            raise


def main() -> None:
    ingest()
    print("Open-data ingestion completed successfully.")


if __name__ == "__main__":
    main()
