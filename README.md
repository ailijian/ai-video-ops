# AI Video Ops MVP V1

This repository contains the approved Customer Truth → Content → Pre-production operating pipeline and its preserved research and validation history.

## Start Here

1. [Frozen Operations Baseline](docs/product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md) — Approved / Frozen system authority.
2. [Operations RUNBOOK](docs/operations/RUNBOOK.md) — commands and honest implementation status for current operations.
3. [Current Status Read Model](docs/operations/CURRENT_STATUS_READ_MODEL_V1.md) — read-only customer status and next-action projection.

## Internal Console

The Phase 1 mobile-first operations surface lives in
[`internal-console`](internal-console/README.md). It is a thin Application/API
Layer over the canonical operations and stores only internal auth, session, and
task-projection data.

The Local Production Node runtime is frozen to one Uvicorn process listening
only on `127.0.0.1:8000`. Its durable SQLite task projection uses two execution
lanes (`GPU_HEAVY` and `STANDARD_BACKGROUND`), lease-based crash recovery, and
a cross-process `global_gpu` guard. Do not start multiple Console instances or
run an unguarded historical GPU script beside the production node. Production
templates and the backup/run checklist are in
[`deploy/local-node`](deploy/local-node/README.md).

View the current real-customer status:

```powershell
python ops-pipeline/scripts/show_customer_status_v1.py --business-id shufang_zhiyuan_community_canteen
```

Documents marked Historical, Working Architecture, Freeze Candidate, Superseded, or Non-canonical are retained evidence and are not Current Operations Authority. Use the operations index above instead of old team demo commands.
