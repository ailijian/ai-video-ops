# R5 冻结与 B1 执行记录

当前状态：R5 已按实际 Founder 确认冻结；仅 B1 受限范围获准。B1 尚未完成独立验收，B2～B4 未启动。

## 批准身份

Baseline Revision 1：`13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3`。
Plan R5：`f1ebd4283dc0e341aca7675c245e2c515cbab1e314af8843eee3e426831e07bb`。
两者原字节保持不变；Plan 内先前未授权状态是冻结前历史状态，以本次实际事件补充，不回写历史审批。

用户对绑定准确 R5 和 C01～C03 范围 SHA `90a1be5f929eb5e5d49627783aad8226bcf42d3fd9f251c8d3940760af05698d` 的问题明确回答：**“确认冻结并批准上述受限范围”**。
来源是本对话 `call_ef18fa60e8de45e38c8cb5bede1b5700` 第 0 项实际答复。
这批准工程范围及 Plan 冻结，不授予 Native 账号权限，不产生 Pattern、Compatibility、内容或 Publish Approval Receipt。

原始 [G0 送审材料](../../../.local/evidence/creation-batch-ux1-r5-final-gate-20261022/CREATION_BATCH_UX_1_R5_FINAL_GATE_REVIEW.md)、[实际合同范围确认](../../../.local/evidence/creation-batch-ux1-r5-final-gate-20261022/C01_C03_OWNER_CONTRACT_APPROVAL.json) 和 [真实冻结记录](../../../.local/evidence/creation-batch-ux1-r5-final-gate-20261022/R5_FREEZE_RECORD.json) 分别保留，原拟稿与原 ZIP 不覆盖。

[确认后独立归档](../../../.local/evidence/creation-batch-ux1-r5-freeze-confirmed-20261022/CREATION_BATCH_UX_1_R5_FINAL_GATE_REVIEW_FROZEN.zip) CRC PASS，SHA-256 `babc0b495d8843e1c66cb5cc803e0f03e6ea73ec5a1c8dd5ca587fc73a3c0777`。它包含原送审 ZIP 原字节及新增真实确认，不改写原历史包。

## 实施边界

原代码锚为 `ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd`；B1 起点为已提交的文档 Checkpoint `8ce3da2443d2b0e83edb5c67a8578a18a00805a3`，分支 `codex/checkpoint-creation-batch-ux1-plan-r5-20261022`，没有在 main 上直接修改，也没有新增提交。

先 persona 单条，原资格实际通过后接入 Native；首条独立审查实际 PASS 后，按既有受限授权扩展 Story/Conversion。C03 持久化与执行预检只消费已确认范围；保留原 Active Request、事实/人物、Pattern、Compatibility/Release、人审、发布确认、导出、Closure、Ledger 和 unknown 恢复所有权。

禁止 B2～B4、生产 Authority 写入、真实模型调用、4090 部署、AUTH/OIDC、Commit/Push/Merge。

## 当前实现范围

- [C01～C03 严格合同](../../../ops-pipeline/scripts/creative_style_contracts_v1.json)、[版本化 Style 规则](../../../ops-pipeline/scripts/creative_style_rules_v1.json) 与原消费者共同建立新 `generation-request-v1.1`，旧 v1.0 保持原身份。每个当前 Style 仅允许 1 条；稳定 Slot 在 Concept 之前分配，贯穿原审核、修订、发布与交付。
- Persona 须以人物已知职责/亲身实践为中心并使用合法第一人称；Story 须保留已批准的具体事件，不从业务事件推导个人经历；Conversion 须保留已批准价值、需求、适用条件和版本化中性 CTA。`primary_angle` 不充当正式 Style。
- 客户列表/详情进入 `/create/config`，继承原客户和适用已批准人物。阶段/自由组合、P/S 未分配、有限周期确认、Novel/Repurpose 分计、总 0 阻断、修改失效旧预检均在同一配置页。多条配置仅可编辑保存，B1 不派发整批。
- Console SQLite 草稿为按用户/客户隔离的可编辑意图，CAS 修订及服务端 operation key 防止旧保存覆盖和重复确认；不作为业务资格。原 capacity-preview 只读核对配置/事实/当前 Catalog/Release/Ledger，确认在原锁中重验。创建后接原 `resolve-sources`，再进入原 Native 页面，不自动生成或批准内容。
- 真实 Style/Slot 来源保留在 Native Request/Concept/content，Console 只投影 Style id/version/definition SHA；原 Template、Receipt、Closure、Ledger 不重编码、不重复写入。

## 可核验的执行与验证证据

[B1 当前机器结果](../../../.local/evidence/creation-batch-ux1-b1-20261022/B1_CURRENT_STATUS.json) 汇总准确源码清单、独立 Review 与最终验证结果。该证据由实际运行结果生成；本记录不预签 PASS，也不代替阶段接受。

- 改消费者前的原 Mix 隔离资格/交付通过，真实 Case/Pattern/独立 Compatibility/Release/Business/Speaker Gate 执行。
- 首条 persona 经四轮独立审查关闭 CR-001～012，准确 [PASS 原文](../../../.local/evidence/creation-batch-ux1-b1-20261022/review/persona-pass/RAW_OUTPUT.txt) 保留；仅此后才扩 Story/Conversion。
- `internal-console/tests/test_creative_style_native_v1.py` 在全虚构隔离客户上执行原 Gate、实际 HTTP/Task/Human/Publish/Export。三 Style 正负链、缓存拒绝不重发、部分确认/重登、同 key 冲突和历史 Ledger 保护按最终 XML 范围判断。
- `ops-pipeline/tests/test_creative_style_v1.py` 验证合同、当前/历史 Catalog、Style 事实及结构限制；单元合成引用本身不构成 Native 资格。
- [真实浏览器与分屏证据](../../../.local/evidence/creation-batch-ux1-b1-20261022/browser/) 区分早期只读预览与真实隔离 Console。完整 Persona 浏览器旅程包括原人工审核、独立 Publish 确认和已确认 Excel 下载；所有人物和来源均虚构，只有外部模型 transport 合成，禁止外网。
- 全量/受影响 runner 使用实际比较起点 `8ce3da2443d2b0e83edb5c67a8578a18a00805a3`，保留失败、超时、中止及后续最终结果，不能以历史 PASS 冒充当前通过。
- 独立完整审查新增 CR-013/014：校验链接导致未保存草稿丢失、旧异步回调覆盖重返页面。修复使用页面代次和原地 focus/scroll，回归覆盖 options/draft/mutation 三个等待边界；最终复审结果仍见机器记录，不在此代签。

## 证明边界与停止点

只准备 B1 独立验收候选。阶段接受与 Founder UAT 由独立控制方作出，B1 未验收不进入 B2。实际隔离 Pattern/Compatibility 只证明其精确测试来源和已激活版本，不能为真实客户授予生产资格。

20/40 条、跨 Request 批量调度、集中审核/汇总交付属于后续 B2/B3 范围；真实模型质量、成本、限流、吞吐与 Android/iOS 实机仍 `NOT_VALIDATED`。三种屏宽截图是桌面浏览器 viewport 证据。R5 原 Manifest 只校验冻结时材料；新源码与执行证据由 B1 新 Manifest 绑定，不改写原包。
