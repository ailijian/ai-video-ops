# CREATION_BATCH_UX_1 — Native Authority and Source Graph

> 本文件是 [唯一可编辑 Baseline](BASELINE.md) 的配套交付文档。原 BL-0 审计结论、目标、状态和证据范围保持不变；文中的审查包、自检、MANIFEST及运行结果指原历史快照，见 [交付入口](README.md)。

Status: Draft；Current Truth = CODE_PROVEN，测试适用范围见 ../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/TEST_EVIDENCE.json。所有源码行号为当前Checkpoint原文件的1-based行号。机器合同字段/枚举归源码与Schema；下文只解释所有权。

Checkpoint: `ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd`

```text
Business + Speaker → Creation Entry / Qualification → Native Request → Task (execution projection)
Case + Fingerprint → Approved Pattern → Compatibility decision → Release/Activation/live control
                                        ↓
Mix Source/Content Plan → Mix Generation ─┐
Novel opportunity → Novel News Beats ─────┼→ Native Human Review/Approved/Receipt
Historical semantic → Repurpose Slots ────┘              ↓
                          Publish Copy → explicit Human confirmation
                                        ↓
                          Native Export/Closure → business-wide Ledger
                                        ↓
                          versioned supplemental Delivery (zero exposure)
```

Task、capacity/read models、阶段目标、Draft、Case研究与可见性均不是第二业务Authority。补充交付可先委托原Native writer补完未关闭核心交付；已关闭的核心不重复。

## N01 — Business

- **唯一Owner/源码**：[S110](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S110.txt) `ops-pipeline/scripts/approve_persona_v1.py:78` `approve_persona`。
- **机器合同及版本**：`persona-v1.0 / persona-approval-receipt-v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：Customer fact review → build_persona_v1 → approve_persona_v1；GET /api/customers/{business_id} / POST persona/approve。
- **输入→输出身份**：Intake/Candidate/typed Human decisions → exact Approved Business revision + approval receipt；resolver resolve_current_persona。
- **不可变SHA / Receipt /路径**：data/personas/<business>/revision_*/persona_v1.json；file SHA + content SHA + approval source SHA。
- **人工Gate**：显式 Customer Truth Human Approval；原始Intake和AI分析不是Truth。
- **恢复、幂等、失效/撤回**：批准writer独占写入/恢复同一decision；当前限制及版本重新核对；旧Approved和Receipt不改写；未解决restriction阻断。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT03、CT25。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_customer_intake_persona_onboarding_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。 Case/Persona属于既有源域验证，不把其历史功能验收推广成新Batch证明。

## N02 — Speaker

- **唯一Owner/源码**：[S008](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S008.txt) `ops-pipeline/scripts/show_customer_status_v1.py:271` `resolve_speaker_persona`。
- **机器合同及版本**：`persona-v1.0 / persona-approval-receipt-v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：Speaker Fact Review/build/approve；GET /api/customers/{business}/speakers / POST /speakers/{speaker}/persona/approve。
- **输入→输出身份**：Speaker persona_id/revision → exact Approved Business revision/SHA binding；非按mtime选择。
- **不可变SHA / Receipt /路径**：data/personas/<speaker>/revision_*/persona_v1.json；Business ref + exact receipt SHA。
- **人工Gate**：独立Speaker Human Approval、first-person scope；发现候选≠批准/媒体授权。
- **恢复、幂等、失效/撤回**：Business版本变化需要原生revalidation/重新批准；当前不匹配fail closed；旧批准保留。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT03。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_speaker_persona_vertical_slice_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。 Case/Persona属于既有源域验证，不把其历史功能验收推广成新Batch证明。

## N03 — Case

- **唯一Owner/源码**：[S112](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S112.txt) `ops-pipeline/scripts/approve_case_v1.py:250` `main`。
- **机器合同及版本**：`case-v1.1-draft（Human审批后lifecycle.status变approved，schema仍保留）/ case-evidence-final-review-v2.0 / case-console-authorization-v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：Console Case final-review → canonical_gateway.approve_case_candidate → approve_case_v1.py main。
- **输入→输出身份**：case_id + exact attempt/candidate/ASR/shot evidence → Approved Case/receipt + Fingerprint。
- **不可变SHA / Receipt /路径**：data/cases/<case_id>/case_v1.json、approval_receipt.json、source governance companion；source media SHA只作来源证据。
- **人工Gate**：显式Case reviewer capability + final evidence Human Gate；shared display不是Approval。
- **恢复、幂等、失效/撤回**：source/role/quality不匹配阻断；幂等审批恢复保留原收据；研究不转Customer Truth、生产素材或Proof。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT05、CT24。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_case_customer_review_flow`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。 Case/Persona属于既有源域验证，不把其历史功能验收推广成新Batch证明。

