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
| Customer-centric creation navigation and customer operations list | [NAV-1 / CUSTOMER-LIST-1 implementation](../design/NAV1_CUSTOMER_LIST1_IMPLEMENTATION_REPORT.md) | Founder-authorized presentation amendment and dated offline implementation evidence; supersedes applicable navigation/list/global-create presentation only, retains Authority boundaries, and awaits independent Product Review / production validation |
| Business artifacts and their writers/consumers | [Authority Map](AUTHORITY_MAP_V1.md) | Current ownership route; artifact fields and validation belong to the linked machine sources |
| Historical Mix export anchors and Native Ledger append evidence | [Generation Export Anchor v1](GENERATION_EXPORT_ANCHOR_V1_CONTRACT.md) | Additive exact-snapshot reader; original Closure, Human gates and Ledger remain with their Native owners |
| Derived publishing fields and versioned supplemental Excel | [Publish Copy / Delivery v1](PUBLISH_COPY_V1_CONTRACT.md) | Separate Human confirmation, strict source/constraint and Native export checks; adds no semantic exposure or production approval |
| Runtime, rollout, recovery and deployment | [RUNBOOK](RUNBOOK.md), [Console](../../internal-console/README.md), [Local Node](../../deploy/local-node/README.md) | Current operating references; implementation, availability and validation evidence remain separate |
| Case Smart Intake V1.1 controlled deployment | [CSI production deploy procedure](CASE_SMART_INTAKE_V1_1_PRODUCTION_DEPLOY_RUNBOOK.md) | Exact-commit promotion, migration/backup, preflight and real-validation gates; preparation does not establish Production PASS |
| Portable shared creative Authority | [Creative Authority deployment](../../deploy/creative-authority/README.md) | Source/consumer and immutable manifest route; installation never re-runs approval or copies customer runtime state |
| Verification execution, isolation and live Authority smoke | [Repository verification](../../tools/README.md), [Pipeline test layers](../../ops-pipeline/tests/README.md), [Console test configuration](../../internal-console/pyproject.toml) | The root runner owns full/affected execution; package configuration owns its checks. Fixtures and test results remain evidence, not production Authority |

## Machine sources

The [CASE isolated release candidate](../design/CASE_INTAKE_REVIEW_SHARE_V1_ISOLATED_RC.md)
records the Founder-accepted Intake/Review/Share scope and frozen dependency
lineage. It does not authorize production rollout or replace the machine owners.

DASH-1's [Brand Operations Home read contract](../design/DASH1_BRAND_OPERATIONS_HOME.md)
routes the homepage aggregation, action identities and unknown completion metric.
It combines existing owners without changing Authority or granting permissions.

Runtime artifact paths in the Authority Map and Artifact Lifecycle are relative to `ops-pipeline/`. Resolve their approval and SHA lineage; do not substitute a fixture or select a file by mtime.

