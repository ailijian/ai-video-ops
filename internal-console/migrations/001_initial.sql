CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 1 CHECK (must_change_password IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL CHECK (
        task_type IN ('case_analysis', 'customer_analysis', 'content_generation', 'excel_export')
    ),
    subject_ref TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'awaiting_review', 'completed', 'failed')
    ),
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    stage TEXT,
    error_code TEXT,
    error_message TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_tasks_status_updated ON tasks(status, updated_at DESC);
