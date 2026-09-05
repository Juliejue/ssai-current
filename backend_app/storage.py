from __future__ import annotations

import json
import os

import psycopg

from .schemas import OutcomeRequest, ProductEvent


def _database_url() -> str | None:
    return os.getenv("DATABASE_URL") or None


async def store_product_event(payload: ProductEvent) -> bool:
    database_url = _database_url()
    if not database_url:
        return False
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute(
            """
            INSERT INTO product_events
                (event_name, session_id, recommendation_id, place_id, properties)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (
                payload.name,
                payload.session_id,
                payload.recommendation_id,
                payload.place_id,
                json.dumps(payload.properties, ensure_ascii=False),
            ),
        )
    return True


async def store_outcome(payload: OutcomeRequest) -> bool:
    database_url = _database_url()
    if not database_url:
        return False
    # Private prose remains on the user's device until Current has accounts and
    # per-user encryption. Anonymous prose is stored only after explicit opt-in.
    shareable_note = payload.note if payload.visibility == "anonymous" else None
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute(
            """
            INSERT INTO visit_outcomes
                (session_id, recommendation_id, place_id, change_score,
                 factor_keys, visibility, anonymous_note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id, recommendation_id)
            DO UPDATE SET
                change_score = EXCLUDED.change_score,
                factor_keys = EXCLUDED.factor_keys,
                visibility = EXCLUDED.visibility,
                anonymous_note = EXCLUDED.anonymous_note,
                updated_at = now()
            """,
            (
                payload.session_id,
                payload.recommendation_id,
                payload.place_id,
                payload.change_score,
                payload.factor_keys,
                payload.visibility,
                shareable_note,
            ),
        )
    return True