| Executable fact | Editable machine owner / resolver |
|---|---|
| Current approved Persona lineage and status | [Status resolver](../../ops-pipeline/scripts/show_customer_status_v1.py); Console [Persona adapter](../../internal-console/app/persona_authority.py) delegates approved selection to it |
| Profile registry, coverage and compatibility structure | [Production Profile](../../ops-pipeline/scripts/production_profile_v1.py); runtime registry/approval artifacts carry their lineage |
| Independent Mix Compatibility v1.1 review, versioned publication and active-consumer fencing | [C0 contract](PROFILE_COMPATIBILITY_V1_1_CONTRACT.md), [existing Production Profile owner](../../ops-pipeline/scripts/production_profile_v1.py) and [existing release owner](../../deploy/creative-authority/authority_release.py); explicit independent grant and Human decision, then release activation; local approval alone is not runtime eligibility |
| Mix Human Review and export closure | [Review V2](../../ops-pipeline/scripts/review_generation_batch_v2.py), [Export closure](../../ops-pipeline/scripts/close_generation_export_v1.py) |
| Mix partial Human/Export receipt recovery | [Companion schemas and strict readers](../../ops-pipeline/scripts/delivery_receipt_recovery_v1.py), [native Excel writer](../../ops-pipeline/scripts/export_mix_excel_v1.py), [Console protocol](../../internal-console/README.md#mix-generation-recovery); original Human/Export/Closure owners retain all approval and delivery authority |
| Mix zero-output transport failure recovery, effective Batch and completed-operation replay | [Native Generation](../../ops-pipeline/scripts/resolve_generation_batch_v1.py), [recovery machine schemas](../../ops-pipeline/scripts/generation_recovery_v1.py), [Console protocol](../../internal-console/README.md#mix-generation-recovery) |
| Novel News opportunities, review, export and semantic closure | [Opportunity projection](../../ops-pipeline/scripts/novel_news_opportunity_v1.py), [Novel News](../../ops-pipeline/scripts/novel_news_v1.py); shared novelty rules remain in [Content Quality](../../ops-pipeline/scripts/content_quality_v1.py) |
| Native Novel/Repurpose export safety and interrupted publication | [News export recovery](NEWS_NATIVE_EXPORT_RECOVERY_V1.md), [executable schemas](../../ops-pipeline/scripts/news_export_recovery_v1.py); original Native News writers retain Receipt, Closure and Ledger ownership; this protocol grants no News qualification |
| Finite customer batch configuration, Native admission/reservations and concentrated Human commands | [Console protocol](../../internal-console/README.md#creation-entry-preparation), [original Request coordination](../../ops-pipeline/scripts/native_batch_v1.py), [C07 delegation](../../ops-pipeline/scripts/creation_batch_review_v1.py); isolated engineering scope and test evidence do not grant production eligibility or a second approval/ledger authority |
| Novel News model dispatch uncertainty and explicit retries | [Native generation recovery](NEWS_NATIVE_GENERATION_RECOVERY_V1.md), [attempt schemas and immutable evidence](../../ops-pipeline/scripts/novel_news_generation_recovery_v1.py); [original Native owner](../../ops-pipeline/scripts/novel_news_v1.py) retains Plan validation/publication; generic Task recovery and Human/export gates remain independent |
| News v1.2 independent approval, isolated qualification and exact consumers | [Executable contracts](../../ops-pipeline/scripts/profile_compatibility_contract_v1_2.py), [Pattern delegation](../../ops-pipeline/scripts/news_pattern_authority_v1_1.py), [release adapter](../../ops-pipeline/scripts/profile_compatibility_release_v1_2.py), [Native evidence](../../ops-pipeline/scripts/news_qualification_v1_2.py), [runtime binding](../../ops-pipeline/scripts/news_runtime_v1_2.py); no automatic production eligibility |
| Privacy projection and remote-model boundary | [Privacy Projection](../../ops-pipeline/scripts/privacy_projection_v1.py) |
| Console persistence and feature availability | [Migrations](../../internal-console/migrations), [Settings](../../internal-console/app/config.py), [Novel News rollout](../../internal-console/app/novel_news_rollout.py) |
| Smart Case intake groups, private Excel candidates and independent classification labels | Console [intake admission](../../internal-console/app/case_intake_service.py), delegated [Excel candidate store](../../internal-console/app/case_excel_import.py), [I2 scope/recovery](../deliveries/case-excel-import-1/i2/README.md) and [owned submissions](../deliveries/case-excel-import-1/continuation-r1/README.md) and [current JC-01 / finite EX-S2 R4 engineering scope](../deliveries/case-excel-import-1/native-implementation-r4/README.md), [classification companion](../../internal-console/app/case_classification.py), and [usage/API boundaries](../../internal-console/README.md#case-smart-intake); Excel save never enters the auto-dispatch groups; Native submission, bound reviewer notes, single-confirmation typed sharing and finite multi-row consent retain their exact independent authorization and original Owners; engineering results do not grant production Authority |
| Customer intake identity, additive Business revisions and explicit Speaker revalidation | [Console contracts and recovery](../../internal-console/README.md#customer-and-speaker-smart-intake), [Customer review writer](../../ops-pipeline/scripts/customer_fact_review_v1.py), [Speaker review writer](../../ops-pipeline/scripts/speaker_fact_review_v1.py); existing Persona builder, resolver and approval remain Authority owners |
| Legacy unscoped critical adjudication | [Restriction Authority amendment](AUTHORITY_MAP_V1.md#legacy-unscoped-critical-scope-adjudication--2026-10-16), [existing restriction consumer](../../ops-pipeline/scripts/customer_constraints_v1.py), [immutable scope companion](../../ops-pipeline/scripts/legacy_constraint_scope_v1.py); explicit reviewer grant and isolated validation do not unlock real customer production |
| Snapshot-bound final review, targeted corrections and interrupted command recovery | [Console review closure](../../internal-console/README.md#review-closure-and-targeted-corrections), [Persona lifecycle companion](../../ops-pipeline/scripts/persona_review_lifecycle_v1.py), [Human operation records](../../ops-pipeline/scripts/human_review_operations_v1.py); existing approvers retain Authority |
| Shared Authority release provenance and checksums | [Authority release](../../deploy/creative-authority/authority_release.py) |
| Case publication, reviewer grants and private submission access | [Case Library Access V1](../design/CASE_LIBRARY_ACCESS_V1.md), [final Human quality contract](../../ops-pipeline/scripts/case_human_review_v2.py), [evidence revision and coverage owner](../../ops-pipeline/scripts/case_evidence_revision_v1.py), [display receipt/projection owner](../../internal-console/app/case_shared_display.py), [principal/access adapter](../../internal-console/app/case_library_access.py), [independent Approval authorization owner](../../ops-pipeline/scripts/case_console_authorization_v1.py); approved Case and production Authority retain their existing owners |

## History and evidence

The superseded [Working Architecture](../product/AI短视频代运营生产工作流与案例资产架构_V0.1_Working_Architecture.md), [Content Quality candidate](../product/Content%20Uniqueness%20&%20Editorial%20Quality%20V1｜产品与工程冻结框架.md), and [Customer Intake design record](../design/Customer%20Intake%20&%20Persona%20Onboarding%20V1｜产品与工程冻结框架.md) remain historical references. The [UI audit](../design/INTERNAL_CONSOLE_PRODUCTIZATION_UI_AUDIT_V1.md) is evidence for its recorded checkpoint, not the current UI specification. Approval receipts prove gates; neither receipts nor completed task projections create business requirements. Preserve valuable lineage under the Artifact Lifecycle rather than deleting old versions by age.

## Delivery baselines

The [Delivery index](../deliveries/README.md) routes delivery-scoped Baselines and
their approval status. [CREATION_BATCH_UX_1](../deliveries/creation-batch-ux-1/README.md)
has one [Approved / Frozen Baseline, Revision 1](../deliveries/creation-batch-ux-1/BASELINE.md).
The Founder selected D-P01/02/03 and requested target freeze; the earlier
[BR-01 decision](../deliveries/creation-batch-ux-1/BASELINE_REVIEW_RECORD.md) remains
the historical limited Current Truth review. The attributable target approval
chain is retained in [BR-02](../deliveries/creation-batch-ux-1/BASELINE_APPROVAL_RECORD.md).
[Plan Revision 5](../deliveries/creation-batch-ux-1/PLAN.md) retains its exact reviewed
bytes; the Founder has now frozen that R5 and approved restricted C01–C03/B1 scope
after G0. See the attributable [B1 execution record](../deliveries/creation-batch-ux-1/B1_EXECUTION_RECORD.md).
The user explicitly resolved DR-01/02;
Design Readiness is PASS for planning scope. Planning Preflight on actual R4 inputs is PASS; contract candidates, UI details,
responsibilities and isolated development environment checks are prepared. Old
reviews remain historical. Native qualifications remain source-specific.
B2–B4 implementation has now been requested with real Human acceptance deferred to the end;
the exact restricted A03/A04 engineering scope has now been explicitly approved.
The additional isolated 20/40 admission scope has also been explicitly approved;
capacity remains subject to staged Native validation. See the
[continuation record](../deliveries/creation-batch-ux-1/B2_B4_EXECUTION_RECORD.md).
B1 has not been independently accepted. These delivery documents do not supersede
machine Authority or authorize deployment or production use.

## Current boundaries

- `show_customer_status_v1.py` is read-only and derived-only.
- `operational_controls_v1.py` owns only explicit Operator Action Controls.
- Novel News has a separate implemented flow with default rollout `off`; validation access, supported opportunities and Scene Contrast gates are described in the RUNBOOK. Code presence does not establish production availability or completion of a real-customer gate.
- Production Asset Intake, Production Package, Video Production, Final Video QA, and Performance Learning are not implemented here.
- Historical artifacts and documents remain evidence. Historical does not mean deprecated.
