# AI Video Ops MVP V1 — Operations RUNBOOK

**Status:** Canonical Operations Entry
**System Authority:** [Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)

Run commands from the repository root. Replace angle-bracket placeholders with explicit reviewed paths. Never select an authority by file timestamp or filename sorting.

## NEW_CUSTOMER

- **Goal:** Create approved Customer Truth for a new business and speaker.
- **Required Inputs:** Interview/raw intake followed by Human-reviewed persona inputs.
- **Authority Preconditions:** Raw input and Fact Candidates are not Production Authority.
- **Canonical Entry Point:** Intake functions in `customer_intake_v1.py`, then the Persona build/approval CLIs below.
- **Execution:** No generic end-to-end intake CLI exists. Do not use `--run-stage-a` as a generic real-customer command. Continue with `BUILD_PERSONA` only after reviewed inputs exist.
- **Human Gate:** Fact review and Customer Truth Approval.
- **Outputs:** Approved Business Persona, Approved Speaker Persona, receipts.
- **Stop Conditions:** Any unresolved or `requires_review` fact; ambiguous business/speaker binding.
- **Next Action:** `CHECK_CONTENT_CAPACITY`.
- **Implementation Status:** `PARTIAL / MULTI_STEP_OPERATION`.

## BUILD_PERSONA

- **Goal:** Build one immutable review-required Persona revision.
- **Required Inputs:** Reviewed persona input; previous approved persona for revision > 1; approved Business Persona for speaker scope.
- **Authority Preconditions:** Inputs must contain only allowed fact authority.
- **Canonical Entry Point:** `ops-pipeline/scripts/build_persona_v1.py`.
- **Execution:** `python ops-pipeline/scripts/build_persona_v1.py --input <persona_input.json> [--previous-persona <persona_v1.json>] [--business-persona <approved_business_persona.json>] [--output-root <directory>]`
- **Human Gate:** None in build; output remains review-required.
- **Outputs:** `persona_v1.json` plus review material.
- **Stop Conditions:** Invalid lineage, overwrite attempt, missing Business Persona binding.
- **Next Action:** `APPROVE_PERSONA`.
- **Implementation Status:** `IMPLEMENTED`.

## APPROVE_PERSONA

- **Goal:** Apply explicit Human Customer Truth Approval.
- **Required Inputs:** Review-required Persona, reviewer, decision note.
- **Authority Preconditions:** Persona validation passed; content hash and prior revision lineage valid.
- **Canonical Entry Point:** `ops-pipeline/scripts/approve_persona_v1.py`.
- **Execution:** `python ops-pipeline/scripts/approve_persona_v1.py --persona <persona_v1.json> --reviewer <human> --note <decision_note>`
- **Human Gate:** Required and explicit.
- **Outputs:** Approved Persona and `approval_receipt.json`.
- **Stop Conditions:** Existing receipt, invalid content hash, unresolved fact authority.
- **Next Action:** `CHECK_CONTENT_CAPACITY`.
- **Implementation Status:** `IMPLEMENTED`.

## CHECK_CONTENT_CAPACITY

- **Goal:** Read current remaining high-quality semantic capacity.
- **Required Inputs:** Business ID with approved personas, canonical ledger and active exported batch lineage.
- **Authority Preconditions:** Persona approval receipts and ledger/batch hashes valid.
- **Canonical Entry Point:** Current read: `show_customer_status_v1.py`; builders remain in `content_quality_v1.py`.
- **Execution:** `python ops-pipeline/scripts/show_customer_status_v1.py --business-id <business_id> --format json`
- **Human Gate:** Capacity is derived; replenishment facts still require Human review.
- **Outputs:** Derived capacity projection; no persisted status.
- **Stop Conditions:** Authority ambiguity or capacity/ledger lineage mismatch.
- **Next Action:** Plan content when capacity exists; otherwise `CONTENT_REPLENISHMENT`. Never pad.
- **Implementation Status:** `PARTIAL` — no standalone generic capacity-build CLI.

## CONTENT_REPLENISHMENT

