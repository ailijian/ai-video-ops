# Native Novel News generation recovery v1.0

Contract freeze (NEWS-REC-01 R0): `novel_news_v1.py` remains the business
owner. Its delegated `novel_news_generation_recovery_v1.py` owns only immutable
attempt evidence inside the existing Request's private metrics directory.
There is no additional Request, Task or approval lifecycle.

The intent binds exact source/Persona/fact/constraint/memory/active authority,
prompt and model parameter identities, trusted principal and authorization state,
and the original Task operation identity. Session credentials are never saved in
these artifacts. Task binding is an immutable supplemental reference, written
before scheduling. Intent/dispatch/response/result references use artifact byte
SHA-256, not Git object IDs or checkout identities.

An immutable dispatch marker is durably written before transport. Its existence
without a prepared response is conservatively `dispatched_outcome_unknown`,
including a crash before the actual send. Legacy running tasks without evidence
are also unknown. Lease recovery never interprets either as permission to call.
`not_dispatched` is provable only for a new protocol intent without dispatch.
No admitted intent projects `not_admitted`, which proves no execution outcome;
the Native execution projection additionally examines original Task evidence.

The prepared response retains only the payload and response metadata needed for
the original privacy, grounding, structure and lineage validators. It is private,
unapproved evidence. A validated response without published Plan projects
`validated_result_unpublished`; an invalid reliably saved response projects
`confirmed_failure`. Exact valid Plan plus attempt/response linkage projects
`review_required`. Current source, authority or actor conflicts project
`source_or_authorization_conflict`. File existence alone never means ready.

Attempt parent refs form one deterministic chain under the Native short commit
lock. Missing parents, forks, schema mismatch or stale operations fail closed.
Only an explicit authenticated confirmation of the current unknown/failed head
can append a new attempt; repeated confirmation of the same parent returns the
same new operation. A live unexpired original Task cannot be superseded. An
expired worker is fenced by the new immutable head, and must recheck ownership
under the same commit lock immediately before publishing. Each attempt has a
separate executor lock. The generic Task recovery policy remains unchanged.
The existing backup gate, current Authority fence and Native commit lock are
acquired in that order for mutations. Network latency holds only the attempt's
executor lock. Private response persistence also uses the original backup gate.

Same-operation replay reuses a prepared response or verifies/reconciles the exact
Plan/result without transport. Unknown dispatch raises
`NEWS_GENERATION_OUTCOME_UNKNOWN`. Conflicting input raises
`NEWS_GENERATION_OPERATION_CONFLICT`; superseded ownership raises
`NEWS_GENERATION_SUPERSEDED`; invalid evidence/source/authorization raises the
corresponding `NEWS_GENERATION_*` error and cannot publish. A completed result is
not Human approval, export permission or production eligibility.

Original `novel_news_beat_plan_v1.json`, review, approved, export, closure and
ledger paths/contracts remain in use. Legacy deliveries with complete original
Receipt/Closure remain historical reads through the original Native validators.
An unbound legacy open Plan cannot gain a new Human approval, and no legacy
running task gains dispatch permission. An already valid Native Result can
reconcile Task completion after Session expiry without invoking generation again.
News Repurpose, Mix C3-05 and NR export protocols are unchanged.
