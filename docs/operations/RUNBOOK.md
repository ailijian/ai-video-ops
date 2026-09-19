# AI Video Ops MVP V1 — Operations RUNBOOK

**Status:** Canonical Operations Entry
**System Authority:** [Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)

Run commands from the repository root. Replace angle-bracket placeholders with explicit reviewed paths. Never select an authority by file timestamp or filename sorting.

## LOCAL_PRODUCTION_NODE_RUNTIME

- **Runtime Freeze:** Internal Console listens on `127.0.0.1:8000`, uses exactly one Uvicorn worker, and never enables reload in production.
- **Production Command:** From `internal-console`, run `& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips "127.0.0.1,::1"` with `AIVO_ENV_FILE` pointing to the protected production env file.
- **Reason:** Task scheduling and startup recovery use a single-process service architecture. SQLite CAS and cross-process operation locks are defensive guards, not authorization to start multiple Console instances.
- **Execution Lanes:** `GPU_HEAVY` contains Case Analysis/local model work; `STANDARD_BACKGROUND` contains Customer/Speaker Analysis, Content Plan, Script Generation, Mix/News Plan and Export, and other long non-GPU work.
- **GPU Guard:** Every canonical Ollama/CUDA entry acquires `global_gpu`; production GPU concurrency is one. Historical `merge_video_evidence.py` and any other unregistered GPU tool are **DO NOT RUN CONCURRENTLY WITH PRODUCTION NODE**.
- **Long Operations:** Content Plan, Script Generation, Mix Export + Ledger Closure, News Plan and News Export are submitted as durable tasks. `completed` is execution projection only; always re-read the canonical delivery/receipt resolver.
- **Actor:** Console mutations derive reviewer/actor from the authenticated session. Request bodies do not choose reviewer identity.
- **Mutation Boundary:** While the Local Production Node is running, formal Authority mutations go through the Console gateways and keyed `operation_lock_v1`. Direct mutation CLIs are offline recovery tools only: stop/idle the Console first and **DO NOT RUN CONCURRENTLY WITH PRODUCTION NODE**.
- **Recovery:** Startup reconciles only expired leases; a low-frequency in-process maintenance loop revisits non-expired inherited leases after they expire, so a fast reboot cannot strand them permanently in `running`.
- **Backup:** Run `internal-console/scripts/backup_local_node_v1.py` during an idle queue window to an external/NAS path. A running task or active Authority mutation holds the backup barrier and produces `BACKUP_REQUIRES_IDLE_WINDOW`.
- **Windows Checklist:** AC sleep and hibernate Never; screen may turn off; disable active-adapter power saving; prefer wired networking; prevent automatic update reboot during production hours; maintenance only after the queue is idle.
- **Deployment Boundary:** Templates in `deploy/local-node` do not authorize installation, FRP setup, firewall changes, public exposure, or changes to Windows policy.
- **Two-host Responsibility:** Until an explicit Authority cutover, the old Windows host owns development and current Production Authority. The RTX 4090 host is runtime-only staging and must not contain direct business-code edits, commits, or pushes.
- **Code Promotion:** Every runtime change moves `old host -> reviewed commit -> private-origin push -> new host git pull`. Never repair Production by hand-editing canonical code on the runtime node.
- **Reproducible Install:** On a clean Python 3.12 host, `deploy/local-node/powershell/bootstrap-runtime.ps1` creates/reuses both venvs from `internal-console/pyproject.toml` and `ops-pipeline/requirements.txt`; `-IncludeTestDependencies` also installs both declared test contracts. Then run `runtime-preflight.ps1` against the protected environment file.
- **Whisper Runtime:** `AIVO_WHISPER_MODEL` accepts a faster-whisper model name or an existing absolute local model directory. The 4090 node uses `E:\ai-model-cache\faster-whisper-large-v3`; transcription remains CPU/int8 and the bootstrap never downloads or invokes the model.

## CASE_ANALYSIS

