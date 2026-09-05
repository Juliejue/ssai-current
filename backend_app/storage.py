from __future__ import annotations

import json
import logging
import os

import psycopg

from .schemas import NeedState, OutcomeRequest, ProductEvent, Recommendation


logger = logging.getLogger("current.storage")

SAFE_EVENT_PROPERTIES = {
    "natural_language_started": {"method"},
    "natural_language_interpreted": {"source", "mood_id", "need_count", "risk_level"},
    "recommendation_shown": {"source"},
    "recommendation_accepted": set(),
    "recommendation_rejected": {"reason"},
    "navigation_opened": {"method"},
    "arrival_confirmed": set(),
    "outcome_saved": {"change_score", "factor_count", "visibility"},
}


def _database_url() -> str | None:
    return os.getenv("DATABASE_URL") or None


def safe_event_properties(payload: ProductEvent) -> dict[str, str | int | float | bool | None]:
    allowed = SAFE_EVENT_PROPERTIES.get(payload.name, set())
    return {key: value for key, value in payload.properties.items() if key in allowed}


async def store_product_event(payload: ProductEvent) -> bool:
    database_url = _database_url()
    if not database_url:
        return False
    properties = safe_event_properties(payload)
    status_by_event = {
        "recommendation_accepted": "accepted",
        "recommendation_rejected": "rejected",
        "navigation_opened": "navigation_opened",
        "arrival_confirmed": "arrived",
    }
    try:
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
                    json.dumps(properties, ensure_ascii=False),
                ),
            )
            status = status_by_event.get(payload.name)
            if status and payload.recommendation_id:
                await connection.execute(
                    """
                    UPDATE recommendation_decisions
                    SET status = %s, updated_at = now()
                    WHERE recommendation_id = %s AND session_id = %s
                    """,
                    (status, payload.recommendation_id, payload.session_id),
                )
        return True
    except psycopg.Error:
        logger.exception("failed to persist product event")
        return False


async def store_recommendations(
    session_id: str,
    state: NeedState,
    recommendations: list[Recommendation],
) -> bool:
    database_url = _database_url()
    if not database_url or not recommendations:
        return False
    # Only the constrained interpretation is stored. The original distress text
    # and the user's coordinates are intentionally absent.
    safe_state = state.model_dump(mode="json")
    try:
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            for rank, recommendation in enumerate(recommendations, start=1):
                await connection.execute(
                    """
                    INSERT INTO recommendation_decisions
                        (recommendation_id, session_id, place_id, rank, score,
                         need_state, score_breakdown, distance_source, walking_minutes)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                    ON CONFLICT (recommendation_id) DO NOTHING
                    """,
                    (
                        recommendation.recommendation_id,
                        session_id,
                        recommendation.place_id,
                        rank,
                        recommendation.score,
                        json.dumps(safe_state, ensure_ascii=False),
                        json.dumps(recommendation.score_breakdown, ensure_ascii=False),
                        recommendation.distance_source,
                        recommendation.walking_minutes,
                    ),
                )
        return True
    except psycopg.Error:
        logger.exception("failed to persist recommendations")
        return False


async def store_outcome(payload: OutcomeRequest) -> bool:
    database_url = _database_url()
    if not database_url:
        return False
    # Private prose remains on the user's device until Current has accounts and
    # per-user encryption. Anonymous prose is stored only after explicit opt-in.
    shareable_note = payload.note if payload.visibility == "anonymous" else None
    try:
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
    except psycopg.Error:
        logger.exception("failed to persist outcome")
        return False