- **Goal:** Collect new information when semantic capacity is low.
- **Required Inputs:** Approved personas/receipts, ledger, content-gap report.
- **Authority Preconditions:** Existing Customer Truth and history remain immutable.
- **Canonical Entry Point:** `content_quality_v1.py --build-replenishment-intake`; current real closure flags in `customer_intake_v1.py`.
- **Execution:** `python ops-pipeline/scripts/content_quality_v1.py --build-replenishment-intake --business-persona <path> --business-approval <path> --speaker-persona <path> --speaker-approval <path> --content-ledger <path> --content-gap-report <path> --json-output <new.json> --markdown-output <new.md>`
- **Human Gate:** Interview/fact review and new Persona revision approval.
- **Outputs:** Replenishment intake; later approved Persona revision and capacity recalculation.
- **Stop Conditions:** Do not treat interview as historical exposure or candidate facts as truth.
- **Next Action:** Human interview/review, then `BUILD_PERSONA`.
- **Implementation Status:** `PARTIAL / MULTI_STEP_OPERATION`; current real closure is customer-specific.

## NEW_MIX_BATCH

- **Goal:** Produce a review-required Mix content batch.
- **Required Inputs:** Explicit approved Business/Speaker Personas, request, approved pattern/cases/fingerprints, profile registry/coverage/compatibility approval, business ledger.
- **Authority Preconditions:** All revisions and SHA lineage validate; request explicitly names persona revisions.
- **Canonical Entry Point:** `match_generation_sources_v1.py`, then `generate_mix_scripts_v1.py`.
- **Execution:** First run `python ops-pipeline/scripts/match_generation_sources_v1.py --persona <path> --speaker-persona <path> --request <path> --pattern <path> --case <path> --fingerprint <path> --profile-registry <path> --creative-coverage-report <path> --profile-compatibility-approval <path> --output-root <directory>`. Then run `python ops-pipeline/scripts/generate_mix_scripts_v1.py --persona <path> --speaker-persona <path> --request <path> --source-plan <path> --pattern <path> --fingerprint <path> --content-ledger <path> --output-root <directory>`.
- **Human Gate:** Generated content is not approved; content review follows.
- **Outputs:** Generation batch and review pack.
- **Stop Conditions:** `capacity_limited`, unsupported fact, privacy/proof failure, or no approved pattern.
- **Next Action:** `CONTENT_HUMAN_REVIEW`.
- **Implementation Status:** `IMPLEMENTED / MULTI_STEP_OPERATION`.

## NEW_NEWS_BATCH

- **Goal:** Validate the currently approved narrow News production paths.
- **Required Inputs:** Explicit novel/repurpose requests, registry, active coverage update, approved News patterns, historical approved Mix/export lineage, fingerprints and template.
- **Authority Preconditions:** News price pattern approved; Scene Contrast requires real Customer Truth opportunity.
- **Canonical Entry Point:** `generate_mix_scripts_v1.py --news-mvp-validation` and `--news-mvp-final-approval`.
- **Execution:** `CUSTOMER_SPECIFIC / VALIDATION_ONLY`; supply the corresponding `--novel-request`, `--repurpose-request`, `--production-profile-registry`, `--creative-coverage-update`, repeated `--news-pattern`, `--historical-approved-batch`, `--historical-export-receipt`, `--news-template`, and repeated `--fingerprint` arguments shown by `--help`.
- **Human Gate:** Track A/Track B Human approval before final export.
- **Outputs:** Validation artifacts, approved repurpose export, presentation-only ledger history.
- **Stop Conditions:** No real State A/B truth; zero novel capacity; any attempt to create semantic novelty from repurpose.
- **Next Action:** Preserve `pending_real_customer_opportunity` or complete the explicit review.
- **Implementation Status:** `PARTIAL / NARROW / CUSTOMER_SPECIFIC / VALIDATION_ONLY`.

## CONTENT_HUMAN_REVIEW

- **Goal:** Record item-level Human content decisions.
- **Required Inputs:** Immutable generation batch and complete Human review artifact.
- **Authority Preconditions:** Machine pass is not approval.
- **Canonical Entry Point:** Human review artifact contract consumed by `approve_generation_batch_v1.py`.
- **Execution:** Prepare the explicit review file; do not mutate the source batch.
- **Human Gate:** Required.
- **Outputs:** Review decision input for batch approval.
- **Stop Conditions:** Missing item decision or request/SHA mismatch.
- **Next Action:** `APPROVE_BATCH`.
- **Implementation Status:** `IMPLEMENTED / HUMAN_OPERATION`.

