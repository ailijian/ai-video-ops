# AI Video Ops MVP V1 — Operations Index

**Status:** Approved Operations Entry

This directory is the canonical entry for operating the existing MVP. It does not replace or restate the system map.

## Authority order

1. [Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)
2. [Authority Map V1](AUTHORITY_MAP_V1.md)
3. [Artifact Lifecycle V1](ARTIFACT_LIFECYCLE_V1.md)
4. [Operations RUNBOOK](RUNBOOK.md)
5. [Current Status Read Model V1](CURRENT_STATUS_READ_MODEL_V1.md)

The Baseline owns system rules. These documents point to the implementation and describe how to operate it without creating a second business authority.

## Current boundaries

- `show_customer_status_v1.py` is read-only and derived-only.
- `operational_controls_v1.py` owns only explicit Operator Action Controls.
- Production Asset Intake, Production Package, Video Production, Final Video QA, and Performance Learning are not implemented here.
- Historical artifacts and documents remain evidence. Historical does not mean deprecated.
