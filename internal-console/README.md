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
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
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

- Set `AIVO_SECURE_COOKIES=1` and serve only over HTTPS.
- Set `AIVO_CONSOLE_DB` to an absolute durable SQLite path.
- Keep the repository and `ops-pipeline` artifacts mounted read-only wherever
  the console only needs projections.

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
