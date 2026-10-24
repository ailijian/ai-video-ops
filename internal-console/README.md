# AI Video Ops Internal Console

Independent Mix Compatibility v1.1 review is a thin Session/CSRF gateway over the
existing Production Profile Owner. Its dedicated local grant, exact source
snapshots, native receipts, release activation and common consumer fence are
specified in the [C0 contract](../docs/operations/PROFILE_COMPATIBILITY_V1_1_CONTRACT.md).
Case reviewer permissions, shared publication, and research hints do not grant this
capability or production eligibility. Existing business/speaker/content Human Gates
and the Task/Request lifecycle remain separate.

The [DASH-1 homepage read contract](../docs/design/DASH1_BRAND_OPERATIONS_HOME.md)
documents `/api/dashboard`, scoped metrics, actionable work and unavailable
completion statistics. The previous `/api/workbench` endpoint stays compatible.

The shared presentation foundation is owned by `static/assets/styles.css`;
list and dashboard layouts retain `brand-lists.css` and `dashboard.css`.
`ui-format.mjs` formats recorded times in Asia/Shanghai and masks displayed
account numbers without changing audit records. `task-list-view.mjs` renders
the existing scoped Task/activity responses, distinguishing execution from
Human Approval and unavailable sources from empty lists. Task tabs support
keyboard navigation and `?view=activity`; all recovery remains in the original
Task route. This UI layer adds no Authority, API, permission or lifecycle.
Unknown-title Case submissions use a friendly label in the existing read
projection while retaining exact Case/Attempt identity and original titles.
Shared controls have visible keyboard focus and mobile text/touch sizing;
the shell keeps four primary destinations and customer-scoped creation.

Mobile-first internal operations surface over the existing canonical pipeline.
The console stores account, session, editable per-operator configuration drafts, and asynchronous task projection data
in SQLite. Customer Truth, Cases, Persona, Content Ledger, Capacity, Batch,
Rights, Footage, and Operational Hold remain owned by `ops-pipeline` artifacts
and resolvers.

The [Knowledge and Operations Index](../docs/operations/README.md) routes current
product/design rules and machine owners. Presentation rules and business
interaction boundaries have distinct scopes; design freezes do not establish
implementation or production availability.

## Creation entry preparation

Customer list/detail links open `/create/config`. The stage/free editor keeps
Persona/Story allocation explicit, finite cycles confirmed, and Novel/Repurpose
counts separate. `GET/PUT /api/create/configuration/{business_id}` stores one
operator-scoped draft with optimistic revision and a server operation key; this
SQLite row grants no eligibility or content approval. Reload restores the draft,
not a past eligibility result. `/api/create/batches/preview` and `/confirm`
delegate finite batch admission to the original Native Request owner. Confirmed
intent is canonical; the SQLite draft and Task progress cannot approve content.

The existing capacity-preview gateway accepts optional `creative_style_id` and
`configuration`. Its read-only Native check binds current Business/Speaker,
Ledger, exact activated source Catalog and normalized configuration. Editing
invalidates the check; explicit confirm rechecks current gates and the supplied
`style_preflight_sha256` under the original Native locks. Same payload/key retries
recover the original Request. The resulting `generation-request-v1.1` is consumed
by original planning/generation/Human/Publish/Export owners; legacy v1.0 remains
separate. See the [machine contracts](../ops-pipeline/scripts/creative_style_contracts_v1.json),
[versioned Style rules](../ops-pipeline/scripts/creative_style_rules_v1.json) and
[B1 evidence/status](../docs/deliveries/creation-batch-ux-1/B1_EXECUTION_RECORD.md).
The B1 single-Style entry remains available independently. The subsequent
isolated batch candidate uses [C03–C06 owners](../ops-pipeline/scripts/native_batch_v1.py)
and the exact [admission policy](../ops-pipeline/scripts/creation_batch_policy_v2.json):
Mix groups retain their versioned Style and stable Slots, while Novel and
Repurpose each map one video to one original Request. Repurpose's 4–8 beats are
not multiple videos; explicit `repurposeSourceIds` must match its quantity.
Pending presentation holds grant no new semantic exposure. Existing qualification,
facts, Speaker, Pattern, Compatibility and Release gates apply independently.

