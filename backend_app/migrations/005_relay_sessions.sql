-- Anonymous, short-lived cross-device continuation. The code is the bearer
-- capability; events contain only whitelisted structured fields and expire.
CREATE TABLE IF NOT EXISTS relay_sessions (
    code text PRIMARY KEY,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS relay_sessions_expires_idx
    ON relay_sessions (expires_at);

CREATE TABLE IF NOT EXISTS relay_events (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_code text NOT NULL REFERENCES relay_sessions(code) ON DELETE CASCADE,
    event_type text NOT NULL CHECK (event_type IN (
        'interpreted', 'recommended', 'departed', 'arrived', 'feedback', 'collector_saved'
    )),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS relay_events_session_sequence_idx
    ON relay_events (session_code, sequence);
