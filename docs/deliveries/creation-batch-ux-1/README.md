# CREATION_BATCH_UX_1 — 交付文档入口

返回：[Delivery 索引](../README.md) · [Knowledge and Operations Index](../../operations/README.md)

**唯一当前 Baseline 是本目录的 [BASELINE.md](BASELINE.md)**，仓库路径为
`docs/deliveries/creation-batch-ux-1/BASELINE.md`。已批准目标只能经明确批准的 Amendment 修改。
`.local` 中的原 `review/BASELINE.md` 是保留的历史审查快照，不再继续编辑，不能作为另一份当前 Baseline。

当前状态：**Baseline Approved / Frozen / Revision 1**。用户要求冻结，并明确采用
D-P01三类定义、D-P02合计推荐后代理商明确分配方案A、D-P03 Novel默认/Repurpose独立选择。
AC-01～07保持原义，新增AC-08～10承接三项产品决定。当前事实、资格、容量未知和历史证据没有变成新功能通过。
本轮DR-01/02产品规则已明确确认，Design Readiness已按当前输入复核；R4已按R3输入完成Planning Preflight，仍待原审批及独立Plan Review，
**Plan Freeze和B1～B4实施仍未获授权**。

[BR-01 审查记录](BASELINE_REVIEW_RECORD.md) 及其 [机器记录](BASELINE_REVIEW_RECORD.json)
保留此前仅批准Current Truth、整体目标仍Draft的历史身份，不是本次目标冻结记录。

## 可编辑交付文档

| 文件 | 用途 |
|---|---|
| [BASELINE.md](BASELINE.md) | 唯一已批准目标；边界、三项冻结规则、当前事实与保留约束 |
| [FOUNDER_TARGET.md](FOUNDER_TARGET.md) | 原Founder目标输入；旧未决由Baseline已批准规则补充，不构成平行 Baseline |
| [CAPABILITY_MATRIX.json](CAPABILITY_MATRIX.json) | 类型、Native Owner、能力状态和未验证范围 |
| [AUTHORITY_AND_SOURCE_GRAPH.md](AUTHORITY_AND_SOURCE_GRAPH.md) | 现有原生所有权与源码关系 |
| [GAP_REGISTER.md](GAP_REGISTER.md) | BL-0差距快照；产品决定的当前状态以Baseline为准，机器能力缺口不自动关闭 |
| [BASELINE_EVIDENCE.json](BASELINE_EVIDENCE.json) | 原 BL-0 源码、SHA、摘录和测试证据索引 |
| [BASELINE_REVIEW_CHECKLIST.md](BASELINE_REVIEW_CHECKLIST.md) | 独立审查检查表；保留原作者自检的时间范围 |

## Plan Revision 5 — 开工材料准备完成，等待真实放行

当前[PLAN.md](PLAN.md)及执行配套为R5，Baseline仍Approved/Frozen Revision1。R4原始输入/Manifest保留新证据目录inputs/r4，原R4及更早所有.local包不变。DESIGN_OPTIONS与PRODUCT_DECISION_REGISTER刻意保留R3原字节和产品来源；R5只细化既有合同、UI实现资产和阶段责任，不重做Design判定。

| 当前材料 | 内容与范围 |
|---|---|
| [PLAN](PLAN.md) | R5精确阶段、依赖、UI状态/动作/响应式与放行边界 |
| [机器合同候选](MACHINE_CONTRACT_DELTA_PROPOSAL.md) | C01～08字段、Style判据、A03小容量建议、A04父链/Prepared/Receipt时序；均未批准/实施 |
| [责任分工](OWNER_AND_DEPENDENCY_MAP.md) | 当前Codex准备/技术作者责任，实施职责提案、Founder决定、独立Plan/代码审查与原生actor界限 |
| [Gate](IMPLEMENTATION_GATES.md) | B1不等待A03/A04，真实运行资格与工程范围决定分开，原ID/状态未伪改 |
| [测试/UAT](TEST_AND_UAT_MATRIX.md) | 环境已核对、新能力最早接缝与三端真实旅程；未运行的仍NOT_RUN |
| [审查及批准请求](PLAN_REVIEW_CHECKLIST.md) | 一站式具体对象/条件/范围决定，无预填批准 |
| [原产品决定](PRODUCT_DECISION_REGISTER.md)、[设计输入](DESIGN_OPTIONS.md) | 原R3实际字节不变，无重复Founder产品问题 |
| [Manifest](PLAN_MANIFEST.json)、[校验](PLAN_SHA256SUMS.txt) | 当前完整R5身份，旧Manifest保留旧包和新inputs |

