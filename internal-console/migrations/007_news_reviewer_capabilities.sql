-- Add independent permission domains without rewriting historical event JSON.
ALTER TABLE profile_compatibility_capability_events ADD COLUMN capability TEXT NOT NULL
    DEFAULT 'profile_compatibility_reviewer'
    CHECK (capability IN ('profile_compatibility_reviewer',
        'news_profile_compatibility_reviewer', 'news_pattern_reviewer'));
CREATE INDEX idx_profile_compatibility_capability_domain
ON profile_compatibility_capability_events(user_id, capability, event_id);
