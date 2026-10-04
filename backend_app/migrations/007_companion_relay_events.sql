-- Extend the existing event whitelist; retain all existing rows and fields.
ALTER TABLE relay_events DROP CONSTRAINT IF EXISTS relay_events_event_type_check;
ALTER TABLE relay_events ADD CONSTRAINT relay_events_event_type_check CHECK (
    event_type IN ('interpreted', 'recommended', 'departed', 'arrived', 'feedback',
                  'collector_saved', 'companion_action', 'companion_ack', 'scene_changed')
);