本轮[Preflight实际结果](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/evidence/PLANNING_PREFLIGHT_RESULT.md)已在R4输入PASS。[机器可读提案](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/proposals/NATIVE_CONTRACT_CANDIDATES.json)、[样本](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/proposals/STYLE_ACCEPTANCE_SAMPLES.json)、[范围表](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/proposals/ADMISSION_AND_DELIVERY_REVIEW_SCOPE.json)和[环境检查](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/evidence/ENVIRONMENT_READINESS.json)均可复核。JSON检查不是Native资格，环境可用不是新功能通过。

当前缺的外部动作已集中成具体请求：准确R5独立Plan裁决/Freeze、相应工程合同范围决定及B1明确许可；原Native资格在依赖生成前真实取得。A03/A04分别在B2/B3前，可一并送审，不提前阻挡B1。当前作者不代替独立审批、不发grant/Receipt、不实施B1。

本轮审查包：[CREATION_BATCH_UX_1_PRESTART_REVIEW.zip](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/CREATION_BATCH_UX_1_PRESTART_REVIEW.zip)。旧R4审查包原样保留，并作为新包嵌套历史身份链。可从原R4包恢复原Preflight/NCR38和R3 Design/实际用户决定，再由旧嵌套包追溯Baseline审批链。历史副本不是编辑入口。

代码仍main/ceac；只有本目录及导航文档改变。未改功能代码、生产Schema、原Baseline/客户/收据/Ledger、工作树或Git refs；没有安装新依赖、模型/服务/部署、Commit/Push/Merge。Stage开始时刷新实际输入边界，不在准备阶段建立新Checkpoint。历史批准来源仍见[BR-02](BASELINE_APPROVAL_RECORD.md)和[原独立裁决](PLAN_INDEPENDENT_REVIEW_RECORD.md)。

## 保留的原审查包与证据

原目录 `.local/evidence/creation-batch-ux1-baseline-20261022/` 中的文件保持原样，
没有删除、覆盖、迁移或重新打包。以下链接用于读取历史证据，不是编辑入口：

- [原独立审查 ZIP](../../../.local/evidence/creation-batch-ux1-baseline-20261022/CREATION_BATCH_UX_1_BASELINE_REVIEW.zip)
- [原审查 MANIFEST](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/MANIFEST.json)
- [原 CRC / SHA 校验结果](../../../.local/evidence/creation-batch-ux1-baseline-20261022/ARCHIVE_VERIFICATION.json)
- [原 SHA256SUMS.txt](../../../.local/evidence/creation-batch-ux1-baseline-20261022/SHA256SUMS.txt)
- [原测试证据](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/TEST_EVIDENCE.json)
- [原 Checkpoint 与历史保护核验](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/CHECKPOINT_AND_PROTECTION.json)
- [原 Founder 接受范围](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/FOUNDER_ACCEPTANCE_PROJECTION.json)
- [原作者终检](../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/FINAL_SELF_CHECK.json)

| 历史对象 | 原 SHA-256 |
|---|---|
| `CREATION_BATCH_UX_1_BASELINE_REVIEW.zip` | `357b518aabe1eefe3db0004b218512e9f26f6be6ccc8f1ae61ad4eee5c879575` |
| `review/MANIFEST.json` | `b9555b3613a590352c0e4c4889843282044e66855c95aef857fb01bf31a90014` |
| 原 `review/BASELINE.md` | `bbcd3414b97ad6ff3587912df29de4644c7a4c27a68dfd39ce0b6a87bb61054a` |

原 MANIFEST 仅校验原审查包。归位后的文档增加位置说明并修正引用，其字节 SHA 会变化，
不能用原 MANIFEST 或原 Baseline SHA 校验本目录，也不能把原作者自检解释为归位后的新验证。

## 引用与后续边界

- 当前系统合同链接回仓库原 Owner；冻结源码摘录、原运行结果与 Receipt 证据仍指向原 `.local` 快照。
- `BASELINE_EVIDENCE.json` 中 `sources[].path`、`test_source_path` 等原源码路径继续以仓库根为基准；
  `excerpt`、`junit_projection` 和运行证据 `record` 的文件引用以本交付目录为基准，已调整为历史证据路径。
- `.local` 被 Git 忽略，不随普通 clone 分发。复核历史运行证据需要本机保留目录或原 ZIP；
  这一限制不影响从仓库和记录的 Checkpoint 找到源码及合同。
- 后续只在本目录维护交付文档；保留原历史材料。文档归位不授权编写 Plan、实施功能、自动提交、推送或部署。

上述“归位不授权 Plan”是原归位事件的边界；后续用户已明确授权规划与开工准备。本轮STOP在具体材料送审处，不冻结、不实施、不提交或推送。独立批准、工程合同决定和阶段许可须真实取得，不把材料准备完成写成全部开工条件通过。
