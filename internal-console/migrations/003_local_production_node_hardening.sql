ALTER TABLE tasks ADD COLUMN created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN execution_lane TEXT NOT NULL DEFAULT 'STANDARD_BACKGROUND'
    CHECK (execution_lane IN ('GPU_HEAVY', 'STANDARD_BACKGROUND'));
ALTER TABLE tasks ADD COLUMN operation_identity TEXT;
ALTER TABLE tasks ADD COLUMN started_at TEXT;
ALTER TABLE tasks ADD COLUMN worker_id TEXT;
ALTER TABLE tasks ADD COLUMN heartbeat_at TEXT;
ALTER TABLE tasks ADD COLUMN lease_expires_at TEXT;
ALTER TABLE tasks ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0
    CHECK (attempt_count >= 0);

UPDATE tasks
SET execution_lane = 'GPU_HEAVY'
WHERE task_type = 'case_analysis';

CREATE INDEX idx_tasks_queue_fifo
ON tasks(status, execution_lane, created_at ASC, task_id ASC);

CREATE INDEX idx_tasks_lease
ON tasks(status, lease_expires_at);

CREATE INDEX idx_tasks_created_by
ON tasks(created_by_user_id, created_at DESC);

CREATE UNIQUE INDEX idx_tasks_one_active_operation
ON tasks(task_type, operation_identity)
WHERE operation_identity IS NOT NULL
  AND status IN ('queued', 'running');
