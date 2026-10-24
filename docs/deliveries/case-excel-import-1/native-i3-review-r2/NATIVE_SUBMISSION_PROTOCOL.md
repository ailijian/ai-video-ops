# EX-S1 / ME-R1 精确候选协议 R2

`PROPOSED / NOT_IMPLEMENTED`。表名、路径、字段、API 均为本包候选；实际现状绑定 SOURCE_OWNER_MAP.json 的函数与 SHA。

## 原生事实与本轮新增发现

原 CaseAnalysisRequest/submit_case_analysis 解析正式来源、检查重复与媒体 Provider，再调用 create_case_task → submit_task；原 operation_identity 为 `case_analysis:<case_id>`。Task 的短 BEGIN IMMEDIATE 事务去重 queued/running/awaiting_review，随后 schedule/record_submission 发生在事务外。R2 Excel 保存不走此路径，亦不调用 dispatch_groups。

原 recover_expired_tasks 在无法用原生结果对账时可能把 running 改回 queued；CaseTaskRunner.schedule_pending 会再次调度。因此“旧租约已过期”绝不是“外部调用没有发生”的证明。新的 Excel origin 若只加关联表而沿用该默认行为，会留下 unknown 重发风险。本包要求原 Task Owner 同时批准新 origin 的受限执行/恢复栅栏；不声称旧 Native Case 全局协议已经解决该风险，也不借用 Novel News REC-01 收据证明 Case 行为。

## 身份与准入

- 原 R2 Batch/Row/Intent/Result 不改。新 submission intent 由真实 Session 的 namespace/user_id、原 Batch/Row/导入 Intent/Result SHA、原文件/模板、预检摘要和单操作 ID 绑定。所有路径与 SHA 由服务端 Reader 重新解析，客户端只回传已选择引用，不能提供 principal、Case ID、Task ID、批准或证据标志。
- prepare 是只读预检；submit 独立 Session+CSRF+明确确认。预检绑定当前登录、原 head、Row/Result、当前来源/上传、Provider 配置和原 Native 资格。来源、head、权限或版本变化即失效；不静默换来源。
- 首期只接受原 Native Source Owner 已支持的来源。当前主要为合法抖音原始/短链接经原 resolver 规范化，加当前有效上传或已有正式获取方式。只有本地文件名、纯文字、缺少原视频身份或其他未支持平台，继续待补证，不构造随机 Case ID。新增来源平台或无链接独立媒体身份不在此次最小授权内。
- 首期 EX-S1 明确 submit 只处理一行；可以顺序处理多行，但不开放另一个批量队列，不自动处理全部导入行。零资格项不能为了展示成功而派发。

## Canonical 与事务

候选 Canonical 路径：`data/case_intake_imports/<user_id>/<batch_id>/native_submissions/<operation_id>/intent.json`、`association.json`；现有 Row 和 false 标志不迁移。新 intent write-once；原 Task Owner 唯一调度表的候选 DDL 在 ADMISSION_TABLE.sql.proposal，文件不放入 migrations，也未执行。

同一 BEGIN IMMEDIATE 中：重新验证当前 actor；检查稳定 `(namespace,user_id,operation_id)`；比较 origin/input 摘要；运行原 Native active-source/queue/GPU pending/上传去重；新 Task 插入与精确 admission 映射一起提交。不得复用 review_operation_id。既有 Task 的来源规范化、权限及 payload 必须一致；终态不能按“最新 Task”猜测，新重析须新的明确操作及原 Owner 准入。

新增 Task payload 只增加 server-owned `excel_native_origin`（origin digest、submission intent ref、operation ID）；不得把 Row 人工结构、类型建议、许可声明直接写进正式 ASR/Shot/Proof。所有旧 Task payload 保持原样。

候选锁序：原 authority_backup_gate shared → 新本人 submission-operation 锁 → 原 scoped case 锁 → 原 source-upload 锁（如有）→ 原 DB 短事务。Reviewer 当前 grant 的读取/决策遵循原 case→reviewer→DB，绝不在 DB 中等待文件锁/网络。不重入通用 HTTP handler；backup/cleanup/旧直接提交/分组/重析/worker 路径必须在实施前做锁序核对。旧直接提交只有 upload→DB，不增加对 case 锁的反向等待；DB 原 active identity 仍是所有 Native writer 的最终去重约束。若实际实现发现反序，停止该提交，不宣称新局部锁覆盖所有 writer。

事务后只按同一映射补 association 和原 record_submission，再调度。worker 对新 origin 在 claim 前验证关联/原投稿已完整，claim 与 execution_claimed CAS 由同一 Task 事务持有。只有 relation_kind=new_origin_task 可由此路径执行；已关联的旧 owned Task 不改 payload，不重新执行。

## 外部结果未知与媒体生命周期