The original worker dispatches one operation per Business at a time. Pause/end
stop unissued work; issued unknown results retain their original recovery and
are never automatically sent again. Content review and Publish confirmation
remain separate explicit gates. [C07](../ops-pipeline/scripts/creation_batch_review_v1.py)
continues the same immutable Human command in bounded segments, verifies original
receipts on replay, and permits whole-item rejection only where the Native owner
supports it (Mix). News beat revision stays in its original editor; no empty
approved News bundle is invented. Relogin can retrieve saved commands as intents,
not approval proof. A later explicit control keeps precedence over a concurrently
finishing review's refreshed execution context.

The original three writers delegate supplemental delivery to
[creation_delivery_v1](../ops-pipeline/scripts/creation_delivery_v1.py). Publish
edits and delegated core admission share a per-Request fence; core and supplemental
Receipt/Closure/Ledger remain with their original owners. C08 validates every
parent and row, renders at most one News and one Mix workbook, omits zero-type
files, and preserves historical versions and zero-write completed replay.
Only an explicit partial scope can deliver fewer than the confirmed target.
Current limits and tested capacity are distinct; actual evidence and remaining
UAT obligations belong to the [B2–B4 execution record](../docs/deliveries/creation-batch-ux-1/B2_B4_EXECUTION_RECORD.md).
This remains an isolated implementation candidate, not production qualification,
real-provider approval or rollout authorization.

The customer-scoped entry automatically previews the selected type and quantity;
stale responses cannot replace a newer selection. One explicit Mix confirmation
then sequences the existing `/api/create/confirm` and Request-scoped
`resolve-sources` gateways. The frontend orchestration is in
`static/assets/creation-entry-flow.js`; it creates no parallel Authority or Task.
An interrupted continuation retains the same confirmation key/payload and exact
Request. Opening an already-confirmed request with missing source preparation
continues that preparation; it does not create another request. Native permission,
Compatibility, immutable source and operation-lock checks remain mandatory.
Source preparation never calls a model or performs content Human Review/export.
News retains its existing native availability and permission gates.

## Mix generation recovery

`resolve_generation_batch_v1.py` owns native readiness and the append-only
`generation-recovery-intent-v1.0`, `generation-recovery-dispatch-v1.0` and
`generation-recovery-result-v1.0` companions defined in `generation_recovery_v1.py`.
Only initial Mix batches with zero accepted content and exclusively transport /
response failures can retry. Planning stays closed. Partial content, quality
rejection, Human review and closed history do not acquire regeneration rights.

Authenticated Session/CSRF routes
`/api/create/{request_id}/generation-recovery/preview` and `/confirm` accept only
operation ID and, for confirm, the frozen preview SHA. Caller, current sources,
Business/Speaker/constraints, live memory and pinned Compatibility are independently
rechecked by the native owner. Preview grants no execution or content approval.
Root-relative references use exact artifact bytes; parent-chain selection never
uses file time or SQLite as business authority. Unknown external outcomes require
an explicit new operation; replay cannot silently repeat a provider request.

Retry artifacts remain under the original Request's `recovery/<operation_id>/`.
Human Review, Approved Batch, Receipt and Closure remain at the Request root,
bound to the actual effective source Batch SHA. One native readiness result feeds
the Gateway, UI and original Task reconciliation. Files alone never mean ready.
Same-operation delivery replay returns the original Task; an interrupted pending
operation can continue that Task after native admission, with original capacity,
lease and locking rules. A terminal failed attempt requires an explicit new retry.

Completed Mix export is verified read-only by the original Closure owner before
enqueue. Response `content-operation-response-v1.1` contains `accepted=false`,
`recovered=true`, `canonical_result`, and the original execution `task` (without
rewriting its status), or null when no Task projection exists. Existing non-completed responses keep their
`accepted/task` shape. JS handles canonical completion before Task polling.
No duplicate Task, Closure or Ledger is created by completed replay. Historical
closed interpretation and the current Compatibility write fence are unchanged.

