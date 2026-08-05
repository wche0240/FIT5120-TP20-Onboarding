# Epic 1 Data Freshness Decision

## Decision

For the onboarding MVP, `DATA_STALE_AFTER_MINUTES` is **45 minutes**. Pedestrian crowd scores are shown only when the newest minute-count record is 45 minutes old or newer. The interface labels this as recent data, not real-time data.

## Evidence

On 5 August 2026, the ETL successfully refreshed the official City of Melbourne sensor-location and past-hour minute-count datasets. The newest available source reading was 34 minutes old when the API was checked. This exceeded the former 30-minute limit despite a successful ETL run, so the project decision is to use a documented 45-minute window for this onboarding MVP.

This is treated as a data-latency limitation of the public source, not as a live-data failure in SensoryWay.

## Rationale

- The official source can be delayed by more than 30 minutes even after a successful refresh.
- A 45-minute threshold allows the product to show recent official observations while still withholding data that is materially outdated.
- The product labels eligible scores as recent data, not current or real-time data.
- Returning route geometry with a visible warning still supports route planning while meeting Epic 1 US 1.2's requirement to warn users when crowd data is unavailable or outdated.

## User-facing Behaviour

| Data age or coverage | API behaviour | UI requirement |
| --- | --- | --- |
| 45 minutes or newer and route has nearby sensors | Return crowd score and eligible recommendation | Show the crowd indicator as recent data and the recommended route. |
| Older than 45 minutes | Return physical walking routes with `degraded` status | Show that crowd data is outdated; do not recommend a quieter route. |
| No sensor coverage or no readings | Return physical walking routes with `unavailable` status | Explain that crowd information is unavailable; do not infer a low crowd level. |
| No route meets the user's selected threshold | Return scored alternatives without a recommendation | Warn that no currently monitored route meets the threshold. |

## Review Trigger

Before the Epic 1 release, review the timestamps captured in `data_refresh_log` across multiple ETL runs. Record this 45-minute product decision, the source-latency evidence and any required mentor approval in the PGP.

## PGP Evidence Text

> SensoryWay uses City of Melbourne minute-level pedestrian Open Data and applies a 45-minute freshness threshold. During integration testing on 5 August 2026, the latest official record was 34 minutes old after a successful ETL refresh. The interface describes eligible readings as recent data, not real-time data. Data older than 45 minutes continues to withhold crowd recommendations and display an outdated-data warning.

## LeanKit Updates

- Move **Server-side OpenRouteService route integration** to **Done**. Evidence: commit `4f1d293`, `POST /api/v1/routes`, and successful live test returning three walking routes.
- Move **Data freshness warning for outdated pedestrian data** to **Done**. Evidence: `GET /api/v1/data-status` and `POST /api/v1/routes` returned `degraded` when the latest official reading was 41 minutes old.
- Move **Review Open Data freshness threshold before Epic 1 release** to **In Progress**. Attach this decision record and obtain any required mentor approval before moving it to Done.
