# I2 精确写入合同送审（候选，未批准）

本轮只完善待审批材料，未实现持久化。原 I1 核心解析审查通过；新增上传预览是独立的无业务写入接缝，不代表 I2 获批。

候选 Schema：[I2_EXACT_WRITE_CONTRACT_R2_PROPOSAL.json](I2_EXACT_WRITE_CONTRACT_R2_PROPOSAL.json)。原提案 SHA：`be12957c9a2937a3542c3c13c08d233b363a8c589c4336186558dc6d4df8ac84`；新提案 SHA：`b483223d796fb7d2c233c436dfda100d2cdfe6a5ca6b7b21f33483824f4b58dd`。旧提案和原评审 ZIP 保留。

## 唯一存储 Owner 与身份

原 Case Intake Owner (`app.case_intake_service`) 负责候选 Batch/Row/Intent/Result。拟议私有 Canonical 路径 `ops-pipeline/data/case_intake_imports/<owner_user_id>/<batch_id>/` 尚未创建。SQLite 只能索引候选身份，不能替代原 Canonical 或成为 Case Approval。

Batch 绑定服务器主体验证后的 owner、原文件 SHA、模板、字段注册表 SHA、解析器版本/SHA。Row 绑定工作表/行号、原 external_case_key、原始21字段、分段、许可说明和 SHA。Excel编号不是 Case ID。同用户同文件同意图恢复同一批；不同字节或同 operation 不同 intent 返回冲突。新增精确 `row_source_bindings` 将每行身份与服务器解析的 canonical source、真实 NativeUploadRef、媒体 SHA 一对一绑定；禁止只用全局回执列表含糊关联行。

保存范围只有未核私有投稿候选；不得调用 `dispatch_groups`、`create_case_task`、正式 Case Approval 或共享发布。三种模式均不提升人工说明、类型建议和许可声明的证据等级。候选所有人不继承 Reviewer grant。

## 真实 Native 去重与锁，及待批准 Delta

现有 `case_intake_service.create_group` 用 SQLite `BEGIN IMMEDIATE` 保护用户/client_request_id/digest；它保存链接分组，并非本提案的 Excel Canonical 候选。`main.dispatch_intake` 有进程内 RLock；`task_service.create_case_task` 委托 `submit_task`，用 `case_analysis:<case_id>` 和数据库即时事务约束原生任务。视频 ID/source duplicate reader 决定实际原 Case 身份。**源码未证明存在可直接复用、覆盖全部 Native 写入者的“全局来源文件锁”。** 旧文档中的该项只能解释为待审协调要求。

新提案明确区分 import-source 私有候选协调锁与原正式 Source/Task 去重。拟定锁序列已列于 JSON；具体键域、backup barrier 适用性、跨 writer 原子性及存储恢复仍须原 Owner 批准。I2 保存不保留正式 Case/Task 名额，也不借候选锁声称原生全局占用。未来独立授权派发时重新走原 Native Gateway 去重和真实来源资格；不得把候选保存转换成自动派发。

## 媒体绑定、过期和隐私

只复用已存在的 `case-source-upload-v1.0` 回执和 `{upload_id, receipt_sha256}` 引用。`case_source_upload_v1.read_upload` 核对 canonical source/video、上传者、实际媒体 SHA/size；`app.case_uploads.validate_for_submission` 追加当前24小时和既有任务使用约束。该回执是上传者声明，不能授予平台原创性或媒体生产权。

原存储文件名为 videoID+suffix，不证明 Excel 中的原文件名。必须由用户明确选择真实同用户上传，并由服务端绑定；仅文件名且未上传/未明确来源时保留 pending/null，不搜索本地磁盘，不伪造媒体存在。没有批准的导入 retention Delta 时不延长24小时，不调用正式 `reserve_review_upload`。以后每次准入/恢复重验；过期、媒体被清理或 SHA 变动 -> pending/明确重传，产生新 intent，不改旧候选或悄悄换源。

跨用户相同来源只给不泄露的“来源待核对”状态，不暴露别人的 Case/媒体/任务/回执/投稿者。本人重放可在已验证本人范围内恢复原结果。I3 正式分类和 Typed Shared Display 继续独立待审。

## 原子保存与恢复候选

先鉴权/CSRF/输入与预期head，独占写入 PREPARED Intent；按稳定行序逐项原子 write-once+fsync 写候选与行 Result；所有行有明确结果才发布最终 Result/head。部分成功必须标 partially_saved/recovery_required；不得 all-success。候选已写而响应丢失或行 Result 未写时，在同锁与同 intent 下只恢复准确 SHA/owner 的确定性引用；不得再造候选或任务。不确定状态停在 recovery_required。取消只针对尚未保存行，保留已存历史。双文件发布/目录 fsync/Windows崩溃一致性属于待实现故障注入，不报 PASS。

## 审批前置与待执行测试

A1：精确 Schema、存储域、完整锁序和现有 Source Owner 接缝、跨用户输出、head/CAS、部分写入及响应丢失恢复；A2：人工观察保留未核等级；A3/CC-01/CC-02：以后正式分类与共享，仍不在 I2 授权内。必须明确批准新文件和精确 SHA 后才能写业务候选。

待执行：双击/重放/改 intent409；每个写入点进程中断；跨用户同源且不泄露；同源不同 Excel key；上传清理/过期/重新绑定；当前会话撤权；本地文件名无真实媒体；无 Task/Approval/Share 副作用。本轮只验证 Schema 结构及引用完整性，没有把未来持久化场景报成功。
