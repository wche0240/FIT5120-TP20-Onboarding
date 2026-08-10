# Production ETL Scheduling

## Purpose

The production API exposes `POST /api/v1/internal/ingest` so an external scheduler can refresh City of Melbourne Open Data without a paid Render Cron Job. The endpoint runs the existing sensor, minute-count and public-transport ETL against the Render PostgreSQL database.

## Recommended zero-cost scheduler: GitHub Actions

The repository includes `.github/workflows/refresh-open-data.yml`. It sends a protected `POST` request to the production API at minutes `07`, `22`, `37`, and `52` of each hour (every 15 minutes). The offset avoids the start-of-hour peak where scheduled GitHub Actions jobs are more likely to be delayed.

The workflow deliberately does **not** connect to PostgreSQL directly. It calls the deployed Render API, whose `DATABASE_URL` is the same database used by the website. This prevents a successful scheduler run from accidentally refreshing a different database to the one the public application reads.

Before enabling it:

1. In Render, add `ETL_TRIGGER_TOKEN` to the API Web Service environment variables. Use a long, randomly generated value.
2. In GitHub, open the repository's **Settings -> Secrets and variables -> Actions**, then add a repository secret with the same name: `ETL_TRIGGER_TOKEN` and exactly the same value.
3. Open the **Actions** tab, choose **Refresh Open Data**, and use **Run workflow** once to confirm a successful run.
4. If an older `PRODUCTION_DATABASE_URL` Actions secret was created for the previous workflow design, delete it after the first successful run. It is no longer used.

The workflow allows each request up to 120 seconds. This is important because a Render Free Web Service can take more than 50 seconds to start after inactivity. It retries ordinary connection and server errors, but it does not immediately retry an HTTP `429` response from City of Melbourne Open Data because that response means the provider's daily quota has been reached. It then prints `/api/v1/data-status` in the Actions log, providing evidence of the exact source timestamp the public website can see.

## Local development scheduler

The local scheduler only refreshes data while the `etl-scheduler` container is running. Starting only the frontend or only `db` and `api` will not run scheduled ingestion.

```powershell
docker-compose up -d db api etl-scheduler
docker-compose ps
docker-compose logs -f etl-scheduler
```

`etl-scheduler` runs once immediately, then repeats every `ETL_REFRESH_INTERVAL_MINUTES` (15 minutes by default). It has a restart policy, so Docker restarts it after an unexpected exit. If Docker Desktop itself has been restarted, run the first command again and confirm the scheduler is listed as `running` before relying on automatic updates.

## Provider request quota

City of Melbourne Open Data applies an anonymous request quota. The ingestion process uses 1,000 records per page so a normal minute-count refresh needs only about ten source requests instead of around one hundred. This keeps the scheduled workload well below the quota under normal conditions.

If the provider returns HTTP `429`, SensoryWay records the failed refresh in `data_refresh_log` and exposes its status and error through `/api/v1/data-status`. The local scheduler and GitHub Actions wait for the next scheduled run instead of retrying the quota error immediately. Restarting Docker, Render, or the frontend cannot clear a provider-side quota; the provider must reset it first.

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
2. Confirm the workflow log prints `{"status":"completed"}` and then a `data-status` response.
3. Check that `latest_data_at` in that response matches the most recent official minute-count data available from City of Melbourne Open Data.
4. Open `https://fit5120-tp20-onboarding.onrender.com/api/v1/data-status` directly if a second check is needed.
5. Inspect Render logs if the request fails. The ETL records refresh attempts in the database, so failures remain auditable.