## APPROVE_BATCH

- **Goal:** Create an Approved Content Batch after Human review.
- **Required Inputs:** Generation batch and review file.
- **Authority Preconditions:** Request, item decisions and source SHA agree.
- **Canonical Entry Point:** `ops-pipeline/scripts/approve_generation_batch_v1.py`.
- **Execution:** `python ops-pipeline/scripts/approve_generation_batch_v1.py --batch <generation_batch_v1.json> --review-file <human_review.json>`
- **Human Gate:** Explicit content approval.
- **Outputs:** Approved/reviewed batch and approval receipt.
- **Stop Conditions:** Existing approved output, incomplete review, validation failure.
- **Next Action:** Profile-appropriate export.
- **Implementation Status:** `IMPLEMENTED`.

## EXPORT_MIX

- **Goal:** Export an Approved Mix Batch to the frozen workbook contract.
- **Required Inputs:** Approved batch, template, new output/preview/validation/receipt paths.
- **Authority Preconditions:** All export items Human Approved; output must not exist.
- **Canonical Entry Point:** `ops-pipeline/scripts/export_mix_excel_v1.mjs`.
- **Execution:** `node ops-pipeline/scripts/export_mix_excel_v1.mjs --batch <approved_batch.json> --template <template.xlsx> --output <new.xlsx> --preview <new.png> --validation-output <new_validation.json> --receipt <new_receipt.json>`
- **Human Gate:** Approved Batch required.
- **Outputs:** XLSX, preview, validation and export receipt.
- **Stop Conditions:** Template mutation, formula error, overwrite attempt, contract mismatch.
- **Next Action:** `WRITE_CONTENT_LEDGER`.
- **Implementation Status:** `IMPLEMENTED`; Python exporter remains preserved compatibility/history.

## EXPORT_NEWS

- **Goal:** Export an explicitly approved News result.
- **Required Inputs:** News Human approval, template, new output/preview/validation paths.
- **Authority Preconditions:** Approval schema and `approved_for_export` status validate.
- **Canonical Entry Point:** `ops-pipeline/scripts/export_news_excel_v1.mjs` within the customer-specific final closure.
- **Execution:** `node ops-pipeline/scripts/export_news_excel_v1.mjs --approval <news_approval.json> --template <template.xlsx> --output <new.xlsx> --preview <new.png> --validation-output <new_validation.json>`
- **Human Gate:** Explicit News content approval.
- **Outputs:** News XLSX, preview and validation; final closure writes receipt/presentation history.
- **Stop Conditions:** Approval, workbook or template validation failure.
- **Next Action:** Customer-specific final closure.
- **Implementation Status:** `IMPLEMENTED EXPORTER / CUSTOMER_SPECIFIC CLOSURE`.

## WRITE_CONTENT_LEDGER

- **Goal:** Record approved/exported semantic history once.
- **Required Inputs:** Canonical business ledger, approved batch, validated export and lineage artifacts.
- **Authority Preconditions:** Content approval and export validation complete.
- **Canonical Entry Point:** Ledger functions in `content_quality_v1.py`; current closure in `generate_mix_scripts_v1.py --post-replenishment-export-ledger-close`.
- **Execution:** `CUSTOMER_SPECIFIC`: `python ops-pipeline/scripts/generate_mix_scripts_v1.py --post-replenishment-export-ledger-close --content-ledger <ledger.json> --mix-export <export.xlsx> --mix-export-validation <validation.json>`.
- **Human Gate:** Upstream Content Approval; closure validation.
- **Outputs:** Updated business-wide ledger, lineage audit, post-export capacity.
- **Stop Conditions:** Hash mismatch, duplicate append, unapproved/unexported content.
- **Next Action:** `FOOTAGE_PLANNING` or capacity replenishment.
- **Implementation Status:** `PARTIAL / CLOSURE_COUPLED`.

## FOOTAGE_PLANNING

