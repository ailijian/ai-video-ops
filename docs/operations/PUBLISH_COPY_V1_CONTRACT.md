# Publish Copy and Supplemental Delivery v1

Founder approved PC0 R2 and PC-MIX-ANCHOR-01. This implementation is an
independent derivation after Native production approval. It neither changes
Mix/News production approval nor grants publication or source-media rights.

Executable records and strict dispatch are owned by
`ops-pipeline/scripts/publish_copy_contract_v1.py`, `publish_copy_v1.py` and
`creation_delivery_v1.py`; their frozen schema is
`ops-pipeline/schemas/publish-copy-v1.schema.json`. The Console gateway uses the
existing Session, CSRF, operation locks, Task database and Pipeline interpreter.
`AIVO_PUBLISH_COPY_ENABLED` defaults off.

## Sources and derivation

`publish_copy_sources_v1.py` resolves exact Native approved Mix content, Novel
News content or Repurpose Presentation. Source snapshots bind the original
Request, production approval, safe fact projection, constraints and current
typed Creative Authority. Private intake, Speaker biography and Case analysis
are not model inputs. Request-local aliases replace internal identifiers in
the external prompt. The server selects its existing model configuration; an
Intent pins the model, prompt, owner code, ordered targets and Content Memory.

Generation uses at most five targets per external call. News obtains its
production headlines and publication triplet in that same call. Native News
retains four to eight Beats. Delivery headlines cover every approved Beat/Slot
through exact fragment and Approved SHA mappings, with one to six headlines
per video. Three to six and twelve characters are recommendations; no padding,
fact loss, changed subject, price or qualifier is allowed. A newline separates
headlines in the single production-content cell, never separate video rows.

The immutable generation protocol is Intent -> durable Dispatch -> private
Response -> validated Draft/Result. Unknown execution does not automatically
dispatch again. An explicit authorized retry has a new operation and parent.
A saved response resumes locally. Result readiness requires its exact response
and draft bindings, canonical source mappings and Native validation; file
existence is insufficient. A late operation cannot replace a newer head.
Unbound legacy tasks remain outcome-unknown until their evidence is resolved.

Partial batches retain validated draft targets. Edits bind the exact existing
target set and produce a new immutable draft. Generating the remaining targets
preserves those edits. Final confirmation and delivery require every production
row to be complete. One explicit Human confirmation binds the actual delivered
headlines, their source mapping, title, body and topics. It never changes the
original production approval. New source or permission conflicts fail closed.

## Delivery and recovery

The original `export_mix_excel_v1.py`, `novel_news_v1.py` and
`news_delivery_v1.py` own supplemental export. If the original Native delivery
has not closed, its own writer completes it once. Existing original receipts
are read and validated through their Native reader/writer; they are not
re-serialized by another subsystem. Mix history is delegated to the
[Generation Export Anchor](GENERATION_EXPORT_ANCHOR_V1_CONTRACT.md).

Records live under the original Request's `deliveries/<server delivery ID>`:
Intent -> staged XLSX -> Prepared -> exclusive output publication -> Receipt ->
delivery-scoped Completion -> effective-version event. These durable steps are
not a multi-file transaction. Recovery appends only missing identical records;
existing files, receipt timestamps and source identities are unchanged.

The Intent/Receipt bind the original Closure, confirmed production/derived
versions, template and actual XLSX SHA. Selection uses one verified parent
chain and expected-head comparison. A completed unselected file is not an
effective delivery. Explicit historical download validates the selected
version's own receipt; it cannot certify a newer draft. Replays reuse the
original Task where present and add no semantic content, exposure, business
Closure or Presentation History.

The new deterministic OOXML renderer preserves the two frozen templates:
one visible Sheet1, headers on row four, data from row five, five Mix columns
and four News columns. All parts, cells, order, count, styles and ZIP structure
are checked; formulas are literal strings, and extra sheets, hidden content,
links, comments or trailing payload are rejected. New serialization is fixed
against the XML namespace side effects of openpyxl and the News renderer.
Already-prepared v1.0 candidate files retain read compatibility with the two
known complete namespace projections (default and `s`). Each is an exact
whole-parts comparison, and its actual parts digest and byte SHA must still
match its original Prepared/Receipt. No generic XML normalization, checksum
skip, overwrite or orphan adoption is allowed.

## Runtime boundary

Open generation attempts keep their exact whole-Ledger `memory_sha256` fence,
including Presentation additions. This is distinct from historical validity
of completed production/derived records and zero-exposure re-delivery. A changed
memory snapshot never silently rebinds or redispatches an unfinished attempt.

Engineering acceptance uses fresh fictional SQLite, Canonical and Creative
Authority roots and independent cookies/ports. Only external provider transport
is synthetic; Human approval, Compatibility, release, Task, Native export,
receipts and Ledger remain real. Founder samples remain separate and unused
until the Founder acts. This contract is not a real-model quality or production
deployment claim.
