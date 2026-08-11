# Epic 1 Data Freshness Decision

## Decision

For the onboarding MVP, `DATA_STALE_AFTER_MINUTES` is **60 minutes**. Pedestrian crowd scores are shown only when the newest minute-count record is 60 minutes old or newer. Eligible data is labelled `Recent data`; the interface does not render a `Crowd data delayed` status chip.

## Evidence

City of Melbourne publishes the past-hour minute-count dataset in 15-minute batches, but the timestamp of its newest observation can lag behind the successful ETL completion time. On 11 August 2026, a successful Render Cron run completed at 14:30 UTC while the newest official reading was 13:55 UTC (35 minutes old). A 60-minute boundary accommodates this observed batch-processing latency without treating arbitrarily old data as current.

This is a public-source latency limitation, not an ETL failure: `data_refresh_log` recorded the run as `succeeded`.

## Rationale

- The official source can be delayed by more than 30 minutes even after a successful refresh.
- A 60-minute boundary allows the product to show recent official observations across several scheduled source batches.
- The interface labels eligible scores as recent data, not live or real-time data.
- When the source is older than 60 minutes, crowd recommendations are withheld rather than inferred from outdated observations.

## User-facing behaviour

| Data age or coverage | API behaviour | UI behaviour |
| --- | --- | --- |
| 60 minutes or newer and route has nearby sensors | Return crowd score and eligible recommendation | Show the `Recent data` chip and the recommended route. |
| Older than 60 minutes | Return physical walking routes with `degraded` status | Do not show the `Crowd data delayed` chip; withhold crowd recommendations and show the existing general route warning. |
| No sensor coverage or no readings | Return physical walking routes with `unavailable` status | Explain that crowd information is unavailable; do not infer a low crowd level. |
| No route meets the user's selected threshold | Return scored alternatives without a recommendation | Warn that no currently monitored route meets the threshold. |

## Review trigger

Before the Epic 1 release, review source timestamps and `data_refresh_log` across multiple Cron runs. Record whether the 60-minute boundary continues to match observed source latency and obtain any required mentor approval in the PGP.

## PGP evidence text

> SensoryWay uses City of Melbourne minute-level pedestrian Open Data and applies a 60-minute freshness threshold. The source is published in 15-minute batches but can deliver observations with additional processing delay. Eligible readings are labelled as recent data, not real-time data. Data older than 60 minutes withholds crowd recommendations without rendering a separate crowd-delay status chip.

## LeanKit updates

- Move **Server-side OpenRouteService route integration** to **Done**. Evidence: commit `4f1d293`, `POST /api/v1/routes`, and successful live test returning three walking routes.
- Move **Data freshness warning for outdated pedestrian data** to **Done**. Evidence: `GET /api/v1/data-status` and `POST /api/v1/routes` return `degraded` when the latest official reading is older than 60 minutes.
- Move **Review Open Data freshness threshold before Epic 1 release** to **In Progress**. Attach this decision record and obtain any required mentor approval before moving it to Done.