## N04 — Pattern

- **唯一Owner/源码**：[S113](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S113.txt) `ops-pipeline/scripts/approve_pattern_v1.py:833` `approve_pattern`。
- **机器合同及版本**：`pattern-v1.0；News versioned Pattern uses exact approved definition/receipt`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：原生approve_pattern_v1；News独立 news_pattern_authority_v1_1.approve_pattern。
- **输入→输出身份**：candidate/research + exact supporting Case/FP scope → approved Pattern + receipt；不扩支持scope。
- **不可变SHA / Receipt /路径**：data/patterns/approved/<pattern>/pattern_v1.json；News versions/<version>/；Pattern与receipt SHA。
- **人工Gate**：Pattern Human Approval；News独立 news_pattern_reviewer。
- **恢复、幂等、失效/撤回**：来源/版本变化不由registry补批准；原批准不改写；不支持profile不得匹配。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT05、CT09、CT24。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_approve_pattern_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。 Case/Persona属于既有源域验证，不把其历史功能验收推广成新Batch证明。

## N05 — Compatibility

- **唯一Owner/源码**：[S088](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S088.txt) `ops-pipeline/scripts/profile_compatibility_decisions_v1_1.py:390` `decide`。
- **机器合同及版本**：`compatibility v1.1 Mix / v1.2 News executable SCHEMAS`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：Console profile_compatibility_gateway → production_profile_v1.decide_compatibility_v1_1 → delegated decide。
- **输入→输出身份**：exact target snapshot/preview SHA + actor/current grant + parent → append-only Human decision。
- **不可变SHA / Receipt /路径**：data/production_profiles/compatibility_v1_1/；Case/Pattern/profile/rules exact refs；grant receipt不是接收机权限。
- **人工Gate**：profile_compatibility_reviewer；News news_profile_compatibility_reviewer；与Case reviewer独立。
- **恢复、幂等、失效/撤回**：approve/reject/withdraw per exact target；revoke/regrant变化令旧preview失效；fork/缺parent fail closed；无新Batch权威。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT24。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_profile_compatibility_v1_1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N06 — Release

- **唯一Owner/源码**：[S124](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S124.txt) `deploy/creative-authority/authority_release.py:263` `build_release`。
- **机器合同及版本**：`creative-authority-release-v1.1/v1.2 + activation/runtime config contracts`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：deploy/creative-authority/authority_release.py build_release → verify_release → stage_release_v1_1 → activate_release_v1_1（本轮不执行）。
- **输入→输出身份**：exact committed reader/source + selected decision graph → immutable bundle/manifest → activation receipt/active pointer。
- **不可变SHA / Receipt /路径**：source Git blob SHA与checkout SHA分列；artifact SHA是原始字节；manifest binds parent release/activation。
- **人工Gate**：显式stage/activate并核live control；local approval不自动生效；News隔离qualification/Founder eligibility独立。
- **恢复、幂等、失效/撤回**：current live decision digest/withdrawal fence在新写入重验；unavailable/stale失败关闭；完成历史可读；isolated包不能生产安装。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT24、CT09。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`authority-release:test_authority_release`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N07 — Creation Entry / Qualification

- **唯一Owner/源码**：[S001](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S001.txt) `ops-pipeline/scripts/content_creation_entry_v1.py:466` `build_content_creation_entry`。
- **机器合同及版本**：`content-creation-entry-v1.0；read-only projection`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：GET /api/create/options → content_gateway.list_creation_options；POST /api/create/capacity-preview；Novel preview独立。
- **输入→输出身份**：business_id/speaker_id/profile/requested_quantity → capacity/recommendation/feasibility/blocker + source refs。
- **不可变SHA / Receipt /路径**：projection引用Approved Personas/registry/ledger来源SHA；不生成新的Authority Receipt。
- **人工Gate**：真实Business/Speaker/Fact/Restriction/Pattern/Compatibility资格；确认容量不是内容批准/媒体权利。
- **恢复、幂等、失效/撤回**：可缩量，不padding；no capacity、未批档案、失效sources阻断；阶段预设不属于当前资格。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT01、CT03、CT09、CT25。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_content_creation_entry_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N08 — Request

