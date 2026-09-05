CREATE TABLE IF NOT EXISTS product_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name text NOT NULL,
    session_id text NOT NULL,
    recommendation_id text,
    place_id text,
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS product_events_session_created_idx
    ON product_events (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS product_events_name_created_idx
    ON product_events (event_name, created_at DESC);

CREATE TABLE IF NOT EXISTS visit_outcomes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id text NOT NULL,
    recommendation_id text NOT NULL,
    place_id text NOT NULL,
    change_score smallint NOT NULL CHECK (change_score BETWEEN -3 AND 3),
    factor_keys text[] NOT NULL DEFAULT '{}',
    visibility text NOT NULL CHECK (visibility IN ('private', 'anonymous')),
    anonymous_note text CHECK (char_length(anonymous_note) <= 80),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, recommendation_id)
);

CREATE INDEX IF NOT EXISTS visit_outcomes_place_created_idx
    ON visit_outcomes (place_id, created_at DESC);

