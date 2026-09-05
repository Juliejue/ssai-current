CREATE TABLE IF NOT EXISTS places (
    place_id text PRIMARY KEY,
    place_name text NOT NULL,
    catalog_data jsonb NOT NULL,
    map_provider text,
    provider_place_id text,
    longitude double precision,
    latitude double precision,
    verification_status text NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'verified', 'rejected')),
    verified_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS places_provider_identity_idx
    ON places (map_provider, provider_place_id)
    WHERE provider_place_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS recommendation_decisions (
    recommendation_id text PRIMARY KEY,
    session_id text NOT NULL,
    place_id text NOT NULL,
    rank smallint NOT NULL CHECK (rank > 0),
    score double precision NOT NULL CHECK (score BETWEEN 0 AND 1),
    need_state jsonb NOT NULL,
    score_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
    distance_source text NOT NULL CHECK (distance_source IN ('amap', 'prototype_estimate')),
    walking_minutes integer,
    status text NOT NULL DEFAULT 'shown'
        CHECK (status IN ('shown', 'accepted', 'rejected', 'navigation_opened', 'arrived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS recommendation_decisions_session_created_idx
    ON recommendation_decisions (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS recommendation_decisions_place_status_idx
    ON recommendation_decisions (place_id, status, created_at DESC);
