from __future__ import annotations

import os

from scripts.migrate import main as migrate


def main() -> None:
    """Apply outstanding migrations, then replace this process with the API server."""
    migrate()

    port = os.getenv("PORT", "8000")
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()
