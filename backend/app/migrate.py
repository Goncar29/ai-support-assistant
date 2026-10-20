"""Create the database schema: `python -m app.migrate`.

Run it once per database (and again after schema changes). The web app never
creates tables on startup, so a cold start does not pay for DDL.
"""
import sys

from dotenv import load_dotenv

from app.config import Settings
from app.infrastructure.postgres import PostgresRateLimiter, PostgresTicketRepository


def main() -> int:
    load_dotenv()  # local runs read backend/.env; real environment variables win
    settings = Settings.from_env()
    if not settings.database_url:
        print("DATABASE_URL is not set; nothing to migrate.", file=sys.stderr)
        return 1
    PostgresTicketRepository(settings.database_url).create_schema()
    PostgresRateLimiter(
        settings.database_url, settings.rate_limit_requests, settings.rate_limit_window_seconds
    ).create_schema()
    print("Schema is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