execution_claimed=1 只表示可能开始执行，不能证明已有模型结果，也不能证明尚未调用。新 origin 的过期/崩溃不能自动再次排队执行：优先由原 Native Attempt/结果 Reader 对账终态；无法证明时保持原 Task 的 failed/待恢复投影，明确 unknown 阻断。只有原 Owner 可验证的未派发状态才允许恢复初次执行；已 claimed 的不确定任务不凭新 operation、时钟、AI 标记或人工“批准”强制重发。若原 Owner 无法证明安全恢复，报告阻断；本合同不创造第三方 exactly-once 能力。

原 cleanup 对无 Task 或 failed 的旧上传可能在24小时后清理。新准入 intent 在 upload 锁内写不可变 `source_upload_reservation.json`，绑定 owner、upload/receipt/media SHA、source、input digest。cleanup 仅保护通过原 Reader 验证的未完成准入/unknown hold，不因任意同名文件保留媒体；仍走 source-upload 锁。未建立 Task 的 intent 24小时后失效，必须重新预检；已绑定 Task 的 reservation 跟原 Task/retention 生命周期，unknown 未解决时不得静默释放。终态完成、明确已取消且无在途副作用，或原 Owner 已解决 unknown 后才解除 hold；旧 receipt 不删除，损坏 hold 失败关闭并报告，避免误删。此 cleanup 读取扩展也在 EX-S1 待批范围，不延长无业务依据的任意上传。

## 去重与权限

同一来源、不同 Excel 编号不能创建重复 Case/活动 Task。只有原 Owner 确认当前用户本来就拥有/有权读准确 Task，才返回 linked_owned_task；不能因此改变 created_by。已有 Task 不增加新的 primary origin，不把此行说明偷偷追加给旧审核；ME-R1 首期只读新 Task 的唯一 primary-origin 行。

跨用户私有重复只记录本人意图已处理的泛化结果，task/native input ref=null；不创建其 Task 关联、不调用 record_submission 增加其归属、不泄露对方 Case/Task/媒体/说明。已有共享内容仍由原 Shared Reader 返回其合法公开字段，不能由同 URL 推导私有权限。

## 每个故障点

| 窗口 | 候选恢复 |
|---|---|
| intent 之前 | 无 Task；重新预检 |
| intent/reservation 后、DB 前 | 只重验同一 intent；过期/撤权阻断，不替换上传 |
| DB 已提交、association 前 | 按 actor+operation 的精确映射补原 association/投稿；同 Task，未完整前 worker 不执行 |
| 关联后、schedule/响应前 | 同映射只调度未 claimed 的原 Task；读取返回原结果 |
| claimed 后进程退出/租约过期 | 原生结果对账；unknown hold，不自动重复外部调用 |
| 已有 owned Task 或已终态后重放 | 原准确身份只读返回，不创建新 Task/收据/分析 |
| 双击、换输入同 operation、过期 parent | 同输入幂等；不同输入/parent 明确409，不覆盖旧关联 |

## ME-R1

GET 精确 Case/Attempt 的绑定说明。要求真实当前 Reviewer grant+Case/Attempt 可读权限、Task primary-origin payload、association、Row/Intent/Result/文件 SHA 与 namespace 全部匹配；不接受客户端任意 owner/批次选择。不伪装投稿者调用 `_authorized`，由原 Access Owner 明确委托最小 Row Reader。普通投稿者继续只能看本人记录。

允许输出：标题/主题/Hook/结构、人工口播/画面/分段/秒数、风险及许可声明、建议类型/观察依据；每项保留 `unverified_submitter_candidate`。不返回整本 Excel、无关行、上传文件真实路径、token、完整原始私有证据。说明仅供人审对照，不进入正式 ASR、Frames、Shot、Proof、客户事实或共享文案默认值。撤权、错误 Attempt、非 primary origin、SHA 变化拒绝。

## 字段、迁移和摘要的精确补充

NativePrepareInput / NativeSubmissionInput 是客户端DTO；NativePreview、NativeSubmissionIntent、NativeTaskOrigin、NativeSubmissionRecord 和 UploadReservation 是服务端生成/复验的候选。NativeTaskOrigin 只有新 Task 的 primary origin；SQL partial unique index 禁止一个 Task 对应两个 new_origin_task。拟新增迁移名 009_case_excel_native_admissions.sql 当前不存在，只有本目录 .sql.proposal；若并行工作占用该版本则先重审，不覆盖旧迁移。

所有旧 R2 摘要仍使用原 encoded/record_sha 的准确规则。新逻辑摘要沿原 authorization digest 的 sort_keys/紧凑 UTF-8 约定，文件 SourceRef 使用实际文件字节 SHA，两者不能混作同一身份。NativePreview.preflight_sha256 / TypedDisplayPreview.preview_sha256 各自计算时只排除自己的摘要字段，避免自引用；所有其他资格、父版本、权限和来源字段都必须纳入。目录、Intent 时间由服务端确定，重放不新写时间或换源。

reanalyze_explicit 必须绑定原失败/拒绝 Attempt、理由、当前权限及原 Native Owner 的可重析判断，原结果 unknown 未解决时不允许创建替代 Task。schema 的非空字符串不等于有效人审理由，仍须服务端去空白及业务约束。首条 thin slice 只使用 analyze_new，不把重析或其它来源的缺口隐藏为成功。