- **唯一Owner/源码**：[S013](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S013.txt) `ops-pipeline/scripts/generation_request_handoff_v1.py:742` `create_generation_request_handoff`。
- **机器合同及版本**：`generation-request-v1.0 / generation-source-planning-handoff-v1.0；Repurpose news-delivery-request-v1.0/v1.1`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：POST /api/create/confirm；Repurpose POST /api/create/news/request → news_delivery_v1.create_news_delivery_request。
- **输入→输出身份**：Business+idempotency key → gen_* immutable Request / handoff；Repurpose news_* binds source_content_id + original semantic SHA。
- **不可变SHA / Receipt /路径**：data/generation_requests/<rid>/generation_request_v1.json；Repurpose data/news_deliveries/<rid>/news_delivery_request_v1.json；persona/source/SHA及确认snapshot。
- **人工Gate**：explicit_operator_confirmation；仍 human_review_required；News显式opportunity或历史source选择。
- **恢复、幂等、失效/撤回**：same key/same payload恢复；changed payload冲突；同Business/profile active锁；resolve_generation_request仅合法unapproved disposition；不改旧Request。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT04、CT09、CT11。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_generation_request_handoff_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N09 — Task

- **唯一Owner/源码**：[S061](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S061.txt) `internal-console/app/task_service.py:401` `submit_task`。
- **机器合同及版本**：`SQLite migrations + content-operation-response-v1.1（执行投影，非业务schema）`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：background_task_service/create_background_task → task_service.submit_task；GET /api/tasks/{id}。
- **输入→输出身份**：operation_identity + subject/request_id + execution payload → task_id/status/lease/progress。
- **不可变SHA / Receipt /路径**：SQLite operation identity/immutable Native attempt refs；Task ID不是Approval SHA或Receipt。
- **人工Gate**：Session/CSRF/queue admission；Task completed不批准内容。
- **恢复、幂等、失效/撤回**：active dedup、lease recovery、native reconciler；unknown provider outcome不自动重发；completed native replay返回原Task或null。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT17、CT18、CT14。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_generation_recovery_http_task_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N10 — Mix Plan / Generation

- **唯一Owner/源码**：[S022](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S022.txt) `ops-pipeline/scripts/resolve_generation_batch_v1.py:1507` `resolve_generation_batch`。
- **机器合同及版本**：`content-plan-v1.1.1 / generation-batch-v1.0 / generation-recovery-*-v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：POST /api/create/{rid}/resolve-sources → /resolve-content-plan → /generate-scripts。
- **输入→输出身份**：Request+Source Plan+final selected Concept+memory → Batch contents content_id/concept_ref/slot_id；profile=mix。
- **不可变SHA / Receipt /路径**：data/production_plans/<rid>/、content_plans/<rid>/、generation_batches/<rid>/；effective Batch由recovery graph选取，不按mtime。
- **人工Gate**：Approved事实/first-person范围、privacy、Pattern/Compatibility、novelty/quality；生成后Review仍独立。
- **恢复、幂等、失效/撤回**：C3-05仅zero-output transport/response故障；partial不获通用regen；source/memory变化停止旧operation。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT05、CT06、CT07、CT08、CT15。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_resolve_generation_batch_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N11 — Novel News Generation

- **唯一Owner/源码**：[S047](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S047.txt) `ops-pipeline/scripts/novel_news_v1.py:444` `generate_novel_news_plan`。
- **机器合同及版本**：`novel-news-beat-plan-v1.0 / novel-news-generation intent/dispatch/response/result v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：POST /api/create/novel-news/{rid}/generate / retry-generation → novel_news_generation_gateway。
- **输入→输出身份**：one selected Novel opportunity + Request/source exact binding → 4–8 ordered fact-grounded Beats / one video。
- **不可变SHA / Receipt /路径**：data/generation_batches/<rid>/novel_news_beat_plan_v1.json；private attempts contain exact Request/source/response SHA。
- **人工Gate**：Native News qualification/release、Known Fact Atoms、Scene Contrast额外controlled-validation gate若适用；不创造新事实。
- **恢复、幂等、失效/撤回**：REC-01 dispatch未知不重发；明确retry append parent，saved response本地恢复；late worker fenced；source/actor变化阻断。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT09、CT10、CT14。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_news_generation_recovery_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N12 — Repurpose Plan

