"""Run the Open Data ETL immediately, then repeat it at a safe fixed interval."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from app.etl import OpenDataRateLimitError, ingest


def refresh_interval_seconds() -> int:
    """Read a positive refresh interval from the environment."""
    try:
        interval_minutes = int(os.getenv("ETL_REFRESH_INTERVAL_MINUTES", "15"))
    except ValueError as error:
        raise ValueError("ETL_REFRESH_INTERVAL_MINUTES must be a whole number.") from error

    if interval_minutes < 1:
        raise ValueError("ETL_REFRESH_INTERVAL_MINUTES must be at least 1 minute.")

    return interval_minutes * 60


def rate_limit_delay_seconds(
    error: OpenDataRateLimitError, fallback_seconds: int, *, now: datetime | None = None
) -> int:
    """Wait until a provider-supplied quota reset when that information is available."""
    if not error.reset_time:
        return fallback_seconds

    try:
        reset_at = datetime.fromisoformat(error.reset_time.replace("Z", "+00:00"))
    except ValueError:
        return fallback_seconds

    if reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    seconds_until_reset = (reset_at - current_time.astimezone(timezone.utc)).total_seconds()
    if seconds_until_reset <= 0:
        return fallback_seconds

    # Add a small buffer because providers may need a moment to apply their reset.
    return max(fallback_seconds, int(seconds_until_reset) + 60)


def run_forever(sleep=time.sleep) -> None:
    """Keep attempting refreshes so transient source failures do not stop the service."""
    interval_seconds = refresh_interval_seconds()
    print(f"Open-data scheduler started; refreshing every {interval_seconds // 60} minutes.")

    while True:
        delay_seconds = interval_seconds
        try:
            ingest()
            print("Scheduled open-data ingestion completed successfully.")
        except OpenDataRateLimitError as error:
            delay_seconds = rate_limit_delay_seconds(error, interval_seconds)
            wait_minutes = (delay_seconds + 59) // 60
            print(
                "Scheduled open-data ingestion was rate-limited; "
                f"waiting about {wait_minutes} minute(s) before retrying: {error}"
            )
        except Exception as error:
            # The ETL writes failed attempts to data_refresh_log before re-raising.
            print(f"Scheduled open-data ingestion failed; will retry: {error}")

        sleep(delay_seconds)


if __name__ == "__main__":
    run_forever()
