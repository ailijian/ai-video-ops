# Generation Export Anchor v1

Founder decision: `PC_MIX_ANCHOR_01_CONTRACT_APPROVED_WITH_GUARDS`.
This is an additive historical verification path. It does not approve content,
reopen a Request, or change the original `generation-export-closure-v1.0` reader.

Machine owners are `close_generation_export_v1.py` and `content_quality_v1.py`.
`ledger_history_v1.py` implements their shared evidence mechanics.
`news_delivery_v1.py` delegates its existing Presentation append; Novel News
delegates semantic and Presentation steps, retaining its own Native receipts.
Executable fields and strict dispatch are in `ledger_history_v1.SCHEMAS`.

## Evidence and verification

`generation-export-anchor-evidence-v1.0` binds the exact original Closure,
Approved Batch, Human Approval Receipt, XLSX, Export Receipt, Business, original
Ledger byte snapshot and canonical hash, semantic and Presentation prefixes,
baseline Native transition and validator version. A snapshot is copied from
actual Native bytes and checked against the original Closure. No reconstruction
of a missing past Ledger from its present contents is permitted.

The delegated `content-ledger-native-transition-v1.0` binds exact before/after
snapshots, their canonical hashes, frozen Native source refs, operation identity,
kind and deterministic parent. A source-specific Native recipe reconstructs the
whole resulting Ledger, including catalogs, statistics, validation metadata and
`updated_at`. The reader compares the complete object and exact snapshot bytes.
Prefix equality alone is insufficient. Unknown changes, branches, missing
parents, duplicate events, cross-Business data and unknown schemas fail closed.

`content-ledger-native-transition-receipt-v1.0` binds that transition to the
original Native Export Receipt and Closure. A prepared transition without the
corresponding complete Native result cannot certify completed history. Novel
News has two ordered steps and one original Native closure; it gains no second
business Closure. Events confer no independent Human approval or media right.

## Writes and recovery

Native publication order is snapshots -> immutable prepared transition ->
original atomic Ledger update -> original Native Receipt/Closure -> immutable
transition receipt. Mix additionally captures its historical anchor. These are
multiple durable steps, not a multi-file atomic transaction. A crash retains
evidence, and retry appends only missing identical steps. Another operation
cannot adopt an unfinished Native transition. No ledger rollback is performed.

Existing Console Business/backup/Authority fences remain. Native Ledger commits
also use `content-ledger-history:<Business>`; supplemental delivery acquires that
same fence inside its current Authority and Business locks, verifies the anchor
there and binds its ref in the new Delivery intent/receipt. Current source,
Compatibility, Pattern and customer restrictions still gate every new write.

The old v1.0 Closure Reader continues checking current whole-Ledger SHA exactly.
Consumers explicitly dispatch to the anchor reader only when the versioned
proof exists; an invalid proof never falls back to the old reader. Without a
proof, an unchanged, fully verified Native bundle may be captured by the owner.
An already changed legacy Ledger without its authentic original snapshot is
`LEDGER_HISTORY_EVIDENCE_INSUFFICIENT`, not an automatic repair or human approval.
The original PC-MIX-ANCHOR-01 fixture is retained unchanged as this negative case.

Supplemental deliveries have zero semantic, exposure and Presentation deltas.
Their completion and effective-version events remain distinct from business
Closure. Replays preserve original timestamps, files, receipts and ledger state.

## Content memory

The approved publication-generation attempt still binds its exact
`memory_sha256`. A Presentation append adds no original semantic entry, but it
changes presentation/exposure history in that bound memory snapshot. An open
or uncertain generation attempt cannot silently adopt it: resume is blocked and
an explicit new attempt is needed. This conservative rule is not weakened by
the historical anchor. Previously completed production and publication records
remain immutable; ordinary publication edits add no Ledger effects.

## Scope

Implementation and verification are isolated and fictional. No production root,
old Founder runtime, real model, AUTH/OIDC, remote push or deployment is granted.
An unsupported Ledger writer must not silently create an unjournaled change in
a root with active history evidence.
