# Case Library Access V1 — CASE-CL0 implementation contract

Status: implementation contract within Founder instruction CASE-CL0 + BRAND-UI-1,
2026-10-14. This records concrete engineering choices within the approved
boundaries; it does not claim that the earlier proposed machine fields received
an independent field-by-field architecture review.

## Alignment before implementation

| Earlier Delta / approved boundary | Concrete owner and version | Compatibility / affected paths |
|---|---|---|
| Stable local principal and explicit reviewer grant/revoke | SQLite migration `005_case_library_access`; `case_library_access.py`; node namespace plus immutable local user ID; capability `case_library_reviewer`; append-only capability events | No login/Session/OIDC changes; no automatic grant/backfill. Trusted local maintenance CLI only; no HTTP grant endpoint |
| Gateway and Approval Owner independently authorize | Gateway supplies server-derived principal; `canonical_gateway.approve_case_candidate` and Pipeline `case_console_authorization_v1.py` re-read current capability | HTTP approval always supplies Console context. Existing CLI without Console flags remains trusted offline maintenance, never selected by untrusted HTTP. Existing evidence/privacy/source/SHA gates stay intact |
| Approved Case is distinct from sharing | `case_shared_display.py`; append-only `case-shared-display-v1.0` receipts in `data/case_governance/cases/<id>/shared_display/` | Exact Case/Approval Receipt SHA, explicit `audience=eligible_platform_users`, parent receipt SHA, sequence, publish/withdraw, actor/capability event, approved fields and their sources; never rewrite original Case/Approval/Fingerprint/Pattern |
| Safe fields only | Same shared-display owner; title, confirmed industry, optional finite positive duration, explicitly reviewed structural summary, optional cleared cover | `/api/cases?view=shared` and `/api/case-library/<id>` read the same whitelist. No Raw, full transcript, reviewer/private actor or original-media URL |
| Cover permission is distinct from SHA | Shared receipt optional cover clearance binds exact Case/source/cover SHA and explicit Human rights evidence; existing cover path resolver still validates local path and bytes | `/api/case-library/<id>/cover` validates current publication each request, private/no-store. Sharing grants neither original-video download nor Production Asset Rights |
| Immediate withdrawal | Validate receipt chain and live hashes each list/detail/cover request, no permission TTL cache | Old receipts retained. Shared endpoint returns uniform 404 for missing/withdrawn/invalid publication |
| Trusted submission ownership | Existing authenticated Group/Task `created_by_user_id` relationships in the same local DB; new `case-submission-v1.0` task/group companions bind namespace, user, source, task/group, time | New companions are additive. Existing non-null FK-backed authenticated submission relationships remain compatible; null/unlinked legacy records stay reviewer-only. Never infer from phone/name/file/earliest Case task |
| Case/Attempt identity | Raw access must bind to the exact resolved Attempt Task (including an explicit historical Attempt when requested), or explicit reviewer capability | Case ID alone and a duplicate Group association do not grant access to another user's Attempt |
| All private entry points | `case_library_access.py` scoped predicates plus API enforcement | Case detail/classification/review/annotations/cover/media, groups, tasks/activity/retry/boundary, workbench counts and duplicate responses; customer collaboration unchanged |
| Independent video taxonomy | No new formal type enum or classification writer | Slot says 暂未标注; type filter only enabled if formal confirmed taxonomy is actually present. Separate CASE-TAXONOMY-0 candidate report |

Shared Creative Authority remains the existing structural-production graph and
release mechanism. These node-local display and principal receipts reuse its
SHA-bound, immutable companion approach but are not automatically included in a
release: current releases exclude accounts and media. Sharing creates no second
Case approval or production lifecycle.

## Authorization and legacy rules

Only an active, explicitly granted local principal may approve/reject Case or
publish/withdraw shared display. Revocation is checked again at the owner and
serialized with that principal's approval/publish operations. Historical
reviewer text grants no current permission. The trusted maintenance CLI operates
under local OS authority, records its operator and reason, and is subject to the
existing idle/production operation boundaries; it is not an account-facing API.

Authenticated submission foreign keys already written by the original gateway
are accepted as local legacy evidence; their object relationship must be exact.
New submission companions bind the DB namespace and reject conflicting claims.
Missing submitter or mismatched Attempt remains invisible to ordinary users.
Another user's duplicate input gets only a neutral admission acknowledgement;
no private task/attempt/actor/status/review/media is linked or returned.

Owner access and shared browsing are separate: an owner/reviewer may continue
their private authorized workflow after public display is withdrawn, while the
shared endpoints and cached URLs immediately deny access. Shared browsing never
grants access to classification/evidence/retry/original video.

