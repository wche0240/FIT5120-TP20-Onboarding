# Epic 1 API

## Start the Service

1. Start Docker Desktop.
2. Start PostgreSQL and FastAPI: `docker-compose up -d db api`.
3. Open `http://localhost:8000/docs`.

## Current Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/health` | Confirms the API can reach PostgreSQL. |
| `GET /api/v1/data-status` | Reports whether the newest minute-count data is available, stale, or unavailable. |
| `GET /api/v1/sensors` | Returns map-ready sensor locations and each sensor's latest crowd reading. |

`DATA_STALE_AFTER_MINUTES` defaults to 30 minutes. The frontend must use `data-status` before presenting crowd levels as current information.

## Next API Work

Route generation, sensor-to-route matching, and route crowd scoring are intentionally deferred until these read-only data endpoints are tested against the running database.
