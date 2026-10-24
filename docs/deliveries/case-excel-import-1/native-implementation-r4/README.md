# CASE Excel V0.3 — JC-01 / EX-S2 R4 engineering review

本轮沿用 cxi HEAD `61efbc477ea28b9aee9a492d3ee96324718ef592`，保留已验收但未提交的 EX-S1/ME-R1 和既有工作区增量。当前功能身份由外置 `SOURCE_STATE.json` 的文件 SHA、实际 diff 及最终完整回归 fingerprint 共同确定，不能仅用 HEAD 代表未提交实现。

正常新案例：原生分析与 Evidence 审核完成后，审核页提前显示视频类型、投稿建议、可共享标题/摘要/行业和封面状态；审核员一次最终确认，由原 Review Command 持久化 Case Approval、独立 Type Decision、独立 Shared Publication。类型暂缓显式保存为 null，不采用 Excel 建议补值。历史案例类型补充、发布变更和撤回保持受控独立操作。

Excel 多行：本人已保存候选 → 有序行选择 → 来源与新任务数核对 → 一次有限解析确认 → 逐行原 EX-S1 准入。原 Task 容量、来源去重、上传 reservation 和 Unknown 不重发均保留。没有视频的行仍待补证；提交完成不等于审核通过。

- [准确授权及基线](AUTHORIZATION_PROVENANCE.json)。这是工程授权来源记录，不是替 Founder 或 ChatGPT 签署新的业务批准。
- [J1～J5 和三阶段恢复](JC01_CONTRACT_AND_RECOVERY.md)。运行机器 Schema 位于 `internal-console/app/case_joint_schemas.json`。
- [有限 EX-S2 与容量边界](EXS2_CONTRACT_AND_RECOVERY.md)。Pydantic 严格模型是唯一执行 Owner；评审导出的 Schema 只供校验。
- [字段权限与 Owner](SOURCE_OWNER_MAP.json)、[原34项及新增故障矩阵](TEST_AND_ACCEPTANCE_MAP.json)。精确执行结果以同代码最终 JUnit 为准。
- [隔离浏览器与 Founder 待消费样本](BROWSER_AND_FOUNDER_UAT.md)。1440/390/320 为浏览器视口测试，不表示真实设备或三个浏览器引擎通过。
- [验证及历史保护边界](VERIFICATION_AND_PROTECTION.md)。完整回归结果保存在独立证据目录，避免修改已运行输入。

原 R2/R3 审查包、收据和 Manifest 原字节保留。没有修改 Novelty、CIU、Content Ledger、Pattern/Compatibility 或客户事实；没有授予媒体生产复用权。真实模型解析质量、平台原视频真实性、生产运行和 Founder 最终产品验收仍未验证。
