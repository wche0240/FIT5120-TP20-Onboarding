"""Run the Open Data ETL immediately, then repeat it at a safe fixed interval."""

from __future__ import annotations

import os
import time

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


def run_forever(sleep=time.sleep) -> None:
    """Keep attempting refreshes so transient source failures do not stop the service."""
    interval_seconds = refresh_interval_seconds()
    print(f"Open-data scheduler started; refreshing every {interval_seconds // 60} minutes.")

    while True:
        try:
            ingest()
            print("Scheduled open-data ingestion completed successfully.")
        except OpenDataRateLimitError as error:
            # The provider's daily quota cannot be fixed by retrying straight away.
            # Leave the previous data intact and try again at the next scheduled interval.
            print(f"Scheduled open-data ingestion was rate-limited; waiting for the next interval: {error}")
        except Exception as error:
            # The ETL writes failed attempts to data_refresh_log before re-raising.
            print(f"Scheduled open-data ingestion failed; will retry: {error}")

        sleep(interval_seconds)


if __name__ == "__main__":
    run_forever()
