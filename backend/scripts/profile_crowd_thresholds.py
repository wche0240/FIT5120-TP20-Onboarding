from __future__ import annotations

import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    """Print a reproducible summary for reviewing the configured crowd thresholds."""
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS readings,
                    MIN(total_count) AS minimum_count,
                    MAX(total_count) AS maximum_count,
                    ROUND(AVG(total_count), 1) AS mean_count,
                    percentile_cont(ARRAY[0.25, 0.5, 0.75, 0.85, 0.9, 0.95])
                        WITHIN GROUP (ORDER BY total_count) AS percentiles
                FROM pedestrian_minute_count
                """
            )
            all_readings: dict[str, Any] = cursor.fetchone()

            cursor.execute(
                """
                WITH labelled AS (
                    SELECT CASE
                        WHEN total_count <= %s THEN 'low'
                        WHEN total_count <= %s THEN 'medium'
                        ELSE 'high'
                    END AS crowd_level
                    FROM pedestrian_minute_count
                )
                SELECT crowd_level, COUNT(*) AS readings,
                    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS percentage
                FROM labelled
                GROUP BY crowd_level
                ORDER BY crowd_level
                """,
                (int(os.getenv("CROWD_LOW_MAX", "10")), int(os.getenv("CROWD_MEDIUM_MAX", "30"))),
            )
            category_distribution = cursor.fetchall()

    print(
        json.dumps(
            {"all_minute_readings": all_readings, "configured_category_distribution": category_distribution},
            default=str,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
