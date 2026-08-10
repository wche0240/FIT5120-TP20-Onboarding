# Production Open-Data Refresh

The production API is hosted on Render and the scheduled ETL is hosted on GitHub Actions. This split keeps the public API available while avoiding transient TLS failures between Render and the City of Melbourne Open Data platform.

## Required GitHub Secret

Create the repository Actions secret `PRODUCTION_DATABASE_URL` with the **External Database URL** from the Render PostgreSQL service. The value is secret and must never be committed, pasted into issues, or exposed in screenshots.

The `Refresh Open Data` workflow runs at minutes 7, 22, 37, and 52 of every hour. Each run safely applies pending SQL migrations and then imports the City of Melbourne sensor-location and pedestrian-count data into the production database.

Run it manually from **GitHub > Actions > Refresh Open Data > Run workflow** after changing ETL logic or when a refresh is required immediately.
