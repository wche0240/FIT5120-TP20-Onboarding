# Production Open-Data Refresh

This page has been superseded by [production-etl-scheduling.md](production-etl-scheduling.md).

The production design is now a Render Web Service for the API plus a separate Render Cron Job for the high-frequency `minute` ETL scope. Do not configure `PRODUCTION_DATABASE_URL` in GitHub Actions: the Cron Job receives Render's internal `DATABASE_URL` directly, so the job and the public API always use the same PostgreSQL database.
