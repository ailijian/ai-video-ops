-- Independent local reviewer permissions, not Compatibility business Truth.
CREATE TABLE profile_compatibility_capability_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL CHECK (action IN ('grant', 'revoke')),
    record_json TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL
);
CREATE INDEX idx_profile_compatibility_capability_user
ON profile_compatibility_capability_events(user_id, event_id);
CREATE TRIGGER profile_compatibility_no_update BEFORE UPDATE ON profile_compatibility_capability_events
BEGIN SELECT RAISE(ABORT, 'Capability audit events are immutable'); END;
CREATE TRIGGER profile_compatibility_no_delete BEFORE DELETE ON profile_compatibility_capability_events
BEGIN SELECT RAISE(ABORT, 'Capability audit events are immutable'); END;
