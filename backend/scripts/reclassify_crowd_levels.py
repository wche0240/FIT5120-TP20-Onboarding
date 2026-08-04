from __future__ import annotations

import os

import psycopg


def main() -> None:
    """Apply the configured crowd bands to all stored minute-count rows."""
    low_max = int(os.getenv("CROWD_LOW_MAX", "10"))
    medium_max = int(os.getenv("CROWD_MEDIUM_MAX", "30"))
    if low_max < 0 or medium_max < low_max:
        raise ValueError("Crowd thresholds are invalid")

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pedestrian_minute_count
                SET crowd_level = CASE
                    WHEN total_count <= %s THEN 'low'
                    WHEN total_count <= %s THEN 'medium'
                    ELSE 'high'
                END
                WHERE crowd_level IS DISTINCT FROM CASE
                    WHEN total_count <= %s THEN 'low'
                    WHEN total_count <= %s THEN 'medium'
                    ELSE 'high'
                END
                """,
                (low_max, medium_max, low_max, medium_max),
            )
            print(f"Reclassified {cursor.rowcount} stored pedestrian readings.")
        connection.commit()


if __name__ == "__main__":
    main()
