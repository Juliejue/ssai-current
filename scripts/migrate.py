from __future__ import annotations

import os
from pathlib import Path

import psycopg


database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise SystemExit("DATABASE_URL is required")

migrations = Path(__file__).parents[1] / "backend_app" / "migrations"
with psycopg.connect(database_url) as connection:
    for migration in sorted(migrations.glob("*.sql")):
        connection.execute(migration.read_text(encoding="utf-8"))
        print(f"applied {migration.name}")

