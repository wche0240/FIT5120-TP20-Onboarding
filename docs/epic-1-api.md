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
| `POST /api/v1/route-score` | Scores supplied route coordinates against nearby fresh sensor readings. |

`DATA_STALE_AFTER_MINUTES` defaults to 30 minutes. The frontend must use `data-status` before presenting crowd levels as current information.

## Next API Work

The route-score endpoint uses an 80-metre configurable sensor radius and the busiest matched sensor as a conservative crowd score. It returns no score if data is stale or the route has no sensor coverage.

Route generation from a user's start and destination is the next step. It will call an external routing provider and send each returned route to this endpoint.
