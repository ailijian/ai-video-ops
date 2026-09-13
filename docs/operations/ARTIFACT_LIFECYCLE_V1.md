# Artifact Lifecycle V1

**Status:** Approved Operations Reference
**System Authority:** [AI Video Ops MVP V1 Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)

These classifications describe the role of an artifact. They are not a new workflow state machine.

| Classification | Meaning | Typical repository examples |
|---|---|---|
| `CURRENT_AUTHORITY` | Current owner of a business or production fact | Current approved personas, business ledger, approved patterns/cases, approved batch, subject media confirmation, registered asset eligibility |
| `ACTIVE_DERIVED` | Recomputable projection currently used by operations | Content capacity/gap/plan, generation source plan, shot requirements, capture missions/pack, coverage, current status output |
| `HISTORICAL_IMMUTABLE` | Lineage, audit, diagnostic, or reproduction evidence that must not act as Current Authority | Old persona revisions, old batch revisions, rejected generation attempts, gate diagnostics, case evidence |
| `VALIDATION_RECEIPT` | Evidence that an approval/export/validation gate occurred | Persona/case/pattern/batch approval receipts, export receipts, lineage audits, validation summaries |
| `FIXTURE_TEST` | Test or architecture-validation data; never a real production input | `tests/fixtures/**`, Stage-A fixture customer trees, fixture exports |
| `DEPRECATED_CANDIDATE` | A replacement is known and all consumer, lineage, compatibility, and evidence checks permit future retirement | None confirmed in Consolidation Wave 0 |
| `UNKNOWN_HUMAN_REVIEW` | Retention or replacement cannot be decided safely without Human review | Python Mix exporter disposition, `merge_video_evidence.py`, zero-result discovery outputs |

## Preservation rules

- Historical is not Deprecated.
- An old revision is not a Delete Candidate.
- Approved Persona revisions and their receipts must be preserved.
- Old approved batches, rejected remote attempts, local revalidation attempts, and review packs must be preserved.
- V1/V1.1/V1.1.1 gate diagnostics must be preserved and must not override the effective content-gate resolver.
- Case evidence, frames, shots, fingerprints, source-governance companions, and approval history must be preserved.
- Pattern candidates and rejected hypotheses must be preserved as research history; only approved patterns are Production Authority.
- Approval and validation receipts must be preserved even though they do not create business truth.
- Fixture data must remain isolated from real production consumers.

## Current directory mapping

| Directory / artifact family | Typical classification |
|---|---|
| `data/personas/**/revision_*` | Current highest valid approved revision: `CURRENT_AUTHORITY`; prior revisions: `HISTORICAL_IMMUTABLE`; receipts: `VALIDATION_RECEIPT` |
| `data/content_ledgers/<business_id>` | `CURRENT_AUTHORITY` |
| `data/content_plans`, `data/production_plans` | `ACTIVE_DERIVED` or `HISTORICAL_IMMUTABLE`, depending on active lineage |
| `data/generation_batches/**/revisions` | Current approved production input: `CURRENT_AUTHORITY`; other attempts/revisions: `HISTORICAL_IMMUTABLE`; receipts: `VALIDATION_RECEIPT` |
| `data/patterns/approved` | `CURRENT_AUTHORITY`; approval receipts are `VALIDATION_RECEIPT` |
| `data/patterns/candidates` | `HISTORICAL_IMMUTABLE` or research candidate, never Production Authority |
| `data/cases`, `data/case_governance`, `data/analysis`, `data/visual`, `data/shots` | Approved structural authority plus preserved research evidence; never Production Asset by location alone |
| `data/production_footage/<request_id>` | Rights/inventory authorities plus active derived plan, mission, pack, match, and coverage artifacts |
| `data/operations/<business_id>` | Operator Action Control only; not customer status or business truth |
| `tests/fixtures` and fixture-labelled runtime trees | `FIXTURE_TEST` |

Deletion requires a separate reviewed cleanup wave. Wave 0 deletes or migrates nothing.
