# Epic 1 Data Freshness Decision

## Decision

For the onboarding MVP, `DATA_STALE_AFTER_MINUTES` remains **30 minutes**. Pedestrian crowd scores are shown only when the newest minute-count record is 30 minutes old or newer.

## Evidence

On 4 August 2026, the ETL successfully refreshed the official City of Melbourne sensor-location and past-hour minute-count datasets. The newest available source reading was 41 minutes old when the API was checked. The route API successfully returned three OpenRouteService walking options, but correctly returned `degraded` and no crowd recommendation because the source data exceeded the 30-minute limit.

This is treated as a data-latency limitation of the public source, not as a live-data failure in SensoryWay.

## Rationale

- A 41-minute-old pedestrian count can be materially different from current crowd conditions.
- The product must not label delayed Open Data as current or real-time.
- Returning route geometry with a visible warning still supports route planning while meeting Epic 1 US 1.2's requirement to warn users when crowd data is unavailable or outdated.

## User-facing Behaviour

| Data age or coverage | API behaviour | UI requirement |
| --- | --- | --- |
| 30 minutes or newer and route has nearby sensors | Return crowd score and eligible recommendation | Show the crowd indicator and recommended route. |
| Older than 30 minutes | Return physical walking routes with `degraded` status | Show that crowd data is outdated; do not recommend a quieter route. |
| No sensor coverage or no readings | Return physical walking routes with `unavailable` status | Explain that crowd information is unavailable; do not infer a low crowd level. |
| No route meets the user's selected threshold | Return scored alternatives without a recommendation | Warn that no currently monitored route meets the threshold. |

## Review Trigger

Before the Epic 1 release, review the timestamps captured in `data_refresh_log` across multiple ETL runs. Any increase to the 30-minute limit requires a documented product decision, evidence of source refresh behaviour, and mentor approval in the PGP.

## PGP Evidence Text

> SensoryWay uses City of Melbourne minute-level pedestrian Open Data and applies a 30-minute freshness threshold. During integration testing on 4 August 2026, the official source's latest record was 41 minutes old after a successful ETL refresh. The system therefore returned route options but withheld the crowd recommendation and displayed an outdated-data warning. This avoids presenting delayed Open Data as real-time information.

## LeanKit Updates

- Move **Server-side OpenRouteService route integration** to **Done**. Evidence: commit `4f1d293`, `POST /api/v1/routes`, and successful live test returning three walking routes.
- Move **Data freshness warning for outdated pedestrian data** to **Done**. Evidence: `GET /api/v1/data-status` and `POST /api/v1/routes` returned `degraded` when the latest official reading was 41 minutes old.
- Keep **Review Open Data freshness threshold before Epic 1 release** in **To Do**. It is a governance review, not permission to relax the current 30-minute policy.