- **Goal:** Convert an Approved Batch into visual requirements, capture missions and coverage.
- **Required Inputs:** Explicit Approved Batch, output directory and workspace root.
- **Authority Preconditions:** Approval receipt and batch hash valid; Case Media remains excluded.
- **Canonical Entry Point:** `ops-pipeline/scripts/production_footage_v1.py`.
- **Execution:** `python ops-pipeline/scripts/production_footage_v1.py --approved-batch <approved_batch.json> --output-dir <new_batch_footage_dir> --workspace-root ops-pipeline [--human-review-closure --reviewer <human>]`
- **Human Gate:** Planning approval; media rights remain separate.
- **Outputs:** Requirements, inventory, matches, missions, capture pack, coverage, summary.
- **Stop Conditions:** Existing outputs, invalid batch, rights/proof boundary failure.
- **Next Action:** Review/approve plan, then obey Operational Hold before customer contact.
- **Implementation Status:** `IMPLEMENTED`; current real path is customer-specific validation.

## CHECK_FOOTAGE_COVERAGE

- **Goal:** Read batch-bound registered asset and coverage status.
- **Required Inputs:** Business ID and uniquely resolved active batch.
- **Authority Preconditions:** Footage artifacts must reference the Approved Batch request and SHA.
- **Canonical Entry Point:** `show_customer_status_v1.py`; coverage builder is inside `production_footage_v1.py`.
- **Execution:** `python ops-pipeline/scripts/show_customer_status_v1.py --business-id <business_id>`
- **Human Gate:** Rights review for identifiable media.
- **Outputs:** Registered/eligible counts and covered/capture-required projection.
- **Stop Conditions:** Footage/batch lineage ambiguity.
- **Next Action:** Capture/customer input, or Production Package when later implemented.
- **Implementation Status:** `PARTIAL` — no standalone coverage-build CLI; no real-asset validation yet.

## PRODUCTION_ASSET_INTAKE

- **Goal:** Register returned production assets with rights/privacy/event metadata.
- **Required Inputs:** Not yet productized.
- **Authority Preconditions:** Production Asset contract exists, but no canonical intake operation exists.
- **Canonical Entry Point:** None.
- **Execution:** Do not invent or manually simulate a production command.
- **Human Gate:** Media/rights confirmation will be required.
- **Outputs:** None through a canonical operation.
- **Stop Conditions:** Always stop until implementation is explicitly authorized.
- **Next Action:** `NOT_IMPLEMENTED`.
- **Implementation Status:** `NOT_IMPLEMENTED`.

## CHECK_CUSTOMER_STATUS

- **Goal:** Project Current Authority, blockers and one Primary Next Action without writes.
- **Required Inputs:** Business ID; optional speaker and batch IDs when needed to resolve ambiguity.
- **Authority Preconditions:** Existing approval, receipt and lineage artifacts.
- **Canonical Entry Point:** `ops-pipeline/scripts/show_customer_status_v1.py`.
- **Execution:** `python ops-pipeline/scripts/show_customer_status_v1.py --business-id <business_id> [--speaker-id <speaker_id>] [--batch-id <request_id>] [--format text|json]`
- **Human Gate:** None; this is a read model.
- **Outputs:** stdout only.
- **Stop Conditions:** Any hard Authority blocker; resolve it rather than guessing.
- **Next Action:** Exactly the projected Primary Next Action.
- **Implementation Status:** `IMPLEMENTED / READ_ONLY / DERIVED_ONLY`.

## OPERATIONAL_HOLD

- **Goal:** Explicitly pause or release operator execution/customer contact.
- **Required Inputs:** Business ID and actor; setting also requires a reason.
- **Authority Preconditions:** This control does not alter Customer Truth or production lifecycle.
- **Canonical Entry Point:** `ops-pipeline/scripts/operational_controls_v1.py`.
- **Execution:** Show: `python ops-pipeline/scripts/operational_controls_v1.py show --business-id <business_id>`. Set: `python ops-pipeline/scripts/operational_controls_v1.py set-hold --business-id <business_id> --actor <human> --reason <reason>`. Release: `python ops-pipeline/scripts/operational_controls_v1.py release-hold --business-id <business_id> --actor <human>`.
- **Human Gate:** Set/release are explicit Human operations; AI/system paths never auto-release.
- **Outputs:** `data/operations/<business_id>/operational_controls_v1.json`.
- **Stop Conditions:** Missing actor/reason, invalid metadata, already inactive release.
- **Next Action:** Active hold → `WAIT_FOR_OPERATOR_RELEASE`; released hold → recompute status.
- **Implementation Status:** `IMPLEMENTED`.
