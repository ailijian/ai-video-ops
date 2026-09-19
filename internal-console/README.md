# AI Video Ops Internal Console

Mobile-first internal operations surface over the existing canonical pipeline.
The console stores only account, session, and asynchronous task projection data
in SQLite. Customer Truth, Cases, Persona, Content Ledger, Capacity, Batch,
Rights, Footage, and Operational Hold remain owned by `ops-pipeline` artifacts
and resolvers.

## Local setup

From `internal-console`:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
& .\.venv\Scripts\python.exe .\scripts\provision_user.py --phone 13800000000
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

The provisioning command defaults to the frozen initial password `123456` and
sets `must_change_password = true`. The password is stored only as a salted
scrypt hash. There is no registration endpoint or account-management UI.

For an existing local review account, an internal operator may explicitly reset
the account to the initial-password state:

```powershell
& .\.venv\Scripts\python.exe .\scripts\provision_user.py `
  --phone 13800000000 --reset-existing
```

## Production configuration

Run from `internal-console` with an out-of-repository environment file:

```powershell
$env:AIVO_ENV_FILE = "E:\AI-Video-Ops-Config\local-node.production.env"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app `
  --host 127.0.0.1 --port 8000 --workers 1 `
  --proxy-headers --forwarded-allow-ips "127.0.0.1,::1"
```

Do not add `--reload` or start a second instance.

- Set `AIVO_SECURE_COOKIES=1` and serve only over HTTPS.
- Set `AIVO_CONSOLE_DB` to an absolute durable SQLite path.
- Start exactly one Uvicorn worker, with reload disabled. The runner and lease
  recovery design is a single-process service architecture.
- Keep Uvicorn on `127.0.0.1:8000`; do not bind the Console to `0.0.0.0`.
- When an approved loopback reverse proxy is later introduced, use
  `--proxy-headers --forwarded-allow-ips "127.0.0.1,::1"`. Never trust `*`.
- Set `AIVO_TASK_QUEUE_MAX` (default 20) and
  `AIVO_GPU_PENDING_PER_USER_MAX` (default 3) as operational safety limits.
- Keep one Ollama instance and set its production process environment to
  `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1`.

## Task execution model

SQLite remains an execution projection, not business Authority. Task submit is
atomic per canonical operation identity, claim uses guarded `queued → running`,
and running tasks carry worker, heartbeat and lease fields. Startup only
recovers expired leases and first reconciles the canonical artifacts. A small
maintenance loop revisits leases after startup, so a fast reboot before the old
lease expires cannot leave a task permanently `running`.

- `GPU_HEAVY`: Case Analysis and any future registered local Ollama/CUDA work.
  Actual model entry is additionally protected by the cross-process
  `global_gpu` operation lock, so system-wide GPU concurrency is one.
- `STANDARD_BACKGROUND`: Customer/Speaker Analysis, Content Plan, Script
  Generation, Mix/News Plan and Export, and other long non-GPU operations.

Content Plan, Script Generation, Mix Export + Ledger Closure, News Plan and
News Export return a durable task ID immediately. A completed task means only
that execution ended; the UI re-reads the canonical delivery resolver before
presenting business completion. Browser refresh and re-login recover work from
the shared task list and request lineage.

All operators see the same shared task list. `created_by_user_id` records the
authenticated submitter for auditability and is not an access-control boundary.

## Backup and Windows boundary

Use `scripts/backup_local_node_v1.py` only with an explicitly configured
off-project destination and an idle task window. It uses SQLite online backup,
an exclusive backup barrier, artifact checksums and a temporary restore smoke.
Authority mutations hold the matching shared barrier, so backup fails closed
instead of racing a short synchronous approval. The configuration, WinSW and
read-only PowerShell templates are documented in
[`deploy/local-node`](../deploy/local-node/README.md). This repository does not
install services or modify Windows power/update settings.

## Current capability boundary

Implemented in the foundation slice:

- internal login, forced first-password change, logout, HttpOnly session;
- responsive mobile/desktop shell;
- real workbench projection from `show_customer_status_v1.py`;
- real Case Library projection from canonical Case artifacts and receipts;
- Add Case URL validation and canonical duplicate detection;
- persistent task schema and task list projection;
- recoverable `case_analysis_v1` execution with real stage progress;
- mobile Case Review, explicit reject/reanalysis/approval actions;
- approved Case promotion through `approve_case_v1.py`, source-governance companion, and deterministic fingerprint.

The Case workflow accepts a full Douyin video URL with a stable video ID. Each
attempt is isolated under `ops-pipeline/data/case_analysis_attempts`, can resume
from validated checkpoints, and always stops at Human Review. Console task
status is execution projection only. Case approval remains an explicit Human
operation and never grants production-media rights.
