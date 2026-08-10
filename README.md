# SensoryWay

FIT5120 TP20 onboarding project - a sensory-aware route planning web app for Melbourne CBD.

## Project Goal

SensoryWay helps sensory-sensitive commuters compare Melbourne CBD walking routes using pedestrian crowd information. Epic 2 features, including quiet spaces and short-term forecasts, remain future work.

## Planned Technology

- Frontend: Next.js
- Backend API: FastAPI and Python
- Database: PostgreSQL
- Data processing: Python and pandas
- Route provider: OpenRouteService, called only by the backend
- Map display: Google Maps JavaScript API, called only by the browser

## Repository Structure

```text
frontend/        Next.js web application
backend/         FastAPI application and data services
database/        SQL schema, migrations, and seed scripts
docs/            Product, architecture, and testing documentation
data/raw/        Downloaded source data (not committed)
data/processed/  Cleaned or generated data (not committed)
```

## Status

Project setup in progress.

## Production Deployment

SensoryWay is deployed as separate services: the Next.js frontend on Vercel, and the FastAPI API plus PostgreSQL database on Render. A protected API endpoint allows a free external scheduler to run the Open Data ETL every 15 minutes. Use `backend/Dockerfile.production` with the repository root as the Docker build context. The API health check is `/api/v1/health`; run `python -m scripts.migrate` before starting the API against a new cloud database.

Keep all production credentials in the Vercel or Render environment-variable settings. Do not commit `.env`, `.env.local`, Google Maps keys, ORS keys, or database URLs.

For the free production ETL schedule, see `docs/production-etl-scheduling.md`. The scheduler calls `POST /api/v1/internal/ingest` with an `X-ETL-Token` header. The endpoint is unavailable until `ETL_TRIGGER_TOKEN` is configured in Render.

## Epic 1 Data Layer

The first build stores City of Melbourne sensor locations and minute-level pedestrian counts in PostgreSQL. The ETL process archives the source response, removes duplicate composite keys, validates required fields, converts timestamps to the Melbourne timezone, and records every refresh attempt.

1. Start Docker Desktop.
2. In PowerShell, copy `.env.example` to `.env` and choose a local PostgreSQL password.
3. Start the database, API and recurring ETL with `docker-compose up -d db api etl-scheduler`.
4. Apply database migrations with `docker-compose run --rm migrate`.
5. The scheduler immediately ingests Open Data and repeats the refresh every 15 minutes. Use `docker-compose logs -f etl-scheduler` to inspect it.
6. Run a one-off ingestion when needed with `docker-compose run --rm etl`.
7. Run the data tests with `docker-compose run --rm etl pytest`.

The API documentation is available at `http://localhost:8000/docs` after the API container starts.

Set `ORS_API_KEY` in the local `.env` before using `POST /api/v1/routes`. Do not commit the key.

Pedestrian data older than 45 minutes is intentionally treated as outdated. SensoryWay still shows physical route options but withholds crowd recommendations; see `docs/epic-1-data-freshness-decision.md` for the recorded decision and evidence.

`ETL_REFRESH_INTERVAL_MINUTES` defaults to 15. This keeps the local database refreshed while correctly preserving the 45-minute freshness warning whenever the official source itself is delayed.

Crowd thresholds are Low `0-10`, Medium `11-30`, and High `31+` pedestrians per minute. They were profiled against the onboarding minute-count snapshot; see `docs/epic-1-crowd-threshold-decision.md` for the evidence, limitations, and required PGP/LeanKit updates.

## CBD Destination Search

Users can enter a Melbourne CBD address, street or landmark for either end of a walk. Select the search icon or press Enter in a field, choose a returned address, then select `Find routes`. The backend rejects results outside the onboarding MVP boundary. The default low-volume geocoder is configurable through `GEOCODER_SEARCH_URL`; see `docs/epic-1-destination-search.md` for privacy, rate-limit and acceptance-test guidance.

## Public Transport Access Points

The ETL also imports official Victorian public-transport stops within the Melbourne CBD, while the frontend shows the nearby stop at each end of a planned walk. Run `docker-compose run --rm migrate` before the ETL to create the `transit_access_point` table. See `docs/epic-1-public-transport-integration.md` for the data source, boundary and acceptance evidence.

## Frontend

The Next.js interface follows the project's Figma map-navigation concept: a responsive full-screen Google map of Melbourne, a route search bar, crowd-threshold controls, and a desktop panel or mobile bottom sheet for route outcomes.

1. Keep the FastAPI service running on `http://localhost:8000`.
2. In a separate terminal, run `cd frontend`, then `npm.cmd install` and `npm.cmd run dev`.
3. Open `http://localhost:3000`. The development script is intentionally fixed to this port so it fails clearly when another frontend server is already running, rather than silently switching ports and breaking the restricted Google Maps key. Stop the old frontend terminal with `Ctrl + C`, then run the command again.

The frontend calls the local API through `NEXT_PUBLIC_API_BASE_URL`, which defaults to `http://localhost:8000`. It also needs `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` in `frontend/.env.local` to show the Google map. Copy `frontend/.env.example` as a starting point and do not commit the key. See `docs/google-maps-setup.md` for the required Google Cloud configuration.