Native partial delivery uses the companion schemas in
`ops-pipeline/scripts/delivery_receipt_recovery_v1.py`. An immutable
`generation-human-review-intent-v1.0` freezes the trusted stable principal,
current authorization state, exact source references, normalized decision,
timestamp and expected Review bytes before the original Review → Approved →
Approval Receipt writes. Missing receipts never project as approved. Explicit
replay must match that decision and current native source/Compatibility checks.
Legacy partial reviews without a trusted intent require an authenticated explicit
reconfirmation; no Reader attributes a historical name to a current principal.

Before a new export, `mix-export-intent-v1.0` freezes the same trusted identity,
native Approved/Approval/source versions, frozen template and server-selected
output path. The native exporter validates the complete workbook, retains an
immutable staged workbook and writes `mix-export-publication-v1.0` before
exclusive publication. A published workbook without its Receipt resumes only
against this exact intent/witness and unchanged workbook bytes. Unbound legacy
workbooks fail closed. New `mix-excel-export-receipt-v1.1` binds both companions;
the historical v1.0 Reader remains supported without rewriting old receipts.

Partial UI states offer **继续完成原操作**. Human approval requires its complete
native receipt bundle; formal downloads require the Export Receipt and, for new
bound exports, native Closure verification. Pending Closure rechecks current
authorization and Compatibility before Ledger/Closure writes. Resuming export
reuses the original Task; completed replay is read-only and adds no Task or
Ledger entry. SQLite task status is only an execution projection. The native
generation result separately reports `generation_completed` so an interrupted
downstream Human receipt cannot turn a finished generation Task into a failure.

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

Customer and content tasks retain their existing internal collaboration scope.
Case Tasks, Groups, raw detail, evidence and source media are scoped to the exact
authenticated submitter/Attempt or an explicitly granted Case reviewer; missing
ownership is never inferred. Shared browsing uses a separate safe projection.

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

### Case library access and shared display

See [Case Library Access V1](../docs/design/CASE_LIBRARY_ACCESS_V1.md) for the
versioned machine contract. Migration 005 creates a stable node namespace and
append-only reviewer capability events, with no automatic grants. Trusted local
maintenance uses `scripts/manage_case_reviewer.py --user-id <stable-local-id>
--action grant|revoke --reason <explicit-reason>` against an explicitly configured
node during the existing permitted maintenance window. There is no HTTP grant
endpoint. A changed password, submitter role, phone or historical reviewer string
does not grant approval authority. HTTP and Pipeline Approval Owner revalidate
server-derived principal/capability; the unflagged CLI remains trusted offline
maintenance and is never chosen by untrusted HTTP.

`GET /api/cases?view=shared|mine|review` scopes before search, facets, totals and
pagination (default 20, maximum 50). Shared is the default; review requires explicit
capability. `GET /api/case-library/<id>` returns whitelist display fields only.
`POST /api/cases/<id>/publication` requires reviewer, CSRF, Case lock, exact Case
and approval SHA and expected display receipt SHA. Append-only publish/withdraw
receipts preserve original Case/Receipt/Pattern/Compatibility. Old approvals have
no implicit publication. Covers require separate explicit display evidence and
exact source/file SHA; original video access and production rights remain separate.
Shared list/detail/cover revalidate current receipts without a permission TTL cache;
withdrawn, invalid or unknown records return uniform 404. Responses are private,
no-store. Historical missing-owner records remain reviewer-only.

The application reuses existing authorized cover bytes; it neither generates nor
fetches remote thumbnails. Absent/invalid covers use a common vector placeholder.
No independent confirmed video-type dictionary exists: the slot remains 暂未标注,
and the type filter is absent until an approved taxonomy exists. Mix/News remains
a distinct production profile. Brand list styling is owned by `brand-lists.css`;
`styles.css` owns shared tokens and retained shell/creation components.

### Case Smart Intake

`/cases/new` extracts Douyin URLs from share text and admits at most ten distinct,
resolved video identities per UI group. `POST /api/case-intake/groups` accepts
`text`, a stable `client_request_id`, and an optional single-source upload ID.
SQLite groups reference existing Case tasks; they own navigation only. Pending
items enter the original gateway as capacity becomes available. Owner/reviewer-scoped group
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

