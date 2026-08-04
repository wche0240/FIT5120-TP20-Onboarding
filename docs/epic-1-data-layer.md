# Epic 1 Data Layer

## Purpose

This data layer supports Epic 1 route crowd indicators. It stores City of Melbourne pedestrian sensor locations and the latest available minute-level pedestrian counts in PostgreSQL.

## Sources

- Sensor locations: `pedestrian-counting-system-sensor-locations`
- Minute counts: `pedestrian-counting-system-past-hour-counts-per-minute`
- API catalogue: `https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/{dataset}/records`

The public API does not permit unrestricted deep pagination. The ETL therefore requests the latest 10,000 minute records in descending timestamp order, verifies that they cover at least 60 minutes, and stores only the latest 60-minute window.

## Local Runbook

1. Start Docker Desktop.
2. Copy `.env.example` to `.env` and set a local PostgreSQL password.
3. Start the database: `docker-compose up -d db`.
4. Run tests: `docker-compose run --rm etl pytest`.
5. Ingest Open Data: `docker-compose run --rm etl`.
6. Inspect container status: `docker-compose ps`.

## Tables

| Table | Purpose | Key |
| --- | --- | --- |
| `sensor_location` | Sensor metadata, coordinates and status | `location_id` |
| `pedestrian_minute_count` | Cleaned minute-level pedestrian readings | `location_id`, `sensing_datetime` |
| `data_refresh_log` | Audit trail for each ingestion attempt | `refresh_id` |

## Data Quality Rules

- Sensor locations must have an ID, name, latitude and longitude.
- Duplicate sensors retain the latest source row.
- Minute counts require a sensor ID and parseable timestamp.
- Duplicate minute records retain the latest record for each `(location_id, sensing_datetime)` key.
- Negative counts and invalid timestamps are discarded.
- Missing directions are treated as zero only when a total is unavailable.
- The process never interpolates current readings. Missing or stale data must be surfaced as unavailable by the future API and UI.
- Every source response is archived under `data/raw/`, which is ignored by Git.

## Crowd Levels

The current configuration uses Low `0-50`, Medium `51-150`, and High `151+` pedestrians per minute. These values are provisional. Before the Epic 1 release, profile the historical distributions and record the approved threshold method in the PGP and LeanKit evidence.

## Current Limitations

- The source only records a minute when at least one pedestrian is detected, so no row does not automatically mean a confirmed zero count.
- The source is refreshed periodically rather than being a direct sensor stream.
- The 30-minute freshness decision and its observed source latency are documented in `docs/epic-1-data-freshness-decision.md`.
- Transport access points remain future Epic 1 work.
