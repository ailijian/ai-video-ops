# AI Video Ops Internal Console

Mobile-first internal operations surface over the existing canonical pipeline.
The console stores only account, session, and asynchronous task projection data
in SQLite. Customer Truth, Cases, Persona, Content Ledger, Capacity, Batch,
Rights, Footage, and Operational Hold remain owned by `ops-pipeline` artifacts
and resolvers.

The [Knowledge and Operations Index](../docs/operations/README.md) routes current
product/design rules and machine owners. Presentation rules and business
interaction boundaries have distinct scopes; design freezes do not establish
implementation or production availability.

## Local setup

Verification requires the declared `[dev]` dependencies and Node.js. From the
repository root use `python tools/verify.py --target console` for isolated,
parallel Console checks, or omit `--target` for complete repository regression.
See [Verification](../tools/README.md). The package's `python -m pytest` also
includes every frontend JavaScript behavior test.

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
- Leave `AIVO_DEFAULT_BUSINESS_ID` unset on a fresh Production node. It is an
  optional Workbench convenience selection only; it never defines Customer,
  Persona, or Ledger Authority. With no customers, Workbench returns a normal
  empty state. With one customer it can resolve that unique customer; with
  multiple customers it requires an explicit selection and never picks the
  first filesystem/list entry.

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

### Case Smart Intake

`/cases/new` extracts Douyin URLs from share text and admits at most ten distinct,
resolved video identities per UI group. `POST /api/case-intake/groups` accepts
`text`, a stable `client_request_id`, and an optional single-source upload ID.
SQLite groups reference existing Case tasks; they own navigation only. Pending
items enter the original gateway as capacity becomes available. Shared group
GET routes recover state across sessions/devices without submitting new work.

Missing `operator_profile_hint` means no operator judgment was supplied. The
legacy explicit values remain `mix`, `news`, `hybrid`, and `uncertain`; absence
does not silently select any of them. Industry initially remains `待分类`.
Recommendations read validated, privacy-projected Case evidence and the
SHA-bound Storyboard narration timeline. No new remote model is called.

`GET/POST /api/cases/<id>/classification` reads/writes the attempt-bound
`case_classification_review_v1.json` companion under the Case operation lock.
It retains the original suggestion, human choices/history, authenticated actor,
time and optimistic hashes. Human confirmation admits unresolved labels only
explicitly and never approves Case, Compatibility, media rights or customer
facts. Smart-intake Case approval additionally requires classification first;
all existing final evidence, privacy, Proof and source gates remain in force.
Approved label corrections use existing SHA-bound annotation companions.

`POST /api/tasks/<id>/retry` resumes the latest failed Case task with its same
attempt/checkpoints, subject to existing queue/GPU admission limits.
Each task permits at most three explicit failed-stage retries; queued duplicate
clicks do not consume another retry. Existing Qiyun pacing remains one provider
call per 60 seconds, with no implicit provider fallback. A retry can incur cost
when acquisition/model evidence was not completed; the cap is not a currency
budget. Operator identity/time remain in `retry_actions`.
Pending Shot Boundary review must still use the existing boundary-review gateway.
Replacing a source file requires an explicit new upload/attempt, with original
source identity and rights checks retained. Cover images are served only when
an existing local, SHA-bound cover survives transient-media cleanup.

Confirmed classification cards are read-only until the operator chooses to
edit. An individual confirmation is itself the audited Human action; its form
does not require an extra checkbox. Explicit industry uncertainty is a field
choice mapped to `null`, while an untouched empty field cannot be submitted.
Only checked, determinate, pending classifications enable the batch action.
Execution completion and canonical Case admission have separate counters.
Confirmed copy distinguishes known labels, both explicitly unknown labels, and
partially unknown labels without changing counters or blocking Human Case Review.
For controlled runtime promotion and rollback gates, use the
[V1.1 production deploy runbook](../docs/operations/CASE_SMART_INTAKE_V1_1_PRODUCTION_DEPLOY_RUNBOOK.md).

Migrations execute DDL, copied rows and applied markers in one `BEGIN IMMEDIATE`
transaction; a failed migration rolls back before the node begins serving.
An applied marker prevents repeat creation. Before deployment, use the existing
idle-window backup route, verify restore/integrity and rehearse the upgrade on
the backup. Restore the verified backup if a previously interrupted,
non-transactional upgrade left unmarked partial tables; do not drop tables or
insert migration markers by hand.

Offline migration checks: `python -m pytest tests/test_case_intake_migration_v1.py`.
The same module's CLI accepts `--source <existing DB> --output <new external
directory>` and only opens the source in SQLite read-only online-backup mode.
It records preserved historical rows, applied markers, repeated startup,
injected failure rollback and backup restore/integrity without exposing rows.

Browser acceptance uses `tests/browser_case_smart_intake_v1.py --workdir <new
directory outside the repo> [--database-backup <audited external DB copy>]`.
It runs the current complete ASGI app on loopback with real cookies, login and
CSRF, replacing the V1.0 pre-authenticated HTTP bridge. All production workers
are off. A serial test-only fixture driver exercises task claim/admission and
recovery with synthetic analysis evidence; it invokes no provider/model/GPU.
`--resume` reuses only a verified fixture directory, its database and artifacts.
Port 8000 is rejected. Close the isolated node after screenshots. This is not
real media, model/provider or production validation.

The implemented foundation includes:

- internal login, forced first-password change, logout, HttpOnly session;
- responsive mobile/desktop shell;
- fresh-safe Workbench projection: empty data is valid, while a selected
  customer's status still comes from `show_customer_status_v1.py`;
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

Current orchestration also includes Customer/Speaker analysis, separate fact
review and Persona approval, readiness/gap flows, Mix creation with Human
Review V2 and export/Ledger closure, and the narrow News repurpose flow.
Their canonical entries and recovery boundaries are in the
[RUNBOOK](../docs/operations/RUNBOOK.md).

[Novel News](../docs/operations/RUNBOOK.md#new_novel_news) is a separate
implemented flow with rollout defaulting to `off`. Its controlled access,
supported opportunities and additional Scene Contrast validation gate do not
follow from the existence of UI/code or from a completed task. Runtime access
is owned by `app/config.py` and `app/novel_news_rollout.py`; artifact structure
and semantic closure are owned by `ops-pipeline/scripts/novel_news_v1.py`.