- **唯一Owner/源码**：[S035](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S035.txt) `ops-pipeline/scripts/news_delivery_v1.py:1779` `resolve_news_delivery_plan`。
- **机器合同及版本**：`news-delivery-plan-v1.0/v1.1；news-slot-recommendation-v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：POST /api/create/news/{rid}/resolve-plan → news_delivery_gateway.resolve_news_plan。
- **输入→输出身份**：exact historical semantic source/Request → ordered presentation Slots；4–8不是多视频。
- **不可变SHA / Receipt /路径**：data/news_deliveries/<rid>/news_delivery_plan_v1.json；source semantic canonical SHA、Pattern/release refs。
- **人工Gate**：重表达不得新增Customer Truth或Ledger semantic；符合News资格与事实/限制。
- **恢复、幂等、失效/撤回**：same Request计划验证/复用；source/qualification变更停止；不会转为Novel。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT11、CT24、CT25。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_news_repurpose_runtime_v1_2`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N13 — Human Review

- **唯一Owner/源码**：[S118](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S118.txt) `ops-pipeline/scripts/review_generation_batch_v2.py:542` `review_generation_batch_v2`。
- **机器合同及版本**：`generation-batch-review-input-v2.0 / review-v2.0 / approved-generation-batch-v1.0 / approval-receipt-v1.0；News各自Human schemas`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：Mix POST /api/create/{rid}/review；Novel /novel-news/{rid}/review；Repurpose /news/{rid}/review。
- **输入→输出身份**：exact source Batch SHA + content item decisions / Beat/Slot decisions → Native Review/Approved/Receipt。
- **不可变SHA / Receipt /路径**：Mix generation_human_review_v2.json、approved_generation_batch_v1.json、generation_batch_approval_receipt.json；News approved_novel_news / approved_news_delivery。
- **人工Gate**：显式approved/revised/rejected；机器passed仅允许进入review；approved subset可导出；AI或Task不批准。
- **恢复、幂等、失效/撤回**：snapshot-bound authenticated decision；partial Receipt只续原intent，不猜批准；source/role/constraints变化重验；历史不改写。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT12、CT10、CT11、CT13。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_review_generation_batch_v2`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N14 — Publish Copy

- **唯一Owner/源码**：[S073](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S073.txt) `ops-pipeline/scripts/publish_copy_v1.py:387` `confirm`。
- **机器合同及版本**：`publish-copy-source-snapshot/generation-intent/draft/confirmation/result-v1.0；frozen publish-copy-v1.schema.json`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：GET/POST /api/create/{rid}/publish-copy/{generate|edit|confirm} → publish_copy_gateway/native owner。
- **输入→输出身份**：exact Native approved Mix/Novel/Repurpose → source snapshot/target IDs → publication title/body/topics，News production headlines mapping。
- **不可变SHA / Receipt /路径**：原Request下publish_copy_v1/{attempts,drafts,confirmations}；model/prompt/owner/target/memory/source SHA。
- **人工Gate**：单独显式Human确认当前draft_ref；每条制作行对应完整字段；不代替Native内容批准/平台发布/媒体权利。
- **恢复、幂等、失效/撤回**：≤5 targets/call；unknown不重发；partial保留、edit新draft；new source/memory/actor conflict阻断；生成剩余保留已编辑targets。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT19、CT20。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_publish_copy_native_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N15 — Delivery / Supplemental Export

- **唯一Owner/源码**：[S077](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S077.txt) `ops-pipeline/scripts/creation_delivery_v1.py:134` `export`。
- **机器合同及版本**：`creation-supplemental-delivery-{intent,prepared,receipt,completion}-v1.0 / creation-delivery-effective-version-event-v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：POST /api/create/{rid}/publish-copy/export → Native Mix/Novel/Repurpose export_supplemental_delivery；GET .../excel/{delivery_id}。
- **输入→输出身份**：exact confirmed draft + original Native Closure/Receipt/anchor → versioned XLSX + Receipt + delivery-scoped Completion/effective chain。
- **不可变SHA / Receipt /路径**：原Request下deliveries/<server_id>；template/XLSX SHA、parent expected_head、confirmed production/derived version SHA。
- **人工Gate**：Native production approval + publish copy确认 + current sources/permission/Compatibility；未完整确认不可导出。
- **恢复、幂等、失效/撤回**：Intent→stage→Prepared→exclusive publication→Receipt→Completion→effective；重放只补缺失一致记录；zero semantic/exposure/presentation delta；不创建第二业务Closure。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT21、CT22、CT23。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_publish_copy_process_recovery_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N16 — Native Export / Closure

