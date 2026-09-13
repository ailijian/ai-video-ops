# Authority Map V1

**Status:** Approved Operations Reference
**System Authority:** [AI Video Ops MVP V1 Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)

This map records existing owners and consumers. It introduces no new business authority.

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
| Business Persona | `data/personas/<business_id>/revision_*/persona_v1.json`; `show_customer_status_v1.py` resolves explicit approved revision lineage | `build_persona_v1.py`, then `approve_persona_v1.py` | Planning, matcher, generation, status read model | Customer Truth Approval | Older approved revisions and receipts remain immutable |
| Speaker Persona | `data/personas/<speaker_id>/revision_*/persona_v1.json`, bound to an exact Business Persona revision/SHA | Same persona build/approval pair | Matcher, generation, capacity, status read model | Customer Truth Approval | Older approved speaker revisions and receipts |
| Content Ledger | `data/content_ledgers/<business_id>/content_ledger_v1.json` | Content-quality ledger closure functions | Novelty, capacity, planning, batch resolver, status read model | Approved/exported content precondition | Append-only semantic entries and presentation history |
| Approved Patterns | `data/patterns/approved/<pattern_id>/pattern_v1.json` | `approve_pattern_v1.py` | Source matcher and generation | Pattern Approval | Candidates, rejected hypotheses, receipts |
| Approved Cases | `data/cases/<case_id>/case_v1.json` with receipt and source-governance companion | `build_case_v1.py`, `approve_case_v1.py` | Structural research, fingerprints, matcher | Case Research Approval | Case evidence, prior attempts, approval receipts |
| Approved Batch | `data/generation_batches/<request_id>/revisions/<revision>/approved_generation_batch_v1.json` with approval receipt | `approve_generation_batch_v1.py` or explicit customer-specific closure | Export, ledger, footage planning, status read model | Content Approval | Old approved batches, rejected attempts, all revisions |
| Subject Media Authorization | `data/production_footage/<request_id>/subject_media_use_confirmation_v1.json` | Explicit Human rights confirmation workflow | Production asset eligibility and coverage | Media / Rights Confirmation | Batch-scoped confirmation records |
| Production Asset Eligibility | Registered Production Asset metadata plus inventory/match artifacts under the batch-bound footage plan | Production footage inventory and eligibility functions | Storyboard coverage | Rights/privacy confirmation as required | Inventory/match revisions; no Case Media promotion |
| Privacy Projection | `data/privacy/*`; `privacy_projection_v1.py` rules | `build_privacy_projection_v1.py` | Case and production boundary checks | Review where projection requires it | Per-source projections and validation evidence |
| Proof Boundary | Approved Customer Truth plus explicit asset event relationship and requirement match | No independent proof writer | Footage match, storyboard coverage, final review | Human proof/claim review | Requirement, match and reason-code artifacts |

## Non-authorities

- Raw intake, Fact Candidate, AI extraction, Case facts, operator hints, capture missions, and status read-model output do not own Customer Truth.
- Approval receipts prove that a gate occurred; they do not replace the approved artifact.
- Operational Controls own only whether an operator action is paused. They do not own Persona, Content, Batch, Footage, Rights, or Proof lifecycle.
