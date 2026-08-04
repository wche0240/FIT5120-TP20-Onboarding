# Epic 1 Public Transport Access Points

## Purpose

Epic 1 requires walking routes to integrate with public transport access points. SensoryWay imports public-transport stops in the Melbourne CBD, shows them as map markers, and reports the closest access point to the selected start and destination.

## Official data source

- Dataset: [Public Transport Lines and Stops](https://data.gov.au/data/dataset/public-transport-lines-and-stops)
- Publisher: Victorian Department of Transport and Planning
- Resource: `Public Transport Stops` GeoJSON
- Imported fields: `STOP_ID`, `STOP_NAME`, `MODE`, longitude and latitude

The ETL retains only the onboarding MVP boundary: longitude `144.94` to `144.99`, latitude `-37.825` to `-37.80`. It maps the source modes to the user-facing `bus`, `tram`, `train`, or `coach` categories. This keeps the project focused on Melbourne CBD while retaining traceability to the official source mode.

## Runbook

Run this after starting Docker Desktop and before the first ETL run:

```powershell
docker-compose run --rm migrate
docker-compose run --rm etl
```

The first command records `002_transit_access_points.sql` in the database migration history. The second command archives the source GeoJSON in `data/raw/`, filters valid CBD stops, upserts access points, and records its outcome in `data_refresh_log`.

## API and interface evidence

- `GET /api/v1/transit-access-points?limit=800` supplies the map layer.
- `GET /api/v1/transit-access-points?longitude=...&latitude=...&radius_metres=500&limit=2` returns nearby access points, ordered by great-circle distance.
- The Next.js route-planning screen displays the closest public-transport stop to both ends of a planned walk. It continues to provide walking routes when this optional map layer is temporarily unavailable.

## Acceptance check

For the Epic 1 demonstration, plan a route between two Melbourne CBD places and show:

1. coloured public-transport access-point markers on the map;
2. the nearest access point at the start and destination in the route result; and
3. the `transit_access_point` rows and successful `data_refresh_log` entry in PostgreSQL.
