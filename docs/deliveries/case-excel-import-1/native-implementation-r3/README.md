# Excel Native 接缝 R3：实施与剩余合同

当前工程基底：61efbc477ea28b9aee9a492d3ee96324718ef592，分支 codex/checkpoint-case-excel-i1-i2-founder-uat-20261024。当前未提交增量的准确身份、diff 和保护以本轮外置 SOURCE_STATE/PROTECTION_RESULT 为准；不是新的 Commit。

R2 ZIP d4942ebe6820cb4335b685111602a9d199289dde193f90b8be09154160ae8701 与范围绑定 4f19ff4dfc02b5f4246350f6a3d11e928e8cf853ec312689d0b2087ec12a224b 均保持原字节。本轮直接裁决来源见 AUTHORIZATION_PROVENANCE.json；它只证明工程范围，不是 Case/Type/Shared 业务审批。

## 已实施的受限接缝

- EX-S1：本人准确 Row 的只读预检、明确单行提交、原 Task 和 admission 同一 SQLite 事务；Canonical companion/原投稿回执完整前 worker 不 claim。任务身份、队列、GPU lane、媒体与来源去重均复用原 Owner。
- 新 origin 的 claim marker 与 Task claim 同事务；租约失效且原 Native 结果不能对账时，原 Task 显示结果未知，不自动重新排队。旧 URL/上传/分组的 Task Owner 也拒绝绕过该 unknown 记录创建替代任务。
- 上传 reservation 由原 Upload cleanup Reader 复验准确 intent/owner/source/SHA/24小时期限；未知执行保留媒体。损坏 hold 失败关闭并记录原因，不能把任意文件当保留许可。
- 只有文件名、纯文字或不受支持的来源继续待补证，不编造 Native URL/Case ID。保存 Excel Candidate 仍不派发模型。
- ME-R1：当前真实 Reviewer + 准确 Case/Attempt/primary-origin 才能读取白名单未核说明。人工文本、分段、秒数、类型和许可声明不升级为 ASR/Shot/Proof/客户事实/媒体权利/共享字段。无任意私有批次浏览和投稿者身份冒用。
- UI：单条详情固定主按钮按状态切换“核对来源→确认解析→查看原进度”；丢失响应保持原操作编号。本人列表准确关联原 Task，避免额外出现一张重复的 Native Task 卡片。审核页只读显示未核说明，不增加强制类型或共享按钮。

## 严格合同及兼容

机器 Source 为 internal-console/app/case_excel_native_schemas.json；保持 R2 的准确 schema_version 字符串（包括已有 -proposal 后缀），不通过改名迁移旧记录。jsonschema Draft202012Validator 是声明的运行依赖，Schema JSON 随 app 包发布。TypeCatalog.version 统一为整数；新目录示例为1，旧 R2 示例和归档不改写。真实 Draft 2020-12 正反测试见当前测试文件/JUnit。目录仍只是候选，没有正式分类 Writer 或批准目录写入。

原 I2 false 标志、Row、Batch、Receipt 不迁移覆盖；新增 companion 只记录单行解析意图/关联。SQLite 009 仅是原 Task 的调度身份约束，不成为 Case、Review 或 Ledger Authority。

## 本轮停止的准确接缝

原 v1.2 联合命令只绑定 Case Approval + Shared Publication。它不签署正式类型选择，严格结果 Reader 也没有第三阶段。依本轮 Gate R1，CC-01/CC-02 接缝 STOP，送审 [JC-01 与 EX-S2](COMMAND_AND_BATCH_APPROVAL_REQUEST.md)。原批准后默认安全共享的已验收流程保持；没有退回三次强制确认。

单行 EX-S1 没有稳定多行 manifest/逐行恢复协议；原 link groups 自动派发，不能冒充这份协议。依 Gate R3，EX-S2 多行编排 STOP，等待准确范围批准；不新增第二套 Task System。

完整“Native分析→人审→正式类型→安全共享”新闭环、34项完整场景、联合操作故障矩阵和 Founder 最终 UAT 均未通过。本包只能申请 EX-S1/ME-R1 受限独立审查，不能输出完整 CASE_EXCEL_IMPORT_V03_READY_FOR_INDEPENDENT_REVIEW。

## 实际验证与边界

已执行证据在项目 .local/evidence/case-native-r3-20261024/：聚焦 JUnit、全 JS、原生HTTP、真实 Session 浏览器、真实可解码全虚构视频上传。1440/390/320 是桌面浏览器视口，不是三种物理设备/浏览器验证。刷新、重登、原 Task 导航与“我的投稿”唯一关联已观察；Browser fixture 的分析/模型 worker 关闭，不能把 queued Task 当作 Native Analysis 或质量通过。Fixture source identity 仅隔离测试，平台原始身份未验证；不为生产独立上传伪造 URL。

当前正式全仓 tools/verify.py 的真实结果、运行ID、JUnit数量和源状态以外置 FULL_REGRESSION_RESULT.json 为准，不在此预填 PASS。不借用旧1013/884全量 Console 数量。R2_34_SCENARIO_STATUS.json 明确未完成项；错误、失败初次记录保留。真实模型、生产/4090、发布部署、Push/Merge、AUTH/OIDC 均未执行；不自动提交。
