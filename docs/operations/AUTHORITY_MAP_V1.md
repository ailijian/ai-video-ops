# Authority Map V1

CASE-SHARE-UX-2 retains separate Case Approval and Shared Display Authority.
`case_shared_display.py` owns source-bound preview v1.0 and Publication v1.1 with
Human display decision v1.0; `review_commands.py` coordinates explicit final Human
command v1.2 and share-result v1.0. See [Case Library Access](../design/CASE_LIBRARY_ACCESS_V1.md).
Neither the joint action nor its execution result grants media or production rights.

**Status:** Approved Operations Reference
**System Authority:** [AI Video Ops MVP V1 Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)

This map records existing owners and consumers. It introduces no new business authority.

## Customer restriction contract amendment — 2026-10-10

Founder / Architecture verdict: `E2_A_CONTRACT_AMENDMENT_APPROVED_FOR_IMPLEMENTATION`.
Machine owner: `ops-pipeline/scripts/customer_constraints_v1.py`, contract
`business-restriction-v1.0`. Existing Intake / Fact Candidate
`derived_authority_constraints` / Human Review / Persona control layer own the
records; this shared validator/resolver writes no parallel Authority.

Types: `publication_prohibition`, `unverified_claim`, `identity_conflict`,
`conditional_fact`. Typed Human actions: `confirm`, `exclude`, `defer`,
`dismiss`, `resolve`. Ordinary fact `approve/edit/reject` cannot review a
restriction. Exact raw answer SHA/quote, candidate SHA, authenticated actor,
time and immutable review intent bind each decision. Resolution quotes are
mapped locally into full source references; original records never change.

Unknown type/scope/source fail closed. Identity conflicts have business scope;
claim restrictions cannot downgrade them. Excluded unverified claims remain
outside Known Truth while independent facts may pass approval. Pending or
deferred restrictions block approval; confirmed prohibitions and conditions
remain production controls. A new critical Intake temporarily restricts current
production without revoking or rewriting Approved R1. Resolution targets bind
one exact ID/hash/source; unrelated Known supplements resolve nothing.
Legacy IDs may repeat across Intakes: resolution matches the ID, Intake ID,
Raw Answers SHA and constraint SHA together, never the ID alone.

Consumers: Business builder/approval/current resolver; Console creation options
and entry; canonical creation/capacity; Fact Atoms; source matching; Mix plan,
generation/revision/review/export/closure. Mix omits excluded facts, rejects
blocked claims and requires applicable original conditions. Novel News preview,
generation/review/export and News repurpose are explicitly blocked when this
new control contract is present until their validators support it. Legacy
Speaker controls and legacy Persona hash serialization remain unchanged.

