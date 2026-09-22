from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg


logger = logging.getLogger("current.relay")

CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 6
SESSION_TTL = timedelta(hours=12)
MAX_EVENTS = 60

# Only structured, display-safe fields may cross devices. In particular there
# is no original utterance, free-form visit note, user coordinate or identity.
EVENT_FIELDS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "interpreted": {
        "mood_id": str,
        "state_label": str,
        "need_labels": list,
    },
    "recommended": {
        "place_id": str,
        "place_name": str,
        "action": str,
        "area": str,
        "travel_label": str,
    },
    "departed": {"place_id": str, "place_name": str, "action": str},
    "arrived": {"place_id": str, "place_name": str},
    "feedback": {
        "place_id": str,
        "place_name": str,
        "change_score": int,
        "factors": list,
    },
    "collector_saved": {"place_name": str, "kind": str},
}

_memory_lock = asyncio.Lock()
_memory_sessions: dict[str, dict[str, Any]] = {}


def _database_url() -> str | None:
    return os.getenv("DATABASE_URL") or None


def normalize_code(value: str) -> str:
    return "".join(character for character in value.upper().strip() if character.isalnum())


def valid_code(value: str) -> bool:
    return len(value) == CODE_LENGTH and all(character in CODE_ALPHABET for character in value)


def safe_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = EVENT_FIELDS.get(event_type)
    if allowed is None:
        raise ValueError("unsupported relay event")
    output: dict[str, Any] = {}
    for key, expected in allowed.items():
        value = payload.get(key)
        if value is None or not isinstance(value, expected):
            continue
        if isinstance(value, str):
            output[key] = value.strip()[:120]
        elif isinstance(value, list):
            output[key] = [str(item).strip()[:40] for item in value[:6] if str(item).strip()]
        elif key == "change_score":
            output[key] = max(-3, min(3, value))
        else:
            output[key] = value
    return output


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _expires_at() -> datetime:
    return datetime.now(timezone.utc) + SESSION_TTL


async def _remember_session(code: str, expires_at: datetime) -> None:
    async with _memory_lock:
        _memory_sessions[code] = {"expires_at": expires_at, "events": [], "next_sequence": 1}


async def create_session() -> tuple[str, datetime, bool]:
    expires_at = _expires_at()
    database_url = _database_url()
    for _ in range(12):
        code = _new_code()
        if database_url:
            try:
                async with await psycopg.AsyncConnection.connect(database_url) as connection:
                    cursor = await connection.execute(
                        """
                        INSERT INTO relay_sessions (code, expires_at)
                        VALUES (%s, %s)
                        ON CONFLICT (code) DO NOTHING
                        RETURNING code
                        """,
                        (code, expires_at),
                    )
                    if await cursor.fetchone():
                        await _remember_session(code, expires_at)
                        return code, expires_at, True
            except psycopg.Error:
                logger.exception("failed to create durable relay session")
                database_url = None
        async with _memory_lock:
            if code not in _memory_sessions:
                _memory_sessions[code] = {"expires_at": expires_at, "events": [], "next_sequence": 1}
                return code, expires_at, False
    raise RuntimeError("could not create relay session")


async def _memory_append(code: str, event_type: str, payload: dict[str, Any]) -> int | None:
    async with _memory_lock:
        session = _memory_sessions.get(code)
        if not session or session["expires_at"] <= datetime.now(timezone.utc):
            return None
        sequence = session["next_sequence"]
        session["next_sequence"] += 1
        session["events"].append({
            "sequence": sequence,
            "event_type": event_type,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        session["events"] = session["events"][-MAX_EVENTS:]
        return sequence


async def append_event(code: str, event_type: str, payload: dict[str, Any]) -> tuple[int | None, bool]:
    code = normalize_code(code)
    if not valid_code(code):
        return None, False
    clean = safe_payload(event_type, payload)
    database_url = _database_url()
    if database_url:
        try:
            async with await psycopg.AsyncConnection.connect(database_url) as connection:
                cursor = await connection.execute(
                    """
                    INSERT INTO relay_events (session_code, event_type, payload)
                    SELECT code, %s, %s::jsonb
                    FROM relay_sessions
                    WHERE code = %s AND expires_at > now()
                    RETURNING sequence
                    """,
                    (event_type, json.dumps(clean, ensure_ascii=False), code),
                )
                row = await cursor.fetchone()
                if row:
                    await _memory_append(code, event_type, clean)
                    return int(row[0]), True
                return None, True
        except psycopg.Error:
            logger.exception("failed to append durable relay event")
    return await _memory_append(code, event_type, clean), False


async def _memory_read(code: str, after: int) -> tuple[list[dict[str, Any]] | None, datetime | None]:
    async with _memory_lock:
        session = _memory_sessions.get(code)
        if not session or session["expires_at"] <= datetime.now(timezone.utc):
            return None, None
        return [event.copy() for event in session["events"] if event["sequence"] > after], session["expires_at"]


async def read_events(code: str, after: int) -> tuple[list[dict[str, Any]] | None, datetime | None, bool]:
    code = normalize_code(code)
    if not valid_code(code):
        return None, None, False
    database_url = _database_url()
    if database_url:
        try:
            async with await psycopg.AsyncConnection.connect(database_url) as connection:
                session_cursor = await connection.execute(
                    "SELECT expires_at FROM relay_sessions WHERE code = %s AND expires_at > now()",
                    (code,),
                )
                session = await session_cursor.fetchone()
                if not session:
                    return None, None, True
                event_cursor = await connection.execute(
                    """
                    SELECT sequence, event_type, payload, created_at
                    FROM relay_events
                    WHERE session_code = %s AND sequence > %s
                    ORDER BY sequence ASC
                    LIMIT %s
                    """,
                    (code, after, MAX_EVENTS),
                )
                rows = await event_cursor.fetchall()
                return [
                    {
                        "sequence": int(row[0]),
                        "event_type": row[1],
                        "payload": row[2],
                        "created_at": row[3].isoformat(),
                    }
                    for row in rows
                ], session[0], True
        except psycopg.Error:
            logger.exception("failed to read durable relay events")
    events, expires_at = await _memory_read(code, after)
    return events, expires_at, False


async def reset_memory() -> None:
    """Tests only: relay sessions deliberately have no long-lived identity."""
    async with _memory_lock:
        _memory_sessions.clear()
