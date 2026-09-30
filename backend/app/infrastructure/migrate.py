import logging
from pathlib import Path

import psycopg

from app.infrastructure.config import settings


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


def run() -> None:
    with psycopg.connect(settings.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            connection.commit()

        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (migration.name,))
                if cursor.fetchone():
                    continue
                logger.info("Applying migration %s", migration.name)
                try:
                    cursor.execute(migration.read_text(encoding="utf-8"))
                    cursor.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (migration.name,))
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise


if __name__ == "__main__":
    run()