## Customer and Speaker smart intake

`POST /api/customers/analyze` accepts a required `customer_name`, optional
`industry`, and `materials`. Analysis requires nonempty materials; `save_only`
saves a recoverable name-only intake without a model call or task. New identities
are generated once, independently of name/industry. Historical IDs are unchanged.
`submission_key` makes initial submission replayable; same-name records require
an explicit existing-customer check or `create_separate`, never automatic merging.

Fact review keeps the original AI candidates and individual Human decisions.
Optional `industry_review` distinguishes absent judgment, explicit `uncertain`,
and a confirmed value from the existing industry taxonomy. It does not add a
readiness requirement. Discovery selection is an intake proposal, never Speaker
approval. Legacy Customer review and Speaker confirmation retain their separate business-lock operations: a draft failure
returns recoverable partial success, preserving the completed Customer review.
`POST /api/customers/{business_id}/speaker-discovery/confirm` resumes saved
selection intent independently. `/speaker-discovery/retry` runs only discovery
from the saved privacy projection using the existing analysis task/runner.

The unified Customer confirmation keeps those writers and the existing final
Persona approver. `POST /api/customers/{business_id}/review-preview` is read-only:
it derives the final known facts and effective restrictions with the same
`derive_business_persona_input` used by the canonical builder. The signed
`customer-final-confirmation-v1.0` preview binds the source review context,
Intake/candidate/current state, proposed decisions, exact displayed projection,
current authenticated principal, and either `approve_business_profile` or
`save_review_progress`. Missing or failed previews never imply approval.

`POST /api/customers/{business_id}/confirm` requires an explicit matching choice
and preview SHA under `human-review-command-v1.3`. The existing Business lock
protects append-only fact review, final candidate comparison and native Persona
approval. `data/review_operations/business/<id>/<operation>/business_approval_target.json`
binds the original intent/actor/preview to the exact candidate and independent
fact-review companions; the existing Approval Receipt links it through
`review_decision_metadata.decision_artifact_ref`. It is an operation companion,
not another Truth store or approval lifecycle. A completed prior fact review is
reused without replaying or rewriting its decisions. Human Speaker selection
may save a Draft and start its existing analysis handoff; it never approves a
Speaker. R1→R2 binding/revalidation, media rights and creation Gates remain separate.

Blocked or incomplete material can only save legal review progress. An
interrupted operation retains both commit boundaries, checks exact original
identity/source/receipt and current access, and resumes through the existing
Review Command recovery entry. It does not repeat a completed Approval or Task.
An unfinished operation must be recovered or legally cancelled before starting
another one. New contexts cannot be downgraded to legacy approval endpoints;
historical contexts and independently explicit legacy/CLI approval remain valid
under their original contracts. No approved artifact or historical SHA is
migrated or reinterpreted as a new joint decision.

New initial onboarding can prepare and confirm selected Speakers on that same
page. `speaker_review_preparation_v1.py` owns immutable
`speaker-review-preparation-v1.0` proposals under `data/speaker_preparations`.
`POST /api/customers/{id}/review-preparation` uses the saved Customer sources and
the existing Customer task worker to prepare Privacy-projected personal facts;
it never writes a Human decision or approved Persona. Repeated preparation
reuses its exact source/selection identity; failed extraction resumes the same
task. Changing source or selected identity requires a different proposal.

`customer_speaker_confirmation.py` coordinates
`customer-final-confirmation-v1.1` with Business-only
`human-review-command-v1.4`. The final signed context includes both the exact
Business sub-decision and complete selected-person proposals/decisions. One
explicit `approve_customer_and_speakers` action commits the existing Business
owners first, then each unchanged Speaker Intake/Fact Review/Persona Approval
owner against the actual Approved Business revision. Cached extraction may be
promoted only when its original sources and actual native candidates match the
displayed proposal; no model call occurs in the approval operation. Every
Speaker retains a separate Human Fact Review and Approval Receipt, linked to
the same operation and exact Business Approval Receipt. Partial success is
recoverable without re-approving completed objects or creating duplicate tasks.