Runtime artifact paths below are relative to `ops-pipeline/`. The [Knowledge Index](README.md) routes human intent and [machine sources](README.md#machine-sources) by scope. Writers listed here identify current implementation and compatible historical paths; their fields and validation remain owned by the code. Formal writes on a running production node use the Console gateways and locks described in the [RUNBOOK](RUNBOOK.md).

### Customer exception review amendment — 2026-10-10

Founder / Architecture verdict: `CS_E2_UX_UX1_CONTRACT_APPROVED_FOR_IMPLEMENTATION`.
`customer_constraints_v1.py` owns `restriction-amendment-v1.0` inside the existing
typed Human Decision. Original candidate/control/source SHA stays immutable;
source-backed effective control is derived by the same collector and production
policy. Core conflicts still require the explicit resolution gate. Unsupported
fields, missing evidence and unsupported weakening are rejected.

`customer_fact_review_v1.py` owns `customer-fact-review-progress-v1.0` receipts
under the same Intake's `review_progress/`. Each immutable increment binds exact
candidate/source SHA, actor/time, operation identity and parent receipt SHA.
Unsubmitted candidates remain Pending; the merged projection is canonical,
not SQLite. Complete Fact Review still requires full coverage and is distinct
from Persona Approval. Historical complete-review files retain their old format
and SHA; a new batch cannot overwrite an existing decision.

Console `customer_gateway.py` signs actor/node-bound review contexts and validates
the current candidate/review/constraint/Persona snapshot inside the Business lock.
Exact committed replay is allowed; stale or borrowed contexts are rejected.
Durable receipt recovery resumes subsequent derived writes without claiming a
multi-file atomic transaction. UI preselection is pending selection only, and
Speaker Human Review, shared-customer access and News fail-closed remain unchanged.

## Authority domains

### Legacy unscoped critical scope adjudication — 2026-10-16

Founder approved `CS-LEGACY-SCOPE-1` implementation. The existing Business
restriction owner `customer_constraints_v1.py` delegates immutable receipt
validation to `legacy_constraint_scope_v1.py`, contract
`legacy-constraint-scope-adjudication-v1.0`. This is neither resolution nor a
restriction edit. Only exact, untyped, unscoped legacy conflicts with supported
historical excluded-claim Human Review and independent approved Persona evidence
are eligible. Typed identity conflicts cannot use it.

Decisions are `external_claims_only`, `core_identity_unresolved`, and default
`insufficient_evidence`. Each receipt binds the four-part legacy target, frozen
source/review/Business/Speaker hashes, stable local principal, explicit grant,
reason, time, operation identity, and parent receipt SHA. Relationships remain
unresolved. B/C retain Business blocking. A derives active publication controls
from the same owner; it never changes the old record or Persona/Approval SHA.
Receipts live inside the original Intake at
`data/customer_intakes/<business>/<intake>/legacy_scope_adjudications/`, never as
a sibling directory that could be mistaken for a newer Intake.
Unsupported historical review layouts fail closed rather than inferring scope.

The narrowly scoped `business_legacy_scope_reviewer` capability is explicitly
granted/revoked by trusted local maintenance under an operation lock. Immutable
`business-legacy-scope-capability-v1.0` events live at
`data/customer_governance/legacy_scope_reviewers/<namespace>/<user_id>/`.
There is no HTTP grant endpoint and existing Business/Case approval rights are
unchanged. The Console rechecks the active Session principal and current grant
inside the Business lock; the canonical writer independently checks them again.
No production grant or adjudication is implied by contract implementation.

Resolver, Truth/Capacity, source matching, Mix generation/revision/review/export
and Closure consume the same effective publication restrictions. Model context
contains safe control fields, never restriction source quotes or raw review
evidence. Source-bound exclusions and conservative relationship/rent guards do
not establish any external relationship. Remaining production gates still apply;
News consumers remain unsupported and fail closed. Future Persona evidence
changes invalidate the snapshot-bound adjudication until reviewed again.

| Domain | Question answered | Authority owner |
|---|---|---|
| Customer Truth | What is true about this customer and speaker? | Current Approved Business Persona + Current Approved Speaker Persona |
| Historical Content Truth | What has this business already communicated? | One business-wide Content Ledger + Communicated Information Units |
| Creative Knowledge | Which approved structures may express the content? | Approved Patterns + Approved Case structural references |
| Production Evidence | Can a production asset satisfy a visual requirement? | Production Asset + Rights + Privacy + Event Relationship + Requirement Match |

## Concrete authorities

| Authority | Canonical artifact / resolver | Writer | Consumers | Human Gate | Historical representation |
|---|---|---|---|---|---|
| Business Persona | `data/personas/<business_id>/revision_*/persona_v1.json`; `show_customer_status_v1.py` resolves explicit approved revision lineage | Console Customer fact review through `customer_fact_review_v1.py` / `build_persona_v1.py`, then explicit `approve_persona_v1.py` | Planning, matcher, generation, status read model | Customer Truth Approval | Older approved revisions and receipts remain immutable |
| Speaker Persona | `data/personas/<speaker_id>/revision_*/persona_v1.json`, bound to an exact Business Persona revision/SHA | Console Speaker fact review through `speaker_fact_review_v1.py` / `build_persona_v1.py`, then explicit `approve_persona_v1.py` | Matcher, generation, capacity, status read model | Customer Truth Approval; discovered drafts are not approval | Older approved speaker revisions and receipts |
| Content Ledger | `data/content_ledgers/<business_id>/content_ledger_v1.json` | Shared `content_quality_v1.py` functions; Mix `close_generation_export_v1.py`; Novel News `novel_news_v1.py`; repurpose presentation closure in `news_delivery_v1.py` | Novelty, capacity, planning, batch resolver, status read model | Approved/exported content precondition | Append-only semantic entries and presentation history; repurpose creates no new semantic entry |
| Approved Patterns | `data/patterns/approved/<pattern_id>/pattern_v1.json` | `approve_pattern_v1.py` | Source matcher and generation | Pattern Approval | Candidates, rejected hypotheses, receipts |
| Approved Cases | `data/cases/<case_id>/case_v1.json` with receipt and source-governance companion | `case_analysis_v1.py` orchestrates evidence and `build_case_v1.py`; only `approve_case_v1.py` applies approval | Structural research, fingerprints, matcher | Case Research Approval | `data/case_analysis_attempts/**` structured evidence, source acquisition/SHA lineage, prior attempts, cleanup and approval receipts; raw source media and pixel frames are transient |
| Approved Mix Batch | Console: `data/generation_batches/<request_id>/approved_generation_batch_v1.json` with approval receipt; historical revision layouts remain lineage-bound inputs | Console `content_delivery_gateway.py` invokes `review_generation_batch_v2.py`; V1 approver remains for compatible historical/offline review inputs | Export, ledger, footage planning, status read model | Item-level Human Review V2; approved subset only | Immutable generated candidate, V2 review, rejected items, old approved batches and revision layouts |
| Approved Novel News | `data/generation_batches/<request_id>/approved_novel_news_v1.json`, bound to its beat plan and Human review | Console `novel_news_gateway.py` invokes explicit review in `novel_news_v1.py` | Novel News export, semantic Ledger closure and status projection through validated export lineage | Human beat review; Scene Contrast additionally needs controlled-validation approval | Unapproved beat plan, Human decisions, export receipt and closure retained separately |
| Production Profile / Creative Compatibility | `data/production_profiles/production_profile_registry_v1.json`, SHA-bound coverage and compatibility approval artifacts | Registry/coverage structure in `production_profile_v1.py`; explicit compatibility approval in `approve_production_profile_compatibility_v1.py` | Feasibility, matcher, source planning and export | Compatibility approval where required; no approval from operator profile hints | Prior research/coverage and approval lineage; Shared Authority release manifest is a portable provenance record |
| Subject Media Authorization | `data/production_footage/<request_id>/subject_media_use_confirmation_v1.json` | Explicit Human rights confirmation workflow | Production asset eligibility and coverage | Media / Rights Confirmation | Batch-scoped confirmation records |
| Production Asset Eligibility | Registered Production Asset metadata plus inventory/match artifacts under the batch-bound footage plan | Production footage inventory and eligibility functions | Storyboard coverage | Rights/privacy confirmation as required | Inventory/match revisions; no Case Media promotion |
| Privacy Projection | `data/privacy/*`; `privacy_projection_v1.py` rules | `build_privacy_projection_v1.py` | Case and production boundary checks | Review where projection requires it | Per-source projections and validation evidence |
| Proof Boundary | Approved Customer Truth plus explicit asset event relationship and requirement match | No independent proof writer | Footage match, storyboard coverage, final review | Human proof/claim review | Requirement, match and reason-code artifacts |

## Non-authorities

- Raw intake, Fact Candidate, AI extraction, Case facts, operator hints, capture missions, and status read-model output do not own Customer Truth.
- Customer save-only identity, industry suggestions, and Speaker discovery intent are intake records, not approved facts. Additive Business updates retain the previous approved revision until a separate approval of the new candidate. `data/speaker_revalidations/<speaker_id>/business_revision_NNNN/speaker_revalidation_review_v1.json` records explicit Human reuse of unchanged personal evidence against an exact new Business SHA; it does not approve the resulting Speaker revision or grant media rights. [Console contracts](../../internal-console/README.md#customer-and-speaker-smart-intake) route these writers and recovery actions.
- Initial Customer/Speaker onboarding may use one explicit final Human action over complete, source-bound previews. `speaker_review_preparation_v1.py` prepares unapproved personal proposals; `customer_speaker_confirmation.py` coordinates the existing Fact Review and Persona Approval owners with separate Business/Speaker decisions and receipts. Preparation and task completion are not Human approval. The joint operation preserves exact Approved Business binding, current actor, source SHA and idempotent recovery; historical or independently approved records are not reinterpreted as a joint decision. Existing Speaker-version revalidation and media/production gates remain independent.
- Approval receipts prove that a gate occurred; they do not replace the approved artifact.
- Operational Controls own only whether an operator action is paused. They do not own Persona, Content, Batch, Footage, Rights, or Proof lifecycle.
- Internal Console tasks own execution status only. `queued`, `running`, `awaiting_review`, and `failed` never replace Case lifecycle or Human approval.
- Case shared display is separate from Case Approval: `case_shared_display.py` owns SHA-bound, append-only `case-shared-display-v1.0` publish/withdraw companions and whitelist projections. Explicit display clearance grants no source-video download, Production Asset Rights, Pattern or Compatibility. Old approvals are unpublished by default. See [Case Library Access V1](../design/CASE_LIBRARY_ACCESS_V1.md).
- Human Case evidence edits/revisions, effective candidate resolution and final v2 coverage belong to [`case_evidence_revision_v1.py`](../../ops-pipeline/scripts/case_evidence_revision_v1.py). Saved/failed edits do not confer approval; immutable source lineage, current reviewer authority, explicit high-risk handling and existing quality/Approval Gates remain mandatory. See the same Case Library Access owner for compatibility and execution boundaries.
- Case Console approval uses an explicit local principal capability. Migration 005 owns the immutable node namespace and capability event store; Pipeline `case_console_authorization_v1.py` independently validates current grants. HTTP derives its actor from Session, never request input. Trusted offline maintenance remains a distinct OS authority path; no change to historical reviewer/Receipt SHA. Exact authenticated Task/Group relationships scope private Case Attempts and media; missing lineage remains reviewer-only.
- Novel News opportunity previews and feature-rollout settings do not own Customer Truth, semantic novelty, approval, or real-customer validation. Novel News approved content is distinct from a Mix Approved Batch and from historical-content repurpose; its presentation entry references separately recorded semantic content.
- Local source-video existence and remote Douyin playback are not Approved Case Authority. Source traceability is the canonical URL, stable platform video ID, recorded source-media SHA-256, retained metadata, and acquisition lineage.
- `data/case_governance/cases/<case_id>/case_profile_annotation_v1.json` and the industry annotation companion record human label additions/corrections bound to the exact Approved Case SHA-256. Submission metadata, human labels and system observations remain distinct. Saving requires the existing Case lock and matching Case/annotation hashes; no automatic backfill or Case/receipt/fingerprint/compatibility rewrite occurs.
- `data/case_analysis_attempts/<case_id>/<attempt_id>/case_classification_review_v1.json` records the original evidence-derived suggestion and independent human classification choices/history. Its Console writer owns operator labels only. Classification is never Case Approval, Compatibility Approval, Customer Truth, Proof or media rights. SQLite intake groups reference tasks for UI recovery only.


## Snapshot-bound review closure — 2026-10-17

The Console [review protocol](../../internal-console/README.md#review-closure-and-targeted-corrections)
binds every final approval/rejection/reanalysis to its displayed actor/object/SHA.
[`human_review_operations_v1.py`](../../ops-pipeline/scripts/human_review_operations_v1.py)
provides immutable append-only command companions; SQLite remains execution-only.
[`persona_review_lifecycle_v1.py`](../../ops-pipeline/scripts/persona_review_lifecycle_v1.py)
owns targeted correction Intakes, supersession of explicitly reviewed fact fields,
and SHA-bound disposition of returned **unapproved** candidates. Neither companion
can hide Approved Persona, alter a historical receipt, resolve restrictions or
approve a replacement. `approve_persona_v1.py` retains final Authority and adds
exact-decision write recovery. Current role/binding/production gates still apply.
Historical records without these companions keep their original resolution rules.
