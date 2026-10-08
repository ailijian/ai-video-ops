# AI Video Ops MVP V1 — Knowledge and Operations Index

**Status:** Approved Operations Entry

This is the repository knowledge map and canonical entry for operating the existing MVP. It routes facts to their owners without restating them.

## System and operations entry points

1. [Frozen Operations Baseline](../product/AI%20Video%20Ops%20MVP%20V1｜End-to-End%20System%20Map%20&%20Operations%20Baseline.md)
2. [Authority Map V1](AUTHORITY_MAP_V1.md)
3. [Artifact Lifecycle V1](ARTIFACT_LIFECYCLE_V1.md)
4. [Operations RUNBOOK](RUNBOOK.md)
5. [Current Status Read Model V1](CURRENT_STATUS_READ_MODEL_V1.md)

This is a reading route, not a global precedence rule. The Baseline owns system invariants; each source below owns only its declared fact domain and dimension. Its dated customer figures and implementation checkpoint do not establish live status. The RUNBOOK describes current operation and recovery paths; machine sources establish executable structure and current implementation.

## Scoped knowledge owners

| Fact domain | Owner / entry point | Dimension and relationship |
|---|---|---|
| Content uniqueness, historical exposure, editorial quality, capacity stop | [Content Quality Authority](../content_quality/CONTENT_UNIQUENESS_EDITORIAL_QUALITY_V1.md) | Current product rules; its experiment counts and freeze results are historical evidence |
| Production profiles, creative coverage and structural matching intent | [Production Profile & Creative Coverage](../design/Production%20Profile%20&%20Creative%20Coverage%20V1｜产品与工程冻结框架.md) | Frozen design intent; dated coverage claims are historical, while current coverage comes from validated runtime artifacts |
| Console interaction, Human Gates, auth and business-data boundaries | [Internal Console UX & Interaction](../design/AI%20Video%20Ops%20MVP%20V1｜Internal%20Console%20UX%20&%20Interaction%20Freeze%20V1.0.md) | Current interaction/boundary reference; presentation clauses are partially superseded by the next row |
| Console presentation, navigation, language, layout and responsive rules | [Productized UI & Information Architecture](../design/鲸汤%20AI%20视频代运营工作台｜Productized%20UI%20&%20Information%20Architecture%20Freeze%20V1.0.md) | Frozen design target for this scope; does not prove implementation or replace business/security boundaries |
| Business artifacts and their writers/consumers | [Authority Map](AUTHORITY_MAP_V1.md) | Current ownership route; artifact fields and validation belong to the linked machine sources |
| Runtime, rollout, recovery and deployment | [RUNBOOK](RUNBOOK.md), [Console](../../internal-console/README.md), [Local Node](../../deploy/local-node/README.md) | Current operating references; implementation, availability and validation evidence remain separate |
| Portable shared creative Authority | [Creative Authority deployment](../../deploy/creative-authority/README.md) | Source/consumer and immutable manifest route; installation never re-runs approval or copies customer runtime state |
| Verification execution, isolation and live Authority smoke | [Repository verification](../../tools/README.md), [Pipeline test layers](../../ops-pipeline/tests/README.md), [Console test configuration](../../internal-console/pyproject.toml) | The root runner owns full/affected execution; package configuration owns its checks. Fixtures and test results remain evidence, not production Authority |

## Machine sources

Runtime artifact paths in the Authority Map and Artifact Lifecycle are relative to `ops-pipeline/`. Resolve their approval and SHA lineage; do not substitute a fixture or select a file by mtime.

| Executable fact | Editable machine owner / resolver |
|---|---|
| Current approved Persona lineage and status | [Status resolver](../../ops-pipeline/scripts/show_customer_status_v1.py); Console [Persona adapter](../../internal-console/app/persona_authority.py) delegates approved selection to it |
| Profile registry, coverage and compatibility structure | [Production Profile](../../ops-pipeline/scripts/production_profile_v1.py); runtime registry/approval artifacts carry their lineage |
| Mix Human Review and export closure | [Review V2](../../ops-pipeline/scripts/review_generation_batch_v2.py), [Export closure](../../ops-pipeline/scripts/close_generation_export_v1.py) |
| Novel News opportunities, review, export and semantic closure | [Opportunity projection](../../ops-pipeline/scripts/novel_news_opportunity_v1.py), [Novel News](../../ops-pipeline/scripts/novel_news_v1.py); shared novelty rules remain in [Content Quality](../../ops-pipeline/scripts/content_quality_v1.py) |
| Privacy projection and remote-model boundary | [Privacy Projection](../../ops-pipeline/scripts/privacy_projection_v1.py) |
| Console persistence and feature availability | [Migrations](../../internal-console/migrations), [Settings](../../internal-console/app/config.py), [Novel News rollout](../../internal-console/app/novel_news_rollout.py) |
| Shared Authority release provenance and checksums | [Authority release](../../deploy/creative-authority/authority_release.py) |

## History and evidence

The superseded [Working Architecture](../product/AI短视频代运营生产工作流与案例资产架构_V0.1_Working_Architecture.md), [Content Quality candidate](../product/Content%20Uniqueness%20&%20Editorial%20Quality%20V1｜产品与工程冻结框架.md), and [Customer Intake design record](../design/Customer%20Intake%20&%20Persona%20Onboarding%20V1｜产品与工程冻结框架.md) remain historical references. The [UI audit](../design/INTERNAL_CONSOLE_PRODUCTIZATION_UI_AUDIT_V1.md) is evidence for its recorded checkpoint, not the current UI specification. Approval receipts prove gates; neither receipts nor completed task projections create business requirements. Preserve valuable lineage under the Artifact Lifecycle rather than deleting old versions by age.

## Current boundaries

- `show_customer_status_v1.py` is read-only and derived-only.
- `operational_controls_v1.py` owns only explicit Operator Action Controls.
- Novel News has a separate implemented flow with default rollout `off`; validation access, supported opportunities and Scene Contrast gates are described in the RUNBOOK. Code presence does not establish production availability or completion of a real-customer gate.
- Production Asset Intake, Production Package, Video Production, Final Video QA, and Performance Learning are not implemented here.
- Historical artifacts and documents remain evidence. Historical does not mean deprecated.