Incomplete selected-person evidence cannot silently become a successful joint
approval. The UI can explicitly request `business_only`, which signs a normal
customer-only confirmation and never approves people. Existing approved Speaker
revisions still use their explicit Business-version revalidation contract; this
initial-onboarding path does not rewrite them. Unfinished joint operations
block competing selected-Speaker mutations. Historical v1.0/v1.3 contexts and
independent legacy approval remain governed by their original contracts.
All Console Business/Speaker source mutations check unfinished confirmation
commands inside the shared Business lock. Only the exact Review Command
recovery and legal cancellation routes may proceed through that barrier, so a
new supplement or analysis cannot invalidate a partially committed operation.
The browser context binds local personal source/projection digests rather than
duplicating raw personal material; the commit re-derives and compares that exact
displayed meaning before calling the native Human writers.

`POST /api/customers/{business_id}/gaps/supplement` retains reviewed evidence.
Standalone Speaker review uses the same explicit final-action semantics.
`POST /api/customers/{business_id}/speakers/{speaker_id}/review-preview` is
read-only. `speaker_confirmation.py` derives `speaker-final-confirmation-v1.0`
with the native Speaker decision coverage, historical-source merge, revision,
capability and critical-conflict checks. Normal facts are pending bulk choices.
Source-bound, conflict-free own-work restrictions also join that final choice:
the server checks the native Intake identity, raw-answer SHA and exact quotation,
then conservatively recognises only restrictive clauses. Unrecognised wording,
expansions, identity changes and conflicts still require an explicit choice.
Known expression restrictions are read-only and remain in the native historical
source merge; ordinary corrections cannot remove protected fields. These defaults
are pending selections, never saved decisions. All required candidates still
receive native Human decisions only at the explicit final submit.

`POST .../speakers/{speaker_id}/confirm` accepts only `approve_speaker_profile`
with the exact signed preview under `human-review-command-v1.5`. It shares the
existing Business lock and stages `speaker_approval_target.json` in the existing
Speaker Review Command directory. The original immutable Speaker Fact Review
and independent Persona Approval Receipt remain separate. The latter binds the
exact staged decision, actor, intent, reviewed sources and current Business SHA.
A completed legacy review is reused unchanged. No Task, Draft, media permission
or Business approval is created by this confirmation. A blocked preview cannot
submit; there is no implicit save-only or approval fallback.

Interrupted review, candidate/target persistence, native approval or final result
resumes the original intent across sessions/processes. Unfinished commands guard
competing Speaker mutations; committed stages cannot be discarded. Replays
verify their independent receipt references, and a new actor, source, Business
revision or altered intent cannot borrow the operation. v1.5 cannot enter old
review/approve routes. Historical commands retain their original dispatch and
recovery contracts. This changes interaction, not the Persona Authority lifecycle.

For an approved customer, additive facts form the next unapproved Business
revision through the existing builder. The approved revision remains effective
until independent Persona approval. Empty additions do not create a revision;
conflicting scalar facts preserve conflict evidence and require a new explicit
decision. Approved bytes, receipts, historical Requests and business-wide Ledger
remain unchanged.

After a new Business approval, a Speaker bound to the old revision is projected
as `revalidation_required` and excluded from creation readiness. Human review at
`POST /api/customers/{business_id}/speakers/{speaker_id}/revalidation/review`
requires the exact current Business/Speaker file hashes and an explicit
confirmation that personal facts and expression limits still apply. The record
under `data/speaker_revalidations/<speaker_id>/business_revision_NNNN/` creates an
unapproved Speaker revision through the existing builder. Separate Speaker
Persona approval remains required. Changed personal facts require new evidence
and Human handling; this unchanged-evidence action must not be used to approve
them. Speaker gap answers still require all current gaps in one submission.

Manual browser acceptance can use `tests/browser_customer_speaker_intake_v1.py`
with a new external `--workdir` and loopback `--port` (never 8000). It runs current
ASGI/static/auth/migrations/locks against isolated artifacts and serial synthetic
extraction only. `--resume` requires its fixture manifest. Close that node after
acceptance; fixtures do not establish model quality or Production PASS. Evidence
for this implementation is in the
[implementation report](../docs/design/CUSTOMER_SPEAKER_SMART_INTAKE_V1_IMPLEMENTATION_REPORT.md).

