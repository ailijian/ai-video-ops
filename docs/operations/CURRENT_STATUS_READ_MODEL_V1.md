# Current Status Read Model V1

**Status:** Approved Operations Contract
**Implementation:** `ops-pipeline/scripts/show_customer_status_v1.py`
**System Authority:** [AI Video Ops MVP V1 Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)

## Contract

The status view is read-only and derived-only. It writes no Persona, Ledger, Batch, Footage, or Operational Controls artifact; calls no model; triggers no next action; and is never persisted as `customer_status.json`.

```powershell
python ops-pipeline/scripts/show_customer_status_v1.py --business-id <business_id> [--speaker-id <speaker_id>] [--batch-id <request_id>] [--format text|json]
```

If the speaker cannot be uniquely bound to the Current Approved Business Persona, or if current authority cannot be resolved through approval and lineage, the command fails closed with `CURRENT_AUTHORITY_AMBIGUITY` or another hard blocker and projects `RESOLVE_AUTHORITY_BLOCKER`.

## Field sources

| Status field | Existing source |
|---|---|
| Business/Speaker Persona | Explicit persona revision + approved lifecycle + approval receipt + SHA/lineage |
| Ledger entry count | Length of canonical `entries`; stale `validation.entry_count` is diagnostic only |
| Remaining capacity | Active batch-bound post-export capacity + source persona lineage + current ledger SHA |
| Latest exported Mix | Approved batch/receipt/export receipt jointly validated, ordered by append-only ledger batch references |
| Latest exported News | Business ledger presentation history; cross-profile repurpose remains non-novel |
| Creative paths | Frozen profile registry + active derived News coverage update |
| Footage | Exact Active Batch request ID → requirement/approval/mission/inventory/coverage artifacts |
| Speaker media | Batch-bound subject media confirmation |
| Operational Hold | `operational-controls-v1` metadata |

No source is selected by mtime, filename length, alphabetical order, or directory order. Explicit revision numbers may select the highest valid approved Persona only when approval receipts and previous-approved lineage do not conflict.

## Next action priority

1. Hard Authority Blocker
2. Required Human Review
3. Required Customer or Operator Input
4. System Execution
5. Optional Improvement

Exactly one Primary Next Action is returned. An active Operational Hold overrides a normal execution/customer-contact action with `WAIT_FOR_OPERATOR_RELEASE`, while preserving `would_be_next_action`. It does not hide hard authority blockers.

## JSON contract

The JSON output includes:

```text
business
customer_truth
content
creative
footage
rights
blockers
operational_hold
primary_next_action
would_be_next_action
evidence_refs
```

`evidence_refs` point to existing authorities or active derived artifacts. The projection itself is not an authority.
