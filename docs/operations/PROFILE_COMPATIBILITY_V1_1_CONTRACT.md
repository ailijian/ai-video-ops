# COMPAT C0 — Compatibility v1.1 contract freeze

Source authorization: Founder COMPAT-1–4 instruction, G1–G6, 2026-10-19.
Executable fields are owned by `profile_compatibility_contract_v1_1.py`, delegated
by `production_profile_v1.py`. This document explains semantics, not approval.
Baseline: `1b6fc870bdf6768db10a561385f05ac81475c75d`.

## Identity and acyclic provenance

All artifact refs are root-relative `{path, sha256}` of exact file bytes. Source
Git blobs and Windows checkout bytes are separate provenance fields; CRLF/LF
normalization is never applied to business receipts.

Before approval: native Approved Case/receipt, native Fingerprint/Storyboard,
Approved Pattern/receipt and existing supported-case scope, immutable Mix profile
definition, explicit rules version and native compatibility audit evidence.
The snapshot contains these refs only, and never derived Registry/Coverage.
Each target ID hashes the exact full target. Changing any identity/version creates
a different target and requires fresh review. Source checks are repeated on submit.

The immutable preview binds source control ID, actor, exact current grant event, operation, snapshot,
per-target parent and action. Submission must match its stored SHA. Revoke then
regrant changes the grant event and invalidates the old preview. No username-only
v1.1 CLI. The existing principal/grant chain and locks remain the trust boundary.

## Decisions and history

One append-only receipt per operation; batch omissions have no meaning. Parent
chains are per exact target and independent of filesystem time. approve replaces
the effective approval for that target; reject records denial without withdrawing
an existing approval; withdraw names the exact effective approval and current
parent. New approve after withdrawal requires a fresh preview and current audit.
Missing parents, cycles, forks, unknown versions and conflicting operation replay
fail closed. Historical authorization evidence remains verifiable after revocation;
current authorization is always required for a new or interrupted submission.
Consumers configured to another control root cannot author new local decisions.
Receipt authorization proof is immutable decision-time evidence, not a portable
grant of login/reviewer permissions on the receiving machine.

No old v1.0 validator, historical artifact, receipt or supported-case list changes.
No profile hint, research candidate, shared display, Registry ready flag or Pattern
Candidate grants production qualification. News remains unavailable in this version.

## Derived release and runtime effect

Decision -> derived Registry/Coverage -> immutable release -> explicit Stage and
Activate -> runtime usable graph. Local approval alone is never consumable.
The new Mix-only registry has no dependency on a pre-existing Source Plan.
Old release V1 keeps its original minimum Mix/News graph and parser.

Release v1.1 binds exact committed source, reader version, target profiles,
artifact inventory, approvals, entire decision/withdrawal graph, parent release
and purpose. The activation receipt binds exact release and parent activation.
Source-file entries separate `git_blob_sha256` and `checkout_sha256`. Artifact
entries continue to use `sha256` of exact file bytes. These identities are never
interchanged.
Versioned packages and activations are append-only; only the active pointer is
atomically replaced after complete stage verification. Interrupted activation can
resume the same operation, but cannot change its payload or skip a parent.

Revocation requires a fresh, explicitly configured local/shared filesystem control
Authority. This is the same native decision Owner, not a second database or an
implicit fallback to artifact provenance paths. Consumers hold its existing OS
operation lock during each protected write, compare live decision-head digest with
the activated release, and fail closed if the control Authority is unavailable or
has advanced. Thus withdrawal fences old releases immediately before any new write.
Even unrelated decisions may conservatively require a new release activation.
This local/shared-filesystem protocol does not claim an offline cross-machine
push mechanism. A disconnected consumer cannot proceed using cached approval.
The explicit installation configuration binds control identity, path and purpose.

Creation/feasibility, matcher/source plan, content plan/generation, review, export
and open closure use the same resolver and exact release/receipt refs. New writes
with an old pinned graph stop after withdrawal. Completed history remains readable;
idempotent closed replay returns existing history without another Ledger append.
Business facts, persona/constraint gates, media rights and novelty remain independent.

Isolated-validation packages cannot stage or activate into production-purpose roots.
Test grants, business/customer data, sessions, DBs, media and model output are excluded
from releases. No deployment or real model operation is authorized by this contract.

## C0 execution gate

The strict schema tests, owner integration feasibility, and preserved legacy
dispatch must be checked before changes to production consumers. Contract changes
outside these declared semantics require an explicit Delta and a stop at that gate.

## Native operations and entry points

Apply the ordinary Console migration route to the intended isolated database.
The new `006_profile_compatibility_access.sql` stores local permissions only;
Compatibility decisions remain canonical files. Trusted maintenance can use
`internal-console/scripts/manage_profile_compatibility_reviewer.py` with explicit
`--user-id`, `--action grant|revoke`, `--reason` and the intended existing Console
environment. There is no HTTP grant route and no automatic Case reviewer upgrade.

The existing `approve_production_profile_compatibility_v1.py v1.1` CLI supports:

- `snapshot`: authenticated local principal/grant, `--case-id` (repeatable),
  `--mix-template`, optional exact native `--pattern-file`; reports sources and
  current heads, creates no approval. All three native approved Pattern supports
  must remain available. The default Pattern path is unchanged; an explicitly
  authored immutable version under the original approved Pattern domain may be
  supplied, without modifying the original artifact or widening it automatically.
- `preview`: `--operation-id`, `--decisions-json` with explicit per-target action,
  exact target IDs, current parent and reason. No action is inferred from research.
- `confirm`: the same operation plus exact `--preview-sha256`. All paths use
  `--root`, `--database`, `--namespace`, `--user-id` and current independent grant.
  Supplying a reviewer display name is not a v1.1 authorization mechanism.

HTTP uses the same Owner via POST `/api/profile-compatibility/preview` and
`/api/profile-compatibility/confirm`, normal Session/CSRF and existing locks.
Only the actor from the authenticated Session is passed to the Owner.

Release preparation reuses `deploy/creative-authority/build_release.py` with
`--contract-version 1.1`, explicit `--purpose`, and optional JSON parent release
ref. The source tree must be clean and committed. Source inventory covers tracked
Pipeline scripts, Console app/maintenance/migrations, and release tooling; Git Blob
and checkout byte digests are separate. No runtime data or source text is copied
into that source inventory.

Use the existing `verify_release.py verify` and `preflight` commands. New explicit
`stage-v1.1` and `activate-v1.1` operations use immutable release refs and a stable
activation operation ID. The old `install` route refuses new schemas; it never
silently overwrites V1 singletons. Runtime purpose/control configuration is trusted
local maintenance, immutable after creation, and is not accepted from HTTP input.
Production cannot relabel an isolated validation package as production by editing
its manifest: purpose is schema/inventory/SHA-bound and compared to configured root.

The current transport-failure recovery of the pre-existing Script Generation Owner
is a separate creation concern. Compatibility activation must not hide an incomplete
Batch or grant Human content approval/export. Any new generation-attempt selection
contract belongs to its original Owner and requires a separate explicit Delta.
