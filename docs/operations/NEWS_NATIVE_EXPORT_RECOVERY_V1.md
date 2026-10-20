# Native News export recovery

The original `novel_news_v1.py` and `news_delivery_v1.py` remain the delivery,
Closure and Ledger owners. Their companion `news_export_recovery_v1.py` owns
executable schemas for publication evidence only. It grants no Case, Pattern,
Compatibility, Customer Truth, qualification or media rights.

The Console resumes an existing failed News export Task only for the same
trusted actor/permission epoch and original Native intent. Re-login refreshes
execution context, never the immutable intent or sources. Completed Native
delivery reconciles the original Task after a lost response; no replacement
Task, Receipt, Closure or Ledger entry is created. Native validation remains
mandatory before delivery and on every continuation.

`news-export-intent-v1.0` precedes all XLSX work. It binds the native Request
type/ID, Business/Speaker, original Human Review and Approved artifact, native
plan and immutable structural refs, effective restrictions and release binding,
template bytes, exporter version, server-derived output, titles and stable local
actor. The original Session validator rechecks the current active principal.
The intent stores only stable permission state and database identity hashes;
it stores no Session credential or fingerprint. A new Session for that same
unchanged principal can continue; another actor or changed permission state cannot.

`news-export-prepared-publication-v1.0` binds the exact immutable intent, complete
staged XLSX, eventual output SHA, template and sources. The original dynamic
renderer derives all OOXML members from the trusted template and approved
ordered titles. Validation checks the entire member inventory and bytes, CRC,
container boundaries and metadata, rejecting unapproved sheets, hidden content,
cells/rows/columns, formulas, comments, external links and appended ZIP payloads.
An exclusive hard link publishes the exact prepared bytes without overwriting
any existing destination. This requires a same-volume filesystem supporting
hard links; unsupported publication fails closed. It is not a multi-file transaction.

Each interruption window has separate evidence. An incomplete uniquely named
render temporary is retained; a missing complete stage can be prepared again.
A complete stage with Intent but no Prepared is fully verified before Prepared
is appended. A published output without both trusted records is
`NEWS_EXPORT_LEGACY_UNBOUND_ORPHAN`, never automatically adopted or replaced.
A mismatching existing output stays intact. Completed stages are not rewritten.

New Receipt/Closure files and the first Novel Ledger publication use exclusive
atomic writes. The original Ledger owner can resume a fully written append
temporary only when a valid exact Export Intent/Prepared publication and the
entire expected temporary payload match. Mismatched, unbound or corrupt
temporaries remain blocked and retained. Mix's existing admission semantics
are unchanged; the additional temporary admission is explicitly News-bound.

New Novel Receipt/Closure and Repurpose Receipt/Closure use their respective
v1.1 schemas. Old complete v1.0 history retains its own strict reader. Old
unbound partial files require controlled review; no automatic legacy backfill
exists. Repurpose reuses the original persisted `created_at` and presentation
event. `presentation_recovered` is an execution observation, not new canonical
Receipt identity. Receipt then missing Closure resumes only that missing step.

The original Ledger owner appends `news-presentation-history-event-v1.1` events
with exact prefix-parent SHA. Existing legacy prefix events retain their bytes.
Immutable receipt/closure prefix hashes distinguish the original snapshot from
later append-only history. The native reader validates the event chain and
original semantic/presentation prefixes; it does not compare old snapshot SHA
to the entire newly extended mutable Ledger. Novel records one semantic item;
Repurpose records only its presentation, with zero new semantic exposure.

States are `xlsx_not_generated`, `prepared_unpublished`,
`published_receipt_pending`, `receipt_complete_closure_pending`, `completed`,
or `legacy_unbound_orphan`. File existence never establishes completion.
Native terminal readers validate Human, source, publication, Receipt, Closure
and Ledger before Gateway/Task/download projections can report completion.
UI says “导出尚未完成，可继续原操作。” or “导出结果需要重新核对。”.
Completed HTTP replay returns the canonical result with the original Task if
one exists; it creates no replacement execution Task.

Console keeps its original backup/Business operation locks. A Native News lock
serializes both News writers; child processes do not reacquire the parent's
Windows backup barrier. CLI mutations remain offline recovery only per RUNBOOK.
The current release owner fences open writes; unknown/unconfigured bindings and
Mix-only releases never grant News. The separately approved News v1.2 contract,
qualification, rollout and Founder eligibility still require their own gates.

Focused tests: `ops-pipeline/tests/test_news_export_recovery_v1.py` and
`internal-console/tests/test_news_export_recovery_http_v1.py`. Disposable legacy
unit sources in these tests are not formal News v1.2 qualification evidence.

## News v1.2 reader and isolated qualification

`profile_compatibility_contract_v1_2.py` owns the additive executable News
schemas. The existing decision/control domain retains strict v1.1 Mix and
v1.2 News dispatch. News requires independent `news_profile_compatibility_reviewer`
authorization; Pattern research and approval require `news_pattern_reviewer`.
Capability chains have separate sequences and parents. Legacy event bytes,
Mix proofs, Pattern scopes and receipts are not rewritten.

`news_pattern_authority_v1_1.py` delegates to the original comparison,
candidate and Pattern owners. Pure Profile/rules definitions precede Human
approval; derived Registry/Coverage cannot serve as their own approval input.
Versioned Pattern paths retain their exact supporting Case/FP/storyboard scope.

The original release owner dispatches v1.2 through
`profile_compatibility_release_v1_2.py`. An isolated root explicitly declares
News alone or the exact existing Mix plus News decisions. Production installation
is refused. Pending qualification, completed Native evidence and Founder runtime
eligibility are distinct stages; each publication still requires formal build,
verify, stage and activation. A local approval is not an active runtime binding.

`news_runtime_v1_2.py` provides the exact effective binding to both native
consumers. Novel Request/Source Plan and Repurpose Request/Plan retain their own
types. Current Persona, restrictions, approved source versions, Pattern scope,
live decisions and activation must still agree. No mtime or fixed legacy Pattern
lookup is a fallback for a new binding. Model prompts use request-local Fact Atom
aliases; canonical source identity is restored before Native grounding checks.

`news_qualification_v1_2.py` derives isolated evidence from the original native
completed-result validators. Private Request, Persona, content, Ledger and XLSX
bytes stay in the retained origin runtime; a structural release carries exact
references and validation metadata. Missing or changed origins fail closed.
This does not establish a portable production qualification contract. An archived
qualification activation can be inspected only through an internal read scope
which verifies the complete activation chain and current source decision head.
That scope cannot admit generation, review mutation or export writes. Both
independent Native outcomes are required before Founder eligibility can be built.

News task admission reads Native subprocess state before holding the final
Compatibility fence over SQLite admission, avoiding Windows cross-process CRT
lock reacquisition. Execution retains its own native current-authority fence.
Successful normal export does not establish crash-safe generation: generation
with an unknown external outcome requires an independently validated recovery
contract, separate from this XLSX publication protocol.