Publication allows a Human-confirmed display title bound to the exact approved
Case, or exact verified original metadata. Industry is derived only from the
existing valid Human classification/annotation companions. Optional structural
summary is an explicit Human-reviewed display field bound to that Case; it is
not a Customer fact. Cover clearance requires a separate explicit statement and
evidence reference bound to its bytes and original source. Neither source
acquisition/upload analysis permission nor Case approval substitutes for it.

No old artifact is silently published, backfilled, migrated or given new rights.
Unknown versions, broken receipt chains or SHA mismatch fail closed.

## Exact additive records and query semantics

`case-shared-display-v1.0` has exactly `schema_version`, `case_id`, `audience`,
`sequence`, `parent_sha256`, `action`, `at`, `actor`, `case_sha256`,
`approval_receipt_sha256`, `allowed_fields`, `display`, `sources`,
`cover_clearance`. `actor` binds namespace, user ID, capability and exact immutable
grant event ID/SHA. The whitelist is title, industry, video_type, duration_seconds,
structure_summary; the current type is always null. Title and summary are explicit
human display decisions bound to the approved SHA. Industry comes only from a
valid annotation or the exact pre-approval classification candidate SHA. Optional
duration is the approved source-media identity value; nonpositive/nonfinite values
are omitted. Cover clearance separately binds Case/source/cover SHA, evidence
reference and statement, display scope and `production_media_rights_granted=false`.
Receipt files are exclusive sequential additions under the existing Case lock.

Capability events use `case-library-capability-v1.0`: schema_version, capability,
namespace, user_id, sequence, action, operator, reason, at, parent_sha256. SQLite
stores the JSON and canonical digest; UPDATE/DELETE triggers preserve events and
namespace. Current approval rejects inactive, initial-password or ungranted users.
Historical display receipts validate the referenced historical grant chain, so a
later role revoke blocks new approvals without erasing old publication history.

New submission receipts use `case-submission-v1.0`, principal namespace/user_id,
kind/identity, sources and `at` (original submission time). Existing authenticated non-null FK relations
remain accepted only in this exact local DB, object and Attempt. No importer,
release or UI claims records without trustworthy ownership.

Search, facets, status counts and pagination are derived after access scope.
Shared sort is verified publication timestamp plus Case ID; My sort is submission
timestamp plus submission ID, preserving original Attempts. Technical Task failed,
classification needs_confirmation, awaiting Human approval, Human reject and
actual approved Case are distinct derived states. Review puts outstanding work
before approvals. No new Canonical lifecycle enum is introduced. The implementation
reads small metadata/receipts; card responses contain no Raw/whole-media payload.
There is no persisted search index or permission cache to invalidate.

## Observed legacy compatibility boundary

The actual main census found 12 legacy approved Cases; only 1 passes the existing
full source/privacy/receipt validator used by new approvals. All 12 remain
unchanged and unpublished. The other 11 cannot be published by this new contract
without separately reconciling their original incomplete source/privacy/receipt
evidence. This does not revoke their historical approval or matching lineage;
their authorized reviewer detail paths remain available. This implementation
does not weaken those Gates or rewrite old artifacts to make them publishable.
No real reviewer is granted and no real Case is published by this delivery.

## New final approvals: CASE-UAT-2 amendment (2026-10-17)

Founder approved the streamlined positive human quality decision. Machine owner
[`case_human_review_v2.py`](../../ops-pipeline/scripts/case_human_review_v2.py)
defines `case-human-quality-decision-v1.0` and `case-human-approval-v2.0`.
Every new approval, including the trusted offline CLI, requires an explicit
`suitable` / `human_final_confirmation` submission matching the exact Case,
Attempt, candidate SHA and all retained JSON evidence SHAs. The existing final
confirmation submits it; there is no extra checkbox, quality screen, mandatory
positive reason, score, role or second reviewer. Reject/reanalyze still require
reasons. Session principal, time and command identity come from the owner.

The approved Case and existing Approval Receipt embed the same quality record;
the receipt's approved Case SHA verifies their association. HTTP, Gateway and CLI
validate the same contract. CLI Console flags recheck the current reviewer grant;
CLI without them retains the existing trusted offline operating boundary.
Neither path bypasses evidence, source, privacy, Proof or production Gates.

The existing Review Command coordinates a fully committed approval using an
additive `case-review-command-commit-v1.0` companion, published in the same staged
Case directory transaction. It binds the original intent, actor, exact Attempt,
candidate/evidence, quality submission, approval/authorization/governance SHAs.
Only an exact match plus current reviewer permission can finish an interrupted
result. Recovery reads the original result and receipt; it does not invoke the
Approval Writer, cleanup, fingerprinting or task creation. Missing proof,
conflicting result or mismatched actor/intent/SHA fails closed. Existing partial
transaction repair remains separate. An old pending operation without sufficient
commit proof cannot be retroactively associated automatically.