- **Goal:** Turn one full public Douyin video URL into a traceable, review-required Case Candidate by orchestrating the current acquisition, transcription, visual evidence, privacy, shot-boundary, storyboard, and Case-build implementations.
- **Required Inputs:** Full URL containing a stable Douyin video ID; immutable attempt ID; observed profile (`mix` or `news`) and industry label.
- **Authority Preconditions:** Duplicate Case IDs and active/review-ready attempts fail closed. Source acquisition does not grant media rights. Every remote-model input passes through the existing Privacy Projection boundary.
- **Canonical Entry Point:** `ops-pipeline/scripts/case_analysis_v1.py`.
- **Execution:** `ops-pipeline/.venv/Scripts/python.exe ops-pipeline/scripts/case_analysis_v1.py --source-url <full_douyin_video_url> --attempt-id <immutable_attempt_id> [--profile mix|news] [--industry <label>] [--reanalyze]`
- **Recovery:** Re-run the exact command with the same attempt ID. Completed artifact checkpoints are validated and reused; progress remains in `data/case_analysis_attempts/<case_id>/<attempt_id>/case_analysis_attempt_v1.json`.
- **Storage Retention:** Only after all structured evidence and the Case Candidate validate and the Attempt is durably `awaiting_review`, `storage_retention_v1.py` immediately removes source video/music/cover plus original and Qwen proxy frames. It retains source URL, stable video ID, acquisition/metadata lineage, recorded media SHA-256, structured evidence, logs and `storage_cleanup_receipt_v1.json`. Cleanup failure records `retry_required` and never changes successful Case Analysis into a business failure.
- **Failed Attempts:** Queued/running Attempts are never cleaned. Failed/interrupted Attempts retain transient media for 24 hours; the hourly Console storage-maintenance pass then cleans terminal failures. Human Reject cleans immediately. Reanalysis reacquires from the retained canonical source URL when local media is absent.
- **Human Gate:** Required. Successful analysis stops at `awaiting_review`; this operation never calls `approve_case_v1.py`.
- **Outputs:** Immutable attempt lineage, source-acquisition receipt, existing canonical evidence artifact types, and one review-required `case_v1.json` under the attempt directory.
- **Stop Conditions:** Duplicate Case/attempt, ambiguous source identity, privacy failure, unresolved narration/boundary sub-review, invalid lineage, or any canonical stage failure.
- **Next Action:** Human Case Review, then explicit `APPROVE_CASE`; rejection and reanalysis remain separate reviewed attempts.
- **Implementation Status:** `IMPLEMENTED / RECOVERABLE ORCHESTRATION`.

## APPROVE_CASE

- **Goal:** Explicitly admit one reviewed Case Candidate to the canonical Case Library without changing source-media rights.
- **Required Inputs:** Review-required Case Candidate, Human reviewer, decision note, canonical source URL, stable platform video ID, recorded source-media SHA-256, retained source metadata and valid acquisition lineage. A local source-video file is optional.
- **Authority Preconditions:** Case validation and privacy gate pass; canonical Approved Case cannot be overwritten; Case Source Governance companion keeps `media_reuse_rights=not_established` and `production_footage_pool_eligible=false`.
- **Canonical Entry Point:** `ops-pipeline/scripts/approve_case_v1.py`, invoked through the Internal Console's fixed Case approval gateway; deterministic fingerprint follows approval.
- **Human Gate:** Required and explicit. Analysis completion is never approval.
- **Outputs:** Approved `data/cases/<case_id>/case_v1.json`, approval receipt, Case Source Governance companion, and deterministic Case fingerprint.
- **Stop Conditions:** Existing Approved Case, source-governance ambiguity, missing URL/stable ID/recorded SHA/acquisition lineage, invalid privacy/proof checks, or failed canonical approval. Missing local source media alone is not a blocker.
- **Next Action:** Approved Case Library.
- **Implementation Status:** `IMPLEMENTED / EXPLICIT HUMAN OPERATION`.

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
- **Canonical Entry Point:** Internal Console generation gateways backed by `generation_request_handoff_v1.py`, `resolve_generation_source_plan_v1.py`, `resolve_generation_content_plan_v1.py`, `resolve_generation_batch_v1.py`, `review_generation_batch_v2.py`, `export_mix_excel_v1.py`, and `close_generation_export_v1.py`.
- **Execution:** Generation Request → Source Plan → Content Plan → Generation → Human Review V2 → Export → Ledger Closure. Content Plan, Generation and Export are durable `STANDARD_BACKGROUND` tasks; Human Review remains explicit and synchronous because it is deterministic artifact validation/mutation.
- **Human Gate:** Generated content is not approved; content review follows.
- **Outputs:** Generation batch and review pack.
- **Stop Conditions:** `capacity_limited`, unsupported fact, privacy/proof failure, or no approved pattern.
- **Next Action:** `CONTENT_HUMAN_REVIEW`.
- **Implementation Status:** `IMPLEMENTED / CONSOLE-ORCHESTRATED / RECOVERABLE`.

