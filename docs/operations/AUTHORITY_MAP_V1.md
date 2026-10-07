# Authority Map V1

**Status:** Approved Operations Reference
**System Authority:** [AI Video Ops MVP V1 Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)

This map records existing owners and consumers. It introduces no new business authority.

Runtime artifact paths below are relative to `ops-pipeline/`. The [Knowledge Index](README.md) routes human intent and [machine sources](README.md#machine-sources) by scope. Writers listed here identify current implementation and compatible historical paths; their fields and validation remain owned by the code. Formal writes on a running production node use the Console gateways and locks described in the [RUNBOOK](RUNBOOK.md).

## Authority domains

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
- Approval receipts prove that a gate occurred; they do not replace the approved artifact.
- Operational Controls own only whether an operator action is paused. They do not own Persona, Content, Batch, Footage, Rights, or Proof lifecycle.
- Internal Console tasks own execution status only. `queued`, `running`, `awaiting_review`, and `failed` never replace Case lifecycle or Human approval.
- Novel News opportunity previews and feature-rollout settings do not own Customer Truth, semantic novelty, approval, or real-customer validation. Novel News approved content is distinct from a Mix Approved Batch and from historical-content repurpose; its presentation entry references separately recorded semantic content.
- Local source-video existence and remote Douyin playback are not Approved Case Authority. Source traceability is the canonical URL, stable platform video ID, recorded source-media SHA-256, retained metadata, and acquisition lineage.
- `data/case_governance/cases/<case_id>/case_profile_annotation_v1.json` is a historical operator hint, bound to the exact approved Case SHA-256. It records the authenticated annotator and never rewrites the Case, receipt, fingerprint, or generation compatibility. Submission metadata remains primary; historical annotations and system observations are displayed separately. Saving requires the existing Case lock and matching Case/annotation hashes; no automatic backfill occurs.
