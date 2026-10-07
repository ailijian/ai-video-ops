# Repository Agent Guide

## Scope and knowledge

This repository owns the canonical operations pipeline, its Internal Console,
and deployment tooling. `douyin-downloader/` is an ignored, independent Git
repository; work there requires its own scope and applicable instructions.

Start with the [Knowledge and Operations Index](docs/operations/README.md).
It routes system rules, design intent, machine contracts, operations, and
historical evidence to their owners. The Frozen Operations Baseline is a
durable system reference, not a new Delivery target or a live customer snapshot.

## Authority and production boundaries

- Business Authority remains in canonical `ops-pipeline` artifacts and
  resolvers. Console SQLite and task/status projections must not become a
  second business truth. Execution completion does not imply Human approval.
- Preserve explicit Human Gates and immutable approved lineage. AI extraction,
  Case research, and derived plans cannot independently create Customer Truth,
  production-media rights, or Proof. See the
  [Authority Map](docs/operations/AUTHORITY_MAP_V1.md).
- During production operation, Authority mutations use the Console gateways
  and operation locks. Direct mutation CLIs are offline recovery paths; do not
  use them concurrently with the production node or hand-edit Authority JSON
  to simulate a workflow. Follow the [RUNBOOK](docs/operations/RUNBOOK.md).
- Preserve the single-process production runtime and shared GPU guard. Do not
  start a second Console instance or run unguarded historical GPU tools beside
  it. Runtime, backup, and deployment procedures belong in the RUNBOOK and
  [Local Production Node guide](deploy/local-node/README.md).

## Knowledge maintenance

Update the existing fact owner and its navigation before creating another
durable document. Machine sources own executable fields, enums, paths, and
validation; prose explains intent, semantics, and operating boundaries.

Keep design targets, implementation state, approval/export receipts, and
history distinguishable. Use the index's scoped relationships rather than
choosing authority by version, timestamp, or implementation alone. Historical
does not mean disposable; follow the
[Artifact Lifecycle](docs/operations/ARTIFACT_LIFECYCLE_V1.md).

## Verification routes

- Pipeline checks: from `ops-pipeline`, run `python -m pytest` with its test
  dependencies installed. The default suite excludes live Authority checks;
  see [Test layers](ops-pipeline/tests/README.md).
- Console checks: from `internal-console`, run `python -m pytest` with its
  declared development dependencies. Tests use isolated fixture copies.
- Fixtures are test evidence, never runtime fallback Authority. Live Authority
  checks require an explicit root and remain read-only; do not repoint ordinary
  mutation tests at production data.

## Governance maintenance

Change this guide only when explicitly authorized to update repository
governance. Report durable repository-specific candidates; keep workflow
algorithms, temporary Delivery details, current customer values, and test
results in their proper owners instead of growing this guide after each task.
