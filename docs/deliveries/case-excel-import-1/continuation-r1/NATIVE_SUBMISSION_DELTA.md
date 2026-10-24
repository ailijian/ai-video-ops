# EX-S1 / ME-R1 最小待审合同

状态：`PROPOSED / WRITE_IMPLEMENTATION_NOT_AUTHORIZED`。本文件不是批准收据。

## 原生当前事实

`case_excel_import.save` 只保存私有 Row/Intent/Result，`dispatch_model=false`；原 `main.submit_case_analysis` 经 Source Duplicate、媒体 Provider、上传及 Task Owner 准入。`task_service.create_case_task` 当前 `operation_identity=case_analysis:<case_id>`，支持现有活动任务去重，不包含 Import Row/Intent 身份。不能用“恰好是同一视频的最新 Task”证明本次提交成功。

原 R2 的 Import Source 锁只协调私有候选，不是覆盖所有 Native Writer 的全局锁。原 Case Reviewer 也没有因此获得任意用户整个 Excel/所有候选的读取权。

## EX-S1 拟议输入与状态

原 Intake Owner 新增独立版本的 Native Submission companion；旧 Batch/Row/Intent/Result 与其 `false` 标志均不改写。严格候选 DTO 在 `CONTRACT_CANDIDATES.json`，必须绑定：

1. 服务端真实 principal（namespace、用户 ID）、原 Batch ID/SHA、原 Row ID/SHA、原导入操作/Intent SHA、文件/模板来源。
2. 当前合法来源 URL/视频身份、真实 Native Upload Receipt/媒体 SHA 或既有合法来源获取方式；客户端只提交可选择的引用，不提供 owner/Case ID/批准标志。
3. 用户显式提交意图、单操作 ID、输入摘要、期望 parent；提交按钮与“保存未核候选”分离。纯文字/无合法来源不派发，过期上传明确重新绑定，不用文件名或过期引用替代媒体。
4. 归属原 Task Owner 的精确 Native Task/Attempt 标识及其输入摘要。新 Analysis Result 仅证明提交/关联状态，不证明 Case Approved、证据已核或共享。

## 原子性与恢复审批点

- **必须先解决的确切缺口：**当前 Native Task 创建与新的 Canonical 提交关联不是单一原子事务。若 Task 已创建、companion 尚未发布便退出，仅凭来源或最新任务不能完成精确重放。
- 建议原 Task Owner 增加专用、版本化的可恢复准入身份：由同一数据库事务核对 actor、origin digest、稳定 intent 与实际 task_id；这是调度身份/进度索引，不是新的业务批准或第二套 Case 数据。不能挪用 `review_operation_id` 的人审语义。
- Canonical companion 使用原 write-once。需要审查“提交意图发布 → 原 Task 准入 → 精确任务关联 → 原投稿归属 → schedule”的每个故障边界；响应丢失只恢复同一准入，不重复创建任务。
- 原备份 barrier、Task 数据库事务、upload cleanup 锁、actor/reviewer 锁的完整组合顺序必须由原 Owner 冻结。不得在持有原 upload 锁时嵌套一个再次取得同锁的通用 HTTP handler。
- 已有其他用户私有 Case/Task 时仅提供无泄露结果；不能从同 URL 推导获得其明细或任务所有权。同用户合法重放仍须精确来源与原操作身份。
- 共享 GPU guard、队列限制、活动 Task 去重、取消/重析、人审 grant、权限撤回均沿用。模型结果未知不自动再次请求；外部获取/模型副作用未确定时不能仅重放新 operation 凑“成功”。

以上是本次精确送审范围，不宣称该机制已实现或已获批准。若原 Owner 选择其他方案，必须给出相同恢复/隐私证明，不能静默降低为来源模糊关联。

### 待批准的最小调度表与事务候选

由原 Console `database` / `task_service.submit_task` Owner 拥有一张仅作调度关联的 `case_excel_native_admissions_v1` 表。候选列为 `namespace TEXT NOT NULL`、`user_id INTEGER NOT NULL`、`operation_id TEXT NOT NULL`、`origin_sha256 TEXT NOT NULL`、`submission_input_sha256 TEXT NOT NULL`、`task_id TEXT NOT NULL REFERENCES tasks(task_id)`、`created_at TEXT NOT NULL`；主键 `(namespace,user_id,operation_id)`，禁止以 Excel key 或来源 URL 作该主键。没有 Case Approval、类型或 Evidence 字段。其记录不能单独证明 Case 权限，恢复仍需 Canonical Intent、实际 Task payload/actor、当前授权与来源证据同时匹配。

