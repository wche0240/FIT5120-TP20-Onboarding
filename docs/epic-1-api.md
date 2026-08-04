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
| `POST /api/v1/routes` | Creates and scores up to three walking route options. |

`DATA_STALE_AFTER_MINUTES` defaults to 30 minutes. The frontend must use `data-status` before presenting crowd levels as current information.

## Route Scoring and Recommendations

The route-score endpoint uses an 80-metre configurable sensor radius and the busiest matched sensor as a conservative crowd score. It returns no score if data is stale or the route has no sensor coverage.

`POST /api/v1/routes` accepts a start point, a Melbourne CBD destination, and the user's maximum acceptable crowd level (`low`, `medium`, or `high`).

```json
{
  "start": {"longitude": 144.9631, "latitude": -37.8136},
  "destination": {"longitude": 144.9700, "latitude": -37.8100},
  "max_crowd_level": "medium"
}
```

The backend calls OpenRouteService with the server-side `ORS_API_KEY`, requests up to three walking alternatives, scores each route against active pedestrian sensors, and returns the recommended option. The key is never returned to the browser.

If current data is stale, unavailable, or no monitored option meets the selected threshold, the API still returns the physical walking routes but returns no recommendation and includes a clear warning. This supports Epic 1 US 1.2 and US 1.3 without implying that outdated data is current.
