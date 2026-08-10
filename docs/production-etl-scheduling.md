# Production ETL Scheduling

## Purpose

The production API exposes `POST /api/v1/internal/ingest` so an external scheduler can refresh City of Melbourne Open Data without a paid Render Cron Job. The endpoint runs the existing sensor, minute-count and public-transport ETL against the Render PostgreSQL database.

## Recommended zero-cost scheduler: GitHub Actions

The repository includes `.github/workflows/refresh-open-data.yml`. It sends a protected `POST` request to the production API at minutes `07`, `22`, `37`, and `52` of each hour (every 15 minutes). The offset avoids the start-of-hour peak where scheduled GitHub Actions jobs are more likely to be delayed.

Before enabling it:

1. In Render, add `ETL_TRIGGER_TOKEN` to the API Web Service environment variables. Use a long, randomly generated value.
2. In GitHub, open the repository's **Settings -> Secrets and variables -> Actions**, then add a repository secret with the same name: `ETL_TRIGGER_TOKEN` and exactly the same value.
3. Open the **Actions** tab, choose **Refresh Open Data**, and use **Run workflow** once to confirm a successful run.

The workflow uses a 240-second request limit and retries transient network failures. This is important because a Render Free Web Service can take more than 50 seconds to start after inactivity.

## Cost and reliability notes

- Standard GitHub-hosted Actions runners are free for public repositories. If this repository stays private, GitHub Free includes 2,000 Actions minutes per month. A 15-minute schedule may exceed that private-repository allowance, so do not rely on it as a permanently free private-repository scheduler.
- Scheduled GitHub Actions can occasionally be delayed, especially at the start of an hour. This build does not claim real-time or guaranteed-on-the-minute updates; it records the actual latest source timestamp and labels data as stale when it is older than the configured freshness window.
- Public repositories can have scheduled workflows disabled after 60 days without repository activity. A new commit or manually enabling the workflow restores it.

## Why not cron-job.org for this deployment?

cron-job.org supports POST requests and custom headers, but its free service closes requests after 30 seconds. That is shorter than a possible Render Free cold start, so it is unsuitable as the reliable scheduler for this hosted build.

## Security

Set a long random `ETL_TRIGGER_TOKEN` in the Render API service environment variables. The GitHub Actions scheduler must send the same value in the `X-ETL-Token` request header. Do not put this value in frontend variables, screenshots, source code, or public documentation.

The endpoint returns `503` when the token has not been configured and `401` when the supplied token does not match.

## Verification

1. Trigger the workflow once manually from GitHub.
2. Confirm a successful `200` response in the workflow logs.
3. Open `https://fit5120-tp20-onboarding.onrender.com/api/v1/data-status` and check that `latest_data_at` is current.
4. Inspect Render logs if the request fails. The ETL records refresh attempts in the database, so failures remain auditable.
