from __future__ import annotations

import os
from pathlib import Path

import psycopg


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    migrations_dir = Path(os.getenv("MIGRATIONS_DIR", "/migrations"))
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        raise RuntimeError(f"No SQL migration files found in {migrations_dir}")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migration (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            for migration_file in migration_files:
                cursor.execute("SELECT 1 FROM schema_migration WHERE version = %s", (migration_file.name,))
                if cursor.fetchone():
                    continue

                cursor.execute(migration_file.read_text(encoding="utf-8"))
                cursor.execute("INSERT INTO schema_migration (version) VALUES (%s)", (migration_file.name,))
                print(f"Applied migration: {migration_file.name}")

        connection.commit()


if __name__ == "__main__":
    main()