- **唯一Owner/源码**：[S119](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S119.txt) `ops-pipeline/scripts/close_generation_export_v1.py:407` `close_generation_export`。
- **机器合同及版本**：`generation-export-closure-v1.0；mix-excel-export-receipt-v1.1；Novel/Repurpose receipt/closure v1.1兼容完整v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：Mix /export-mix；Novel /novel-news/{rid}/export；Repurpose /news/{rid}/export → 原Native writers。
- **输入→输出身份**：approved exact bundle + validated workbook → original Export Receipt/Closure + Native Ledger effects。
- **不可变SHA / Receipt /路径**：Mix generation_batches/<rid>/generation_export_closure_v1.json + actual output .export_receipt.json；Novel novel_news_export_receipt/closure；Repurpose news_dynamic_excel_export_receipt/news_delivery_export_closure。
- **人工Gate**：Human批准来源+完整Receipt验证；Task/文件存在不代表可下载。
- **恢复、幂等、失效/撤回**：News Intent/Prepared恢复，无bound evidence的孤儿阻断；completed replay no duplicate Task/Closure/Ledger；Mix无historical anchor时旧reader仍按原规则。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT13、CT16、CT17、CT23。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_news_export_recovery_http_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N17 — Ledger / History Anchor

- **唯一Owner/源码**：[S084](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S084.txt) `ops-pipeline/scripts/ledger_history_v1.py:269` `validate_anchor`。
- **机器合同及版本**：`content-ledger-v1.0 / news-presentation-history-event-v1.1 / generation-export-anchor-evidence-v1.0 / content-ledger-native-transition-v1.0`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：原 content_quality_v1.replace_ledger_after_export / Mix close / Native News writers调用shared history mechanics；无Batch新Ledger。
- **输入→输出身份**：Business-wide approved exported content + authentic snapshots → semantic/presentation history；Novel semantic+1，Repurpose semantic+0。
- **不可变SHA / Receipt /路径**：data/content_ledgers/<business>/content_ledger_v1.json；original Ledger byte snapshot/canonical hash + deterministic parent/transition receipt。
- **人工Gate**：approved/exported precondition；历史anchor仅证明历史，不给新内容Approval/媒体权利。
- **恢复、幂等、失效/撤回**：Business锁+history锁；full-object Native recipe验证，缺parent/fork/crossBusiness阻断；缺旧snapshot不能重建；supplemental delta全部0；open memory exact SHA不随新history自动改绑。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT23、CT30、CT10、CT11。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`console:test_ledger_history_process_recovery_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## N18 — Fact / Privacy Projection

- **唯一Owner/源码**：[S116](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/source/S116.txt) `ops-pipeline/scripts/content_quality_v1.py:2049` `build_fact_atom_catalog`。
- **机器合同及版本**：`fact_atom_version来自FACT_ATOM_VERSION；catalog为list，无独立顶层Schema；privacy safe_verbatim projection`。未单列JSON Schema者由对应writer/strict validator拥有，不能臆造schema文件。
- **HTTP / Gateway / Console入口**：原生planning/generation/closure委托Fact Atom catalog与privacy_projection_v1.project_value；无独立批次Fact批准入口。
- **输入→输出身份**：Approved Known Business/Speaker facts + exact persona SHA → source-bound Fact Atom IDs / safe model context。
- **不可变SHA / Receipt /路径**：Fact Atom引用原字段、Known fact、persona byte SHA；私有raw intake、biography、Case事实不变Customer Truth。
- **人工Gate**：Fact来源必须已由原Persona Human Gate批准；projection自身不批准事实或Proof。
- **恢复、幂等、失效/撤回**：原事实/Persona/限制变化使open source snapshot不再匹配；隐私规则在remote前生效；不得猜补unknown字段。
- **当前版本状态**：原生链源码存在；适用资格范围必须同时读取 CT03、CT19、CT25。News只能在已资格隔离范围验证，非生产上线证明。
- **已执行测试证据**：`pipeline:test_content_quality_v1`；在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/` 的对应 historical exact-commit JUnit投影查实际case；本轮新增测试另列。

## 历史保护边界

旧Persona、Case、Pattern、Compatibility decision、Approval、Native Receipt、Closure和Ledger字节不因新Batch重写。新的限制/撤回封锁新写入；历史完整记录用原version reader验证。原生 source/permission conflict不会由Task恢复或“阶段推荐”消除。

Publish Copy 的 Human confirmation仅覆盖派生发布表达；既不批准制作源，也不授权平台发布。新Delivery的Completion不等于另一份业务Closure。News Repurpose只记录presentation，禁止重复累计semantic。

本包只含源码/Schema及脱敏证据投影，不包含客户原始资料、运行数据库、真实视频、凭据或真实Ledger字节。原业务Receipt SHA只能与保留的受控来源核对；不能用Git blob SHA代替。

历史锚不足的旧记录继续阻断。不存在用当前Ledger伪造旧snapshot、手改Authority JSON、绕过live Compatibility或将Case素材提升为Production Rights的授权。
