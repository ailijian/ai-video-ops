-- Original Task owner's exact admission/claim identity; never Case authority.
CREATE TABLE case_excel_native_admissions_v1 (
 namespace TEXT NOT NULL,
 user_id INTEGER NOT NULL REFERENCES users(id),
 operation_id TEXT NOT NULL,
 origin_sha256 TEXT NOT NULL,
 submission_input_sha256 TEXT NOT NULL,
 task_id TEXT NOT NULL REFERENCES tasks(task_id),
 relation_kind TEXT NOT NULL CHECK(relation_kind IN ('new_origin_task','linked_owned_task')),
 execution_claimed INTEGER NOT NULL DEFAULT 0 CHECK(execution_claimed IN (0,1)),
 created_at TEXT NOT NULL,
 PRIMARY KEY(namespace,user_id,operation_id),
 CHECK(relation_kind='new_origin_task' OR execution_claimed=0)
);
CREATE UNIQUE INDEX case_excel_native_primary_task_v1
 ON case_excel_native_admissions_v1(task_id) WHERE relation_kind='new_origin_task';
