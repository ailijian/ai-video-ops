ALTER TABLE tasks
RENAME TO tasks_before_speaker_analysis;

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,

    task_type TEXT NOT NULL CHECK (
        task_type IN (
            'case_analysis',
            'customer_analysis',
            'speaker_analysis',
            'content_generation',
            'excel_export'
        )
    ),

    subject_ref TEXT,

    status TEXT NOT NULL CHECK (
        status IN (
            'queued',
            'running',
            'awaiting_review',
            'completed',
            'failed'
        )
    ),

    progress INTEGER NOT NULL DEFAULT 0 CHECK (
        progress BETWEEN 0 AND 100
    ),

    stage TEXT,
    error_code TEXT,
    error_message TEXT,

    payload_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO tasks (
    task_id,
    task_type,
    subject_ref,
    status,
    progress,
    stage,
    error_code,
    error_message,
    payload_json,
    created_at,
    updated_at
)
SELECT
    task_id,
    task_type,
    subject_ref,
    status,
    progress,
    stage,
    error_code,
    error_message,
    payload_json,
    created_at,
    updated_at
FROM tasks_before_speaker_analysis;

DROP TABLE tasks_before_speaker_analysis;

CREATE INDEX idx_tasks_status_updated
ON tasks(status, updated_at DESC);