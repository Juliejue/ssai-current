from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from typing import Any, Iterable

import psycopg


logger = logging.getLogger("current.space_profiles")
MIN_VERIFIED_SAMPLES = 5

# Feedback factors are observations, not ratings. Each one points to an existing
# profile dimension and a target value. Unsupported factors stay in the outcome
# table but never invent a new scoring dimension.
FACTOR_TARGETS: dict[str, tuple[str, float]] = {
    "quiet": ("q", 1.0),
    "toonoisy": ("q", 0.0),
    "fewpeople": ("c", 0.0),
    "toocrowd": ("c", 1.0),
    "seat": ("st", 1.0),
    "solo": ("s", 1.0),
    "needsocial": ("s", 0.0),
    "nopressure": ("cp", 0.0),
    "toopricey": ("cp", 1.0),
    "handbusy": ("cr", 1.0),
    "keepwalk": ("w", 1.0),
    "green": ("g", 1.0),
    "newthing": ("e", 1.0),
    "people": ("co", 1.0),
    "energy": ("l", 1.0),
}


def aggregate_verified_visits(rows: Iterable[tuple[int, list[str]]]) -> dict[str, Any]:
    visits = list(rows)
    totals: dict[str, float] = defaultdict(float)
    weights: dict[str, float] = defaultdict(float)
    support: dict[str, int] = defaultdict(int)
    for change_score, factors in visits:
        weight = 1.0 + min(3, abs(int(change_score))) * 0.25
        seen: set[str] = set()
        for factor in factors or []:
            mapped = FACTOR_TARGETS.get(str(factor))
            if not mapped or factor in seen:
                continue
            seen.add(str(factor))
            tag, target = mapped
            totals[tag] += target * weight
            weights[tag] += weight
            support[tag] += 1
    sample_size = len(visits)
    tags = {tag: round(totals[tag] / weights[tag], 4) for tag in totals if weights[tag]}
    confidence = {
        tag: round(min(1.0, support[tag] / max(MIN_VERIFIED_SAMPLES, sample_size)), 4)
        for tag in tags
    }
    evidence = {tag: {"mentions": support[tag]} for tag in tags}
    mean_change = round(sum(score for score, _ in visits) / sample_size, 4) if sample_size else None
    return {
        "tags": tags if sample_size >= MIN_VERIFIED_SAMPLES else {},
        "confidence": confidence if sample_size >= MIN_VERIFIED_SAMPLES else {},
        "evidence": evidence,
        "sample_size": sample_size,
        "mean_change": mean_change,
    }


def apply_profile(place: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile or int(profile.get("sample_size") or 0) < MIN_VERIFIED_SAMPLES:
        return place
    output = {**place, "tags": dict(place.get("tags") or {})}
    confidences = profile.get("confidence") or {}
    for tag, observed in (profile.get("tags") or {}).items():
        if tag not in output["tags"]:
            continue
        confidence = max(0.0, min(1.0, float(confidences.get(tag) or 0)))
        # Human-reviewed profile remains the anchor; verified visits can move a
        # dimension by at most 45% until the evidence base grows.
        observed_weight = min(0.45, 0.15 + confidence * 0.30)
        output["tags"][tag] = round(
            float(output["tags"][tag]) * (1 - observed_weight) + float(observed) * observed_weight,
            4,
        )
    output["profile_sample_size"] = int(profile["sample_size"])
    output["profile_source"] = "verified_feedback"
    return output


async def refresh_space_profile(place_id: str) -> bool:
    database_url = os.getenv("DATABASE_URL") or ""
    if not database_url:
        return False
    try:
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            cursor = await connection.execute(
                """
                SELECT change_score, factor_keys
                FROM visit_outcomes
                WHERE place_id = %s AND presence_level = 'geofence_dwell'
                ORDER BY created_at DESC
                """,
                (place_id,),
            )
            profile = aggregate_verified_visits(await cursor.fetchall())
            await connection.execute(
                """
                INSERT INTO space_profiles
                    (place_id, tags, confidence, evidence, sample_size, mean_change)
                VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                ON CONFLICT (place_id) DO UPDATE SET
                    tags = EXCLUDED.tags,
                    confidence = EXCLUDED.confidence,
                    evidence = EXCLUDED.evidence,
                    sample_size = EXCLUDED.sample_size,
                    mean_change = EXCLUDED.mean_change,
                    updated_at = now()
                """,
                (
                    place_id,
                    json.dumps(profile["tags"]),
                    json.dumps(profile["confidence"]),
                    json.dumps(profile["evidence"]),
                    profile["sample_size"],
                    profile["mean_change"],
                ),
            )
        return True
    except psycopg.Error:
        logger.exception("failed to refresh space profile")
        return False


async def load_space_profiles(place_ids: list[str]) -> dict[str, dict[str, Any]]:
    database_url = os.getenv("DATABASE_URL") or ""
    clean_ids = list(dict.fromkeys(value for value in place_ids if value))[:100]
    if not database_url or not clean_ids:
        return {}
    try:
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            cursor = await connection.execute(
                """
                SELECT place_id, tags, confidence, evidence, sample_size, mean_change
                FROM space_profiles
                WHERE place_id = ANY(%s) AND sample_size >= %s
                """,
                (clean_ids, MIN_VERIFIED_SAMPLES),
            )
            return {
                row[0]: {
                    "tags": row[1], "confidence": row[2], "evidence": row[3],
                    "sample_size": row[4], "mean_change": row[5],
                }
                for row in await cursor.fetchall()
            }
    except psycopg.Error:
        logger.exception("failed to load space profiles")
        return {}

