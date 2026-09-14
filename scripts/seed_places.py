from __future__ import annotations

import json
import os

import psycopg

from backend_app.recommender import load_catalog


database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise SystemExit("DATABASE_URL is required")

with psycopg.connect(database_url) as connection:
    for place in load_catalog()["PLACES"]:
        amap = place.get("amap") or {}
        connection.execute(
            """
            INSERT INTO places
                (place_id, place_name, catalog_data, map_provider,
                 provider_place_id, longitude, latitude,
                 verification_status, verified_at)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (place_id) DO UPDATE SET
                place_name = EXCLUDED.place_name,
                catalog_data = EXCLUDED.catalog_data,
                map_provider = EXCLUDED.map_provider,
                provider_place_id = EXCLUDED.provider_place_id,
                longitude = EXCLUDED.longitude,
                latitude = EXCLUDED.latitude,
                verification_status = EXCLUDED.verification_status,
                verified_at = EXCLUDED.verified_at,
                updated_at = now()
            """,
            (
                place["placeId"],
                place["placeName"],
                json.dumps(place, ensure_ascii=False),
                "amap" if amap else None,
                amap.get("provider_place_id"),
                amap.get("longitude"),
                amap.get("latitude"),
                amap.get("verification_status", "unverified"),
                amap.get("verified_at"),
            ),
        )
print(f"已同步 {len(load_catalog()['PLACES'])} 个地点。")