## NEW_NEWS_BATCH

- **Goal:** Execute the currently validated narrow Price / Offer Cross-profile Repurpose production path.
- **Required Inputs:** Explicit novel/repurpose requests, registry, active coverage update, approved News patterns, historical approved Mix/export lineage, fingerprints and template.
- **Authority Preconditions:** News price pattern approved; Scene Contrast requires real Customer Truth opportunity.
- **Canonical Entry Point:** Internal Console News Delivery gateway backed by `news_delivery_v1.py`.
- **Execution:** News Request → deterministic News Plan task → Human Review → News Export task → Presentation History Closure. The validated path repurposes approved historical semantic content and creates no new semantic Ledger entry.
- **Human Gate:** Track A/Track B Human approval before final export.
- **Outputs:** Validation artifacts, approved repurpose export, presentation-only ledger history.
- **Stop Conditions:** No approved source content; request/receipt mismatch; any attempt to claim new semantic novelty from repurpose.
- **Next Action:** Complete explicit review/export for Price / Offer repurpose. Scene Contrast remains `pending_real_customer_opportunity` and is not Generic Novel News Production Ready.
- **Implementation Status:** `IMPLEMENTED / NARROW PRICE-OFFER CROSS-PROFILE REPURPOSE`; Scene Contrast remains pending.

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
- **Canonical Entry Point:** Internal Console async export task, backed by `ops-pipeline/scripts/export_mix_excel_v1.py` and `close_generation_export_v1.py`.
- **Execution:** Submit `/api/create/<request_id>/export-mix`, poll the returned task, then re-read canonical delivery state and Export Receipt. CLI recovery uses the same scripts and request lineage.
- **Human Gate:** Approved Batch required.
- **Outputs:** XLSX, preview, validation and export receipt.
- **Stop Conditions:** Template mutation, formula error, overwrite attempt, contract mismatch.
- **Next Action:** `WRITE_CONTENT_LEDGER`.
- **Implementation Status:** `IMPLEMENTED / ASYNC CONSOLE TASK / LEDGER CLOSURE INCLUDED`.

## EXPORT_NEWS

- **Goal:** Export an explicitly approved News result.
- **Required Inputs:** News Human approval, template, new output/preview/validation paths.
- **Authority Preconditions:** Approval schema and `approved_for_export` status validate.
- **Canonical Entry Point:** Internal Console async News Export task backed by `news_delivery_v1.py --action export`.
- **Execution:** Submit `/api/create/news/<request_id>/export`, poll the task, then re-read News Delivery state, receipt and Presentation History Closure.
- **Human Gate:** Explicit News content approval.
- **Outputs:** News XLSX, preview and validation; final closure writes receipt/presentation history.
- **Stop Conditions:** Approval, workbook or template validation failure.
- **Next Action:** Customer-specific final closure.
- **Implementation Status:** `IMPLEMENTED / NARROW REPURPOSE PATH / ASYNC CONSOLE TASK`.

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
