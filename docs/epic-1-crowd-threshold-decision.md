# Epic 1 Crowd-Threshold Decision

## Decision

SensoryWay classifies the busiest valid sensor within 80 metres of a walking route as:

| Level | Minute pedestrian count | Route recommendation meaning |
| --- | --- | --- |
| Low | `0-10` | Meets the strictest crowd preference. |
| Medium | `11-30` | Meets a medium or high crowd preference. |
| High | `31+` | Shown only when the user permits high crowd levels. |

The route score is the **maximum**, rather than the average, of the matched sensor readings. This is conservative: a route containing one busy monitored section must not be described as low crowd merely because other nearby sections are quiet.

## Evidence

On 5 August 2026, the local PostgreSQL snapshot contained 7,400 valid City of Melbourne minute-count readings. Its percentiles were:

| Statistic | Pedestrians per minute |
| --- | ---: |
| P25 | 2 |
| P50 | 4 |
| P75 | 10 |
| P85 | 15 |
| P90 | 20 |
| P95 | 29 |

The selected boundaries use the P75 value for the end of Low and round the P95 boundary to `30` for the end of Medium. Reclassifying this snapshot produced 77.3% Low, 18.1% Medium and 4.5% High readings. An earlier 5 August snapshot had a P95 of 31, supporting `30` as a stable, simple boundary. The former `0-50` / `51-150` configuration classified 98.0% of readings as Low, so it was not sufficiently discriminating.

## Reproducibility

After the ETL has loaded a fresh snapshot, review the distribution with:

```powershell
docker-compose run --rm etl python -m scripts.profile_crowd_thresholds
```

The profiler reports the reading count, range, percentiles and distribution under the current configuration. If a threshold changes, reclassify already stored rows with:

```powershell
docker-compose run --rm etl python -m scripts.reclassify_crowd_levels
```

Thresholds must be reviewed after a materially larger historical dataset is introduced, or if stakeholder testing identifies that the labels do not match sensory-sensitive users' experience.

## Delivery Governance

Before Epic 1 acceptance:

1. Add this decision and its evidence link to the PGP's technical/data decision record.
2. Move the LeanKit card **Profile and approve crowd thresholds** to Done, attaching this document and the profiler output.
3. Record feedback from representative neurodivergent users or the closest available proxies; a mentor must approve any revised thresholds.

This is a transparent heuristic for the onboarding MVP. It does not diagnose sensory experience or claim to measure every source of sensory load.
