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

## Epic 1 Data Layer

The first build stores City of Melbourne sensor locations and minute-level pedestrian counts in PostgreSQL. The ETL process archives the source response, removes duplicate composite keys, validates required fields, converts timestamps to the Melbourne timezone, and records every refresh attempt.

1. Start Docker Desktop.
2. In PowerShell, copy `.env.example` to `.env` and choose a local PostgreSQL password.
3. Start the database and API with `docker-compose up -d db api`.
4. Run the data ingestion with `docker-compose run --rm etl`.
5. Run the data tests with `docker-compose run --rm etl pytest`.

The API documentation is available at `http://localhost:8000/docs` after the API container starts.

Set `ORS_API_KEY` in the local `.env` before using `POST /api/v1/routes`. Do not commit the key.

The initial Low/Medium/High thresholds are configuration values only. They must be replaced with a documented profiling decision before the Epic 1 release.
