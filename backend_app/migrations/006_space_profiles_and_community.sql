-- Verified visit evidence gradually replaces editorial estimates (FR-16/17).
-- No raw coordinates or private visit notes are stored here.
CREATE TABLE IF NOT EXISTS space_profiles (
    place_id text PRIMARY KEY,
    tags jsonb NOT NULL DEFAULT '{}'::jsonb,
    confidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    sample_size integer NOT NULL DEFAULT 0 CHECK (sample_size >= 0),
    mean_change double precision,
    profile_source text NOT NULL DEFAULT 'verified_visits'
        CHECK (profile_source IN ('verified_visits', 'mixed')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS space_profiles_sample_idx
    ON space_profiles (sample_size DESC, updated_at DESC);

-- User co-creation enters a moderation queue. Public reads can only see rows
-- explicitly approved later; a local draft is never silently published.
CREATE TABLE IF NOT EXISTS community_contributions (
    contribution_id text PRIMARY KEY,
    receipt_hash text NOT NULL UNIQUE,
    place_name text NOT NULL CHECK (char_length(place_name) BETWEEN 1 AND 80),
    city text NOT NULL CHECK (char_length(city) BETWEEN 1 AND 40),
    reason text NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 160),
    kind text NOT NULL CHECK (kind IN (
        'lasting_place', 'timed_beauty', 'seasonal', 'sensory', 'quiet_corner'
    )),
    mood_id text,
    source_place_id text,
    media_count smallint NOT NULL DEFAULT 0 CHECK (media_count BETWEEN 0 AND 4),
    moderation_status text NOT NULL DEFAULT 'pending'
        CHECK (moderation_status IN ('pending', 'approved', 'rejected')),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
);

CREATE INDEX IF NOT EXISTS community_contributions_public_idx
    ON community_contributions (city, created_at DESC)
    WHERE moderation_status = 'approved';