[Novel News](../docs/operations/RUNBOOK.md#new_novel_news) is a separate
implemented flow with rollout defaulting to `off`. Its controlled access,
supported opportunities and additional Scene Contrast validation gate do not
follow from the existence of UI/code or from a completed task. Runtime access
is owned by `app/config.py` and `app/novel_news_rollout.py`; artifact structure
and semantic closure are owned by `ops-pipeline/scripts/novel_news_v1.py`.


## Review closure and targeted corrections

Final Case, Business and Speaker review commands use the shared
[`review_commands.py`](app/review_commands.py) protocol
`human-review-command-v1.0`. A detail response supplies `approval_context`;
Speaker fact review also uses it, while Business fact review retains its own
existing `review_context`. HTTP requests must send the displayed opaque token.
The token binds the node, stable Session principal, exact object, Intake/Attempt,
artifact SHA and source snapshot. Missing, borrowed or stale contexts are rejected
before domain mutation. Review capability, Session and CSRF checks run again on
replay; a saved command is never a permission grant.

Commands append an immutable intent and result under
`data/review_operations/<kind>/<id>/<operation_id>/`. These are recovery
companions, not new business approval. Replaying the same actor, context and
payload resumes the original operation, including after restart. Changed
payloads fail closed. The submitting principal alone may fetch unfinished
commands at `GET /api/review-commands/{kind}/{id}`. Cancelling an uncommitted
submission appends a cancelled result and cannot revoke any domain decision.
Case reanalysis admission carries the same operation identity: queue failure can
resume to one Task without replacing the original Human decision. Source upload
and provider preflight happen before saving a new command; a created Task is
reused without consuming the upload a second time.

Business/Speaker `POST .../review-amendments` accepts an explicit correction
reason, selected field values and source evidence, plus the same context.
Canonical [`persona_review_lifecycle_v1.py`](../ops-pipeline/scripts/persona_review_lifecycle_v1.py)
owns `persona-review-lifecycle-v1.0`. It appends a new Intake with exact source
references. Human Fact Review and a separate final Persona approval are still
required. Unchanged reviewed fields may be reused with their lineage; replacement
fields supersede earlier values only after explicit Human approval/edit. Ordinary
corrections cannot resolve identity conflicts or remove expression restrictions.
A returned unapproved candidate retains its bytes and receives a SHA-bound
`review_disposition_v1.json`; both resolver and approver refuse its reuse. A new
candidate uses `revision_NNNN_<operation-id-prefix>` when needed to preserve old
unapproved revisions. Approved revision sequence and receipts are unchanged.

When Business changes before the first Speaker is approved,
`binding_review_required` offers explicit reuse of saved personal evidence against
the current Business via a new Intake. Pending personal changes remain pending;
no null revalidation receipt is assumed. Existing approved-Speaker revalidation
remains a separate unchanged-evidence workflow. Duplicate Speaker submissions
with changed materials explicitly report that the new input was not saved and
link to targeted correction, rather than claiming a new analysis was created.

Persona approval writes `approval_intent_v1.json` before approved bytes and the
immutable receipt. Interrupted writes recover only the exact Human decision and
recheck fact/source/constraint validation. Console also checks current Speaker
Business binding. No new reviewer roles, production rights or compatibility are
granted by any of these recovery paths. Shared publication remains separate from
Case approval; unavailable publication context returns actionable whitelist
blockers to reviewers. Foreign deduplicated submissions without accessible task
lineage remain neutral terminal submissions, never an endless analysis spinner.


A validated upload used by an unfinished reanalysis command receives a
SHA-bound `source_upload_reservation_v1.json` in that command directory. Hourly
orphan cleanup retains that exact source while the command is unfinished. The
24-hour new-admission limit does not expire an already saved decision waiting
for queue capacity. Resume revalidates the receipt, bytes, source, principal and
current reviewer grant. Once a Task exists, its existing retention policy owns
the source. Cancelled uncommitted commands release the reservation for ordinary
cleanup. Outstanding file quota remains in force; missing or corrupt sources
fail closed for trusted recovery and are never silently replaced.
