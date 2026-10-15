-- Local application authorization, never Case/production business Authority.
CREATE TABLE console_principal_namespace (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    namespace TEXT NOT NULL UNIQUE
);
INSERT INTO console_principal_namespace VALUES (1, lower(hex(randomblob(16))));
CREATE TRIGGER console_namespace_no_update BEFORE UPDATE ON console_principal_namespace
BEGIN SELECT RAISE(ABORT, 'Principal namespace is immutable'); END;
CREATE TRIGGER console_namespace_no_delete BEFORE DELETE ON console_principal_namespace
BEGIN SELECT RAISE(ABORT, 'Principal namespace is immutable'); END;
CREATE TABLE case_capability_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL CHECK (action IN ('grant', 'revoke')),
    record_json TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL
);
CREATE INDEX idx_case_capability_user ON case_capability_events(user_id, event_id);
CREATE TRIGGER case_capability_no_update BEFORE UPDATE ON case_capability_events
BEGIN SELECT RAISE(ABORT, 'Capability audit events are immutable'); END;
CREATE TRIGGER case_capability_no_delete BEFORE DELETE ON case_capability_events
BEGIN SELECT RAISE(ABORT, 'Capability audit events are immutable'); END;
