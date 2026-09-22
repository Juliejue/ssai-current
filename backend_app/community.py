from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta

import psycopg

from .schemas import CommunityContributionRequest, CommunityContributionPublic


logger = logging.getLogger("current.community")

EXPIRY_BY_KIND = {
    "timed_beauty": timedelta(hours=1),
    "sensory": timedelta(hours=3),
    "seasonal": timedelta(days=7),
}


def expiry_for(kind: str, now: datetime | None = None) -> datetime | None:
    duration = EXPIRY_BY_KIND.get(kind)
    return ((now or datetime.now(UTC)) + duration) if duration else None


def _receipt_hash(receipt_token: str) -> str:
    return hashlib.sha256(receipt_token.encode("utf-8")).hexdigest()


async def submit_contribution(
    payload: CommunityContributionRequest,
) -> tuple[str | None, str | None, bool]:
    database_url = os.getenv("DATABASE_URL") or ""
    if not database_url:
        return None, None, False
    contribution_id = f"contrib_{secrets.token_hex(12)}"
    receipt_token = secrets.token_urlsafe(32)
    try:
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            await connection.execute(
                """
                INSERT INTO community_contributions
                    (contribution_id, receipt_hash, place_name, city, reason, kind,
                     mood_id, source_place_id, media_count, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    contribution_id,
                    _receipt_hash(receipt_token),
                    payload.place_name,
                    payload.city,
                    payload.reason,
                    payload.kind,
                    payload.mood_id,
                    payload.source_place_id,
                    payload.media_count,
                    expiry_for(payload.kind),
                ),
            )
        return contribution_id, receipt_token, True
    except psycopg.Error:
        logger.exception("failed to submit community contribution")
        return None, None, False


async def list_approved_contributions(
    city: str | None = None,
    *,
    limit: int = 30,
) -> list[CommunityContributionPublic]:
    database_url = os.getenv("DATABASE_URL") or ""
    if not database_url:
        return []
    where_city = "AND city = %s" if city else ""
    parameters: tuple = (city, limit) if city else (limit,)
    try:
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            cursor = await connection.execute(
                f"""
                SELECT contribution_id, place_name, city, reason, kind, mood_id,
                       media_count, created_at, expires_at
                FROM community_contributions
                WHERE moderation_status = 'approved'
                  AND (expires_at IS NULL OR expires_at > now())
                  {where_city}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                parameters,
            )
            return [
                CommunityContributionPublic(
                    contribution_id=row[0],
                    place_name=row[1],
                    city=row[2],
                    reason=row[3],
                    kind=row[4],
                    mood_id=row[5],
                    media_count=row[6],
                    created_at=row[7].isoformat(),
                    expires_at=row[8].isoformat() if row[8] else None,
                )
                for row in await cursor.fetchall()
            ]
    except psycopg.Error:
        logger.exception("failed to list community contributions")
        return []


async def delete_contribution(contribution_id: str, receipt_token: str) -> bool:
    database_url = os.getenv("DATABASE_URL") or ""
    if not database_url:
        return False
    try:
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            cursor = await connection.execute(
                """
                DELETE FROM community_contributions
                WHERE contribution_id = %s AND receipt_hash = %s
                """,
                (contribution_id, _receipt_hash(receipt_token)),
            )
            return cursor.rowcount > 0
    except psycopg.Error:
        logger.exception("failed to delete community contribution")
        return False
