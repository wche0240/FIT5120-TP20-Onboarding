# Production ETL Scheduling

## Purpose

The production API exposes `POST /api/v1/internal/ingest` so an external scheduler can refresh City of Melbourne Open Data without a paid Render Cron Job. The endpoint runs the existing sensor, minute-count and public-transport ETL against the Render PostgreSQL database.

## Security

Set a long random `ETL_TRIGGER_TOKEN` in the Render API service environment variables. The scheduler must send the same value in the `X-ETL-Token` request header. Do not put this value in GitHub, frontend variables, screenshots, or public documentation.

The endpoint returns `503` when the token has not been configured and `401` when the supplied token does not match.

## External Scheduler Configuration

Create one HTTPS job with the following settings:

- Method: `POST`
- URL: `https://fit5120-tp20-onboarding.onrender.com/api/v1/internal/ingest`
- Schedule: every 15 minutes
- Header: `X-ETL-Token: <the Render ETL_TRIGGER_TOKEN value>`
- Timeout: at least 120 seconds

The Render free web service can spin down after inactivity. The first scheduled request may therefore take more than 50 seconds while the service wakes up. A successful response is `200` with `{"status":"completed"}`.

## Verification

1. Trigger the scheduler once manually.
2. Confirm a successful `200` response in the scheduler history.
3. Open `https://fit5120-tp20-onboarding.onrender.com/api/v1/data-status` and check that `latest_data_at` is current.
4. Inspect Render logs if the request fails. The ETL records refresh attempts in the database, so failures remain auditable.
