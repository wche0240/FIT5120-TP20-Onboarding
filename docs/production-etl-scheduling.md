# Production ETL Scheduling

## Target design

Use one Render PostgreSQL database, one Render Web Service for the FastAPI API, and one paid Render Cron Job for ingestion. The Cron Job opens Render's internal `DATABASE_URL`, writes to the same database as the API, then exits. It does not call the public API and it does not need `ETL_TRIGGER_TOKEN`.

| Scope | What it refreshes | When it runs |
| --- | --- | --- |
| `minute` | Pedestrian counts from the official past-hour feed | Every 15 minutes |
| reference refresh within `minute` | Sensor locations and public-transport stops | First run and then at most once every 24 hours |
| `reference` | Sensor locations and public-transport stops only | Manual recovery only |
| `all` | Both reference data and minute counts | Manual bootstrap/recovery only |

The official pedestrian feed itself is refreshed roughly every 15 minutes. A 15-minute Cron schedule keeps SensoryWay close to the source; it cannot make the source update more frequently than that.

## Required Render configuration

### Web Service

Keep the API service configured with:

- Build context: repository root
- Dockerfile path: `backend/Dockerfile.production`
- Health check: `/api/v1/health`

Its default command runs `python -m scripts.start_api`, which applies SQL migrations before starting FastAPI. The `003_refresh_log_rate_limited.sql` migration extends the refresh log so rate-limited attempts are visible through `/api/v1/data-status`.

Set these API environment variables:

```text
DATABASE_URL=<Render Postgres internal URL>
CORS_ORIGINS=<exact deployed frontend origin>
DATA_STALE_AFTER_MINUTES=45
ETL_TRIGGER_TOKEN=<long random secret, only for manual API recovery>
```

The frontend must be rebuilt with `NEXT_PUBLIC_API_BASE_URL` equal to the deployed API origin. A browser fallback to `localhost` is only suitable for local development.

### Cron Job

Create one Docker-based Render Cron Job from the same repository:

```text
Build context:      repository root
Dockerfile path:    backend/Dockerfile.production
Command:            python -m scripts.ingest_open_data --scope minute
Schedule (UTC):     */15 * * * *
```

Give the Cron Job the following environment variables. Cron Jobs do not automatically inherit a Web Service's variables, so use a Render Environment Group for shared non-secret settings where possible.

```text
DATABASE_URL=<the same Render Postgres internal URL>
CITY_TIMEZONE=Australia/Melbourne
CROWD_LOW_MAX=10
CROWD_MEDIUM_MAX=30
MINUTE_LOOKBACK_MINUTES=60
MINUTE_RETENTION_MINUTES=90
REFERENCE_REFRESH_INTERVAL_HOURS=24
ARCHIVE_RAW_RECORDS=false
CITY_OPEN_DATA_API_KEY=<optional Huwise/OpenDataSoft API key>
```

`ARCHIVE_RAW_RECORDS=false` is intentional: Render Cron Job filesystems are ephemeral, while the cleaned records and refresh audit log are stored in PostgreSQL. Add `CITY_OPEN_DATA_API_KEY` only if the City of Melbourne data platform has issued one; never expose it in the frontend or commit it to the repository.

`.github/workflows/refresh-open-data.yml` has deliberately been changed to a manual-only recovery workflow. Never restore its 15-minute schedule while the Render Cron Job is active, because the duplicate source traffic increases the chance of HTTP 429 rate limits.

## ETL behaviour and failure handling

The ETL now uses the City of Melbourne JSON export endpoint rather than requesting many oversized records pages. The records API accepts at most 100 rows per ungrouped page; a previous 1,000-row page configuration could be rejected or require repeated requests. Each normal minute job fetches one bounded source snapshot, retains only the newest 60 minutes of source readings, upserts by `(location_id, sensing_datetime)`, and removes local rows older than 90 minutes.

A PostgreSQL advisory lock allows only one ingestion run at a time. An overlapping invocation returns a conflict rather than writing concurrently. Every source attempt first records `running`, then finishes as `succeeded`, `failed`, or `rate_limited`; those details appear in `/api/v1/data-status`.

- HTTP 429: no immediate retry; wait for the next scheduled Cron run or add an approved provider API key.
- Source or database error: the job exits non-zero and the failed refresh log stays in PostgreSQL for diagnosis.
- Stale data: route scoring excludes individual sensor readings older than `DATA_STALE_AFTER_MINUTES`; it does not let an old high count influence a route merely because another sensor is fresh.

## First-run verification

1. Deploy the Web Service and wait for `/api/v1/health` to return `{"status":"ok","database":"connected"}`.
2. Create the Cron Job with the command above and use Render's **Trigger Run** control once.
3. In the Cron log, confirm `Open-data minute ingestion completed successfully.`
4. Open `/api/v1/data-status`; it should show `last_refresh_status: "succeeded"` and a recent `latest_data_at`.
5. Confirm the frontend calls the deployed API in the browser network panel, rather than `http://localhost:8000`.

For a manual complete recovery refresh, call the protected API with `POST /api/v1/internal/ingest?scope=all` and the `X-ETL-Token` header. Do not schedule the `all` scope every 15 minutes.
