-- UI organization only. Every item references the existing canonical Case task.
CREATE TABLE case_intake_groups (
    group_id TEXT PRIMARY KEY,
    client_request_id TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE case_intake_items (
    group_id TEXT NOT NULL REFERENCES case_intake_groups(group_id),
    position INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    canonical_url TEXT,
    case_id TEXT,
    task_id TEXT REFERENCES tasks(task_id),
    state TEXT NOT NULL CHECK(state IN ('pending', 'linked', 'error', 'input_duplicate')),
    duplicate_of INTEGER,
    error_code TEXT,
    message TEXT,
    source_upload_id TEXT,
    PRIMARY KEY (group_id, position)
);
CREATE INDEX idx_case_intake_pending ON case_intake_items(state, group_id, position);
