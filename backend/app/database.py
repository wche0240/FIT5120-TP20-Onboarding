from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


def get_db() -> Generator[psycopg.Connection[Any], None, None]:
    """Yield a database connection without exposing connection errors to users."""
    try:
        with psycopg.connect(get_database_url(), row_factory=dict_row) as connection:
            yield connection
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error
