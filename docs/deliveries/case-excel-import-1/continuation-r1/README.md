# Excel 候选到原生 Case 的接缝收口

基底：`61efbc477ea28b9aee9a492d3ee96324718ef592`。原 V0.3、R2、审查 ZIP、Manifest 和已验收记录保留；本目录不重新签发旧审批。

本轮直接用户指令：“按这个方向继续推进，先补齐剩余接缝的最小合同和审批材料，已授权部分继续开发，打通‘导入→我的投稿→解析→审核→共享’。保留现有权限、来源、幂等和人工审核规则，I3 未批准部分先送审，不自动提交，最后统一验收。”

| 接缝 | 当前授权与本轮处理 |
|---|---|
| EX-R1：本人 Excel 候选 → 我的投稿 → 精确行详情 | 本轮明确要求的只读整合；复用 R2 原 Reader，实现并隔离验证，不产生 Task 或批准 |
| EX-S1：精确候选 → 用户明确提交原生解析 | 精确持久化/Task 绑定合同待原 Case Intake/Task/Source Owner 审查；本轮仅送审，不扩写原 R2 的 `dispatch_model=false` |
| ME-R1：投稿说明 → 原生审核对照 | 本人查看已有未核原文属于只读范围；向另一审核人开放特定行及其与 Native Attempt 的绑定待审，不能从 reviewer 身份推导整个 Excel 私有库权限 |
| CC-01 / CC-02：正式业务类型确认与带类型共享 | I3 仍待独立批准；沿用原 Case Approval 和 Shared Publication 的两份独立 Authority，不新增第二套批准 |

当前已验收的是预检、私有保存、刷新查回。只读整合不等于整条解析/审核/共享链路已可运行。正式写入范围以新的独立审查结论为准；本轮统一 Founder 验收留到获批后完整链路形成时。

## EX-R1 实际读取合同

- 原 `app.case_intake_service` 委托 `case_excel_import` 生成本人候选卡片；唯一数据仍为 R2 Canonical。只使用实际登录 Session，不拼造 token，不新增 SQLite 业务表。
- `/api/cases?view=mine` 合并现有原生投稿与本人 Excel Row；shared/review 视图不因此增加候选。保存不会自动创建链接分组、Task、Case、分类或共享记录。
- 每张卡片稳定绑定 Batch/Row/原操作及 SHA。沿真实 head 链选择该行最新操作，不能用 UUID 文件名顺序代替版本顺序。未知最终保存结果显示“保存待确认”。没有持久化 Row 的未保存项不伪装为案例。
- `case_id`、正式 `video_type`、解析 `task_id` 均为空；Excel 类型单独显示“投稿建议”。时间字段在原合同缺失时为空，不采用 mtime 或当前时间伪造投稿时间；排序使用已有时间与稳定身份。
- 卡片链接进入原操作的精确 Row，只读查看本人原文。无效或不属于原操作的 Row 明确报错，不能静默切换到其他内容。刷新、重新登录保留该行身份。
- 来源当前有效性使用 R2 原 Reader 重验；“上传当前有效”只表示未核上传绑定，不能表示解析准入。原文、许可声明、人工秒数、投稿建议类型全部仍为未核。
- 缺少或变化的登录权限、未知版本、损坏 SHA/链均失败关闭；不把读取失败当作 0 或偷偷漏掉记录。响应 private/no-store，普通投稿者不获得审核能力。

## 送审材料

- [候选提交原生解析、人工说明接缝](NATIVE_SUBMISSION_DELTA.md)
- [I3 精确审核/共享决定候选](I3_APPROVAL_REQUEST.md)
- `CONTRACT_CANDIDATES.json`：严格字段与版本候选，写入部分均为 PROPOSED。
- `OWNER_AND_SOURCE_MAP.json`：本轮真实 Owner、函数行号及 SHA。
- `TEST_MATRIX.json`：区分本轮只读实测、原生既有证据及审批后才能运行的项目。
- `VERIFICATION.md`：实际执行结果与剩余 Gate，不以文档状态代替测试或审批。

不自动提交、推送、合并或部署，不运行真实付费模型，不变更 Reviewer grant、Novelty、CIU、Ledger 或生产资格。

## Console 完整回归收口补充

2026-10-24：cxi 1013 项、cc2 884 项均零失败/错误/跳过，原协调器状态保护通过。见 [超时诊断与真实最终收据](CONSOLE_REGRESSION_TIMEOUT_ROOT_CAUSE.md) 和更新的 [验证记录](VERIFICATION.md)。本补充仅关闭 Console 验证缺口，未批准上表待审合同或 I3。

## 当前精确送审入口 R2

2026-10-24：未批准接缝的当前候选为 [Native / I3 独立审查 R2](../native-i3-review-r2/README.md)。R2 明确 EX-S1、ME-R1、CC-01、CC-02 和五项待决产品规则；原 R1 候选及旧 ZIP 保留。它们均未获得新合同批准，不能解释为整条解析/审核/共享链路已经实现。

本轮已授权 EX-R1 另修复显式空 row= 退回整批的身份检查；当前聚焦 Python 11 项（含 JS 聚合）、Node 261 项通过。上文 1013/884 全量结果属于上一轮准确输入，不能当作新 JS 字节的全量验证。