- 在原 Task 准入的同一个 `BEGIN IMMEDIATE` 事务中，先验证 actor 当前有效，再比较该操作已有映射；同输入只返回原 Task，变更 origin/input 摘要冲突。新 Task 插入及其映射必须一起提交。不得先创建 Task 后另启事务补映射。
- 已有原生活动 Task 的去重仍使用 `case_analysis:<case_id>` 及其原规则。只有原 Duplicate Owner 明确允许、且当前用户有权读取准确 Task 时，才可在本事务建立关联；跨用户私有重复仅返回原生安全反馈，不写入其 Task ID/私有 Case 详情。终态 Task 不通过“最新一个”猜测关联，重析须新的明确意图和原重析授权。
- 在调度事务前 write-once 发布版本化 Canonical Submission Intent。事务后按映射发布只追加的关联 companion 和原 `record_submission`，再允许 `schedule`。worker 对带此 origin 的 Task 需验证 companion/投稿归属已完成；恢复只补齐同一映射和同一 Task，不能创建替代任务。没有合法 companion 的新 Task 保持待恢复，不能执行模型。该新消费者约束也属于 EX-S1 待批范围。
- 候选锁序：原 shared `authority_backup_gate` → 新的本人 submission-operation 锁 → 已绑定的原 `source-upload:<id>` 锁 → 原 Task DB 短事务。R2 import-save/source 锁不持有到模型执行，写入时不重入通用 HTTP 网关；不在 DB 事务中等待文件锁/外部网络。原所有者须核对其与 upload cleanup、备份、Reviewer 重析及所有 Task writer 的交叉顺序；如发现反序，先调整候选并重审，不能声称新局部锁已覆盖全系统。

| 故障边界 | 准确恢复行为候选 |
|---|---|
| Canonical 意图前失败 | 无 Task；同操作输入重新核验后建立意图 |
| 意图已写，Task 事务前失败 | 原意图保留；重新准入并重验来源/权限，过期时阻断并要求明确新绑定意图 |
| Task/映射已提交，companion 前失败 | 精确读取该 actor/operation 映射；校验原输入与 Task；只补原 companion/归属，不新建 Task |
| 归属或 schedule 前失败 | 同 Task 恢复已有准入，不重复收据；worker 不越过未完成 companion |
| 响应丢失或终态后重放 | 读取原关联及实际 Task 状态；不恢复旧媒体授权，不重复分析 |
| 外部获取/模型结果未知 | 原生恢复规则；停止自动重发，不以新操作/新 Task 掩盖 unknown |

拟新增 `prepare`、`submit` 和读取原提交状态三个接口，均限制本人 Import Row；`submit` 必须真实 Session、CSRF、明确确认及准确预检摘要。路径由原 Intake Owner 冻结，不把现有 R2 `save` 改成暗中派发，也不改变其历史响应。上述表、迁移、Task payload、worker 准入、接口及 companion **均未创建/未实施**。

## ME-R1：原文不变、审核视图最小授权

原 Excel Row 可作为 `unverified_submitter_candidate` 私有说明。只读显示不提升其信任等级。投稿者先看本人原文；正式 Reviewer 在合法 Native Attempt 形成后，才允许通过该 Attempt 的精确 origin companion 读取绑定行的必要说明。

需单独批准的 Reader 必须同时验证：当前 reviewer grant/namespace、Case/Attempt 权限、Row/文件/关联 SHA、归属与提交意图。不得直接调用 owner 参数伪装成原投稿者，不允许扫描该用户其他行/批次。撤权、来源变化、跨 Attempt、错误 SHA 均拒绝。

人工结构、口播、画面、秒数、许可和类型建议只供对照，不能写进 ASR/Frame/Shot/Proof 或当作 Shared Display 默认文案。真实媒体与原 Evidence Review、Human Quality、Case Approval 继续成立。文字-only 记录可留待补证，不创建虚构 Case/Attempt。

## 批准后的最小试验与验收

先 1 条虚构真实媒体走 Native Submission，再验证双击、Task 创建后退出、companion 发布中断、响应丢失、撤权、同源跨用户、上传过期及重析。只在外部模型边界注入合成结果，原 Source/Task/Review/Shared Gate 不替换。此列表目前为待执行，不能标 PASS。
