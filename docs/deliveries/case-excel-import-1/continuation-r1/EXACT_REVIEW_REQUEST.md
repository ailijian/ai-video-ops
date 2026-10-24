# 原生解析、审核与共享接缝送审

状态：`EXACT_CONTRACT_REVIEW_REQUEST / NO_INDEPENDENT_APPROVAL_RECORDED`。

本轮沿用已获批准的 I2 R2 私有保存；仅 EX-R1 本人列表/详情读取已实现。请独立审查下表精确范围，不以本文、测试通过或 AI 建议代替审批。当前代码基底为 `61efbc477ea28b9aee9a492d3ee96324718ef592`；实际未提交文件 SHA、diff、验证和保护记录随包提供。

| 决定 | 拟议版本与最小范围 | 原唯一 Owner | 批准前的停止点 |
|---|---|---|---|
| EX-S1 | `case-excel-native-submission-input-v1.0-proposal` / `case-excel-native-submission-v1.0-proposal`；独立明确提交、原 Task 同事务准入映射、不可变 companion、来源/权限重验、响应丢失恢复、worker 准入约束 | `case_intake_service` / `main.submit_case_analysis`，`task_service` / `database`，原 Source Duplicate / upload Owner | 不创建该迁移/接口/companion，不派发 Excel 解析 Task；原 R2 保存继续不派发 |
| ME-R1 | `case-excel-bound-notes-read-v1.0-proposal` / `case-excel-bound-notes-projection-v1.0-proposal`；已有合法 Native Attempt 的真实 Reviewer 只读绑定行，原文保持未核 | 原 Case Access、Evidence Review 与 Intake Row Reader | 不开放跨用户 Excel 读取，不以 reviewer grant 推导全部私有库权限 |
| CC-01 | `case-content-type-catalog-v1.0-proposal` / `case-content-type-review-v1.0-proposal`；可扩展类型目录、指定 Reviewer 明确确认、冲突/其它/待判断与版本失效规则 | 原 `case_classification` / Case Reviewer Owner | 正式类型继续 `null`；Excel 值仍仅为投稿建议 |
| CC-02 | `case-shared-display-v1.2-proposal`；由原 Shared Owner 绑定有效 Case Approval、类型决定及独立 Human Display 确认 | 原 `case_shared_display` / Shared Publication Owner | 不新增 typed 共享写入、不改原 v1.0/v1.1 收据；未核私有候选不进入共享库 |

字段和严格读取候选见 `CONTRACT_CANDIDATES.json`；原子性/锁与故障边界见 `NATIVE_SUBMISSION_DELTA.md`；I3 审核和展示边界见 `I3_APPROVAL_REQUEST.md`。候选路径、表名、版本均属送审设计，当前并不存在。

## 必须由独立审查核对的项目

1. EX-S1 的 Task 与映射同事务，所有原 Native writer 仍遵守活动任务/来源去重；新局部锁不冒充全局去重。终态重放与重析分开。
2. 意图发布、Task/映射提交、companion、投稿归属、schedule、worker 各故障点的恢复；来源过期、撤权、未知外部结果不能自动重发。
3. 同一来源的跨投稿用户隐私：不泄露对方 Case/Task/媒体/投稿说明，关联不能增加原权限。
4. ME-R1 必须有合法 Native Attempt 和准确 origin；只读必要原文，不晋升 ASR/Frame/Shot/Proof、许可或 Business Truth。
5. CC-01 保留 profile 与业务类型两个维度。建议的冲突处置 enum 是提案；未判断继续 null，不按 Excel 值自动确认，不自动新增 Production Style。
6. CC-02 两份独立 Authority 保留，旧共享收据不改；类型变更使旧 preview 失效，只有新明确共享确认能改变公开投影。
7. Schema 的 strict/未知版本策略、引用目录限制、Catalog 成员唯一性、当前 grant/版本/SHA、人审重放与撤回语义必须进入原 Owner 消费者的正负测试。

批准后，先 1 条虚构媒体薄切片：本人导入 → 我的投稿 → 明确提交解析 → 原生证据核对 → 原分类/人审 → 独立共享。随后验证响应丢失、双击、跨用户、撤权/过期、部分失败及旧收据兼容，再由 Founder 统一体验。真实模型质量、生产、部署和 Git 提交不在候选批准范围内。

本轮没有创建正式 Approval Receipt，没有代签 Founder/ChatGPT/原 Owner 决定。原始 B0 ZIP、R2、历史 Manifest/SHA 及已验收记录保持原字节。
