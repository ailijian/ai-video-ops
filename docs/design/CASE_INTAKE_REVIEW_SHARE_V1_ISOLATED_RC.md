# CASE_INTAKE_REVIEW_SHARE_V1_ISOLATED_RC

Founder and independent product verdict:
`CASE_SHARE_UX_2_FOUNDER_ISOLATED_UAT_PASS` (2026-10-18).
This is an isolated release candidate, not production approval or permission to
push, merge, deploy, use real models, or change a production database.

## Exact lineage and scope

The candidate starts at `363e5f3fa243cbef27969775273502ebfc188215`, following
`d41792b6ac373d95ed68c95850a2d420f925cc48` (CASE-UAT-2 approval recovery,
terminal reads and streamlined human quality). Its source is the full accepted
`codex/case-share-ui1` workspace, including the uncommitted CASE-REVIEW-UX-1,
scope fallback closure, CASE-SHARE-UX-2 and recovery presentation changes.
The commit containing this document freezes those CASE increments. The precise
commit, file SHA manifest and fresh validation receipts are recorded in the
local CASE RC handoff; neither an old HEAD nor a runtime database is a substitute.

Inherited `b06bd0887e4a3916279f6e76754caa1bb31a93e6` owns the existing Console,
four-item navigation, customer/speaker and dashboard baseline. This candidate
does not sweep later uncommitted customer, legacy-scope, dashboard or AUTH work
into the CASE commit. Shared `main.py`, task service, review protocol, privacy
and shot builders, app entry and asset imports contain only CASE dependencies
in this increment; non-CASE paths retain the inherited behavior.

## Owners and compatible contracts

The executable owners and full boundaries remain in
[Case Library Access V1](CASE_LIBRARY_ACCESS_V1.md) and the
[Authority Map](../operations/AUTHORITY_MAP_V1.md).

| Contract | Existing owner |
|---|---|
| Case Intake, classification, object access and reviewer grant | Console intake, classification and Case access adapters |
| Human quality v1.0 / Human approval v2.0 | `case_human_review_v2.py`, `approve_case_v1.py` |
| Human evidence edit/revision/validation v1.0 | `case_evidence_revision_v1.py` |
| Confirmation policy v1.0 / final evidence review v2.0 | Same revision and coverage owner |
| Signed display preview / human display decision v1.0 | `case_shared_display.py` |
| Shared display v1.1, historical v1.0 publish/withdraw | Same publication owner, separate from Case Approval |
| Human Review Command v1.2, historical v1.0/v1.1 | `review_commands.py` |
| Case review/share result v1.0 | Same command owner; current visibility always follows the latest valid publication |

New scope failures cannot fall back to legacy keep. Edits append evidence and
validated derived candidates without modifying original ASR, frames, candidates
or receipts. The original final human confirmation supplies coverage, quality
and exact display consent; high-risk/unknown evidence stays blocked.

Approval and Publication remain two independent receipts. Partial publication
failure preserves approval; exact recovery resumes only missing steps. A later
withdrawal cannot be reversed by an old intent. The read-only progress projection
explains retry sharing versus synchronizing results; it grants no capability.
Historical approvals, reviews, publications and commands keep their frozen
versions and bytes. There is no retrospective quality claim or bulk publication.

## Acceptance and remaining boundaries

Founder operated four fictional tracks through formal authentication, CSRF,
reviewer authorization, revision/coverage, quality, Approval, Publication and
Review Command: A normal approval/share; B no-cover safe text; C publication
failure and original-operation recovery; D withdrawal followed by result recovery.
All passed. Ordinary users see A/B/C and cannot find or directly read withdrawn
D. Original approval SHA and the publish/withdraw chain remain unchanged; tasks
are not duplicated. Evidence collection did not execute the Founder's decisions.

The only synthetic boundary was external acquisition/model output. This does
not validate real ASR/semantic reanalysis, remote providers, production readiness,
media rights, Pattern Approval or Profile Compatibility. Cases are structural
references, never Customer Truth or automatically eligible production assets.
News retains its existing fail-closed consumer boundaries.

CASE feature development stops at this candidate. A future P0/P1 regression
requires an explicit defect scope and fresh validation. Customer/Speaker Founder
UAT proceeds separately without modifying this frozen candidate.