Historical approvals without these additive versions retain their old semantics
and bytes. There is no backfill, automatic historical quality claim, withdrawal,
or new publication requirement for historical cases. Sharing and all production
rights/compatibility still use their independent existing owners.

Terminal Attempt detail lookup is independent of executable candidate selection.
Authorized owners/reviewers can read rejected decisions, reason, reviewer, time
and legal evidence; rejected Attempts get no executable approval context.
Reanalysis creates an independent Attempt, never rewrites the terminal decision.

See [CASE-TAXONOMY-0 candidate](CASE_TAXONOMY_0_CANDIDATE.md) for the separate,
unapproved vocabulary decision.

## Human evidence revision and final coverage

[`case_evidence_revision_v1.py`](../../ops-pipeline/scripts/case_evidence_revision_v1.py)
owns `case-human-evidence-edit-v1.0`, `case-human-evidence-revision-v1.0`,
`case-evidence-confirmation-policy-v1.0` and `case-evidence-final-review-v2.0`.
These are immutable companions of an existing submission Attempt, not a second
Case approval lifecycle. A saved edit is not a validated candidate or approval.
The newest unvalidated/failed revision blocks approval of older candidates.

Only a current explicitly authorized reviewer may save bounded source-audio
corrections or move an existing cut to a verified frame in the same Manifest.
Original ASR words/times, observations, media, candidates and receipts stay
unchanged. The source and parent SHA are compared inside the Case/reviewer locks.
One genuine Case-analysis Task builds each revision; it is never a submission
Attempt and is excluded from submission selection. The whole Privacy, narration,
Shot, Storyboard and Case dependency graph is rebuilt, without old `passed` cache
reuse. Absent models or failed validation leave a recoverable saved revision.

The deterministic policy requires source/Privacy/timeline evidence in addition
to confidence. Ordinary accurate results are confirmed only by the existing
final button. Uncertain results still require explicit keep or correction;
unsupported risks fail closed. Corrected evidence uses `resolved_by_revision`,
never keep of the original error. API/Gateway/Approval CLI share exact v2
coverage validation and the existing Q1 positive Human quality action.

Review Command v1.1 snapshots revision, validation and scope SHAs. A null expected
revision SHA is an explicit comparison against the original head, retained in
durable recovery. Saved edits and build Tasks recover the same operation; the
UAT-2 Domain Commit proof also binds v2 coverage and revision companions.
Historical v1 commands/receipts retain their original dispatch and bytes.
Revised candidates cannot downgrade to v1 keep coverage. Shared Display,
Fingerprint, Pattern, Compatibility, media rights and News Gates remain separate.

## CASE-SHARE-UX-2 joint final confirmation amendment

Architecture decision: `CASE_SHARE_UX_2_S0_CONTRACT_APPROVED_WITH_GUARDS`.
The executable display owner remains `internal-console/app/case_shared_display.py`.
New read-only `case-shared-display-preview-v1.0` binds exact Candidate, Attempt,
Evidence, Revision/Validation, Coverage scope, source-backed display fields,
current reviewer grant event, publication head and validator identity. Console
signs it in `human-review-command-v1.2`; edits reissue a new exact preview.
An unavailable source/scope/service never implies permission or approve-only.
Missing display title is an independent display deficiency; only then the signed
mode can be approve-only, while every existing Approval Gate still applies.

One explicit final Human action submits Q1 and `case-human-display-decision-v1.0`.
Approval and `case-shared-display-v1.1` Publication remain separate receipts.
Publication binds the actual postcommit Case/Approval hashes, original immutable
intent and exact preview. Default cover is placeholder: file existence is no right.
No original media, private transcript, business claim or reviewer log is projected.
Human title/summary edits are source-bound proposals, privacy scanned and explicitly
confirmed for display; they do not create Customer Truth or Proof.
The offline implementation permits excerpts of the exact source title and a
deterministic description of the validated timeline. Unsupported new factual
paraphrases are rejected, rather than presented as semantically verified.

Review Command owns two-stage execution and `case-review-share-result-v1.0`, not a
new approval lifecycle. A committed Approval is never repeated or rolled back for
a display failure. Temporary publication failure leaves a resumable intent;
permanent preview/head/grant changes preserve Approval and require fresh display
review via advanced management. A revoke/regrant cannot revive old consent.
An already committed publication is recognized before parent-CAS; later withdrawal
or publication always wins and an old intent never republishes. Current UI state
comes from the latest validated display projection, not the historical result.

Historical command v1.0/v1.1 and Publication v1.0 keep their frozen semantics and
bytes. Old Approval does not auto-publish. Advanced explicit publication/withdrawal,
Pattern, Fingerprint, Compatibility, News and media rights retain their own Gates.
No schema migration, role, database or background publication listener is added.
