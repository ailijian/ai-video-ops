# EX-S2 finite confirmed orchestration

原 Case Intake 为唯一批次提交协调Owner，原 EX-S1 创建Task，原Task/Case/Review/Shared Reader投影状态。没有新Task数据库、模型Worker、审核或Case生命周期。

`orch_<32hex>` 绑定当前用户namespace、Import Batch/head、原保存Intent、有序去重Row集合与各Row SHA。每行保存准确Native preview及预检来源、受支持URL与真实Upload Receipt；确定性native operation不跨行复用。预览的新Task数量排除已有、关联及待补证。准备/保存候选本身不派发模型。

一次有限确认后，原Owner逐行调用EX-S1；仍使用现有用户/队列容量。每行不可变Result引用原association；中断仅补缺失记录/未准入行。重复操作读取原意图，不产生第二Task。Task已claim而结果未知时原生UNKNOWN fence不允许租约超时自动重发。

暂停/继续/结束使用 `control_<32hex>` 和原控制head CAS，控制历史不可变。直接EX-S1在原Task事务内也核对该有限意图，不能绕过暂停或取消。取消只标记尚未准入行；已进入Task或Unknown保留原状态。跨用户重复来源只有通用重复说明，不泄露或关联他人私有任务。

锁顺序：原Authority backup共享屏障 → 有限意图操作锁 → 原EX-S1 source/upload操作锁 → 原Task SQLite立即事务/当前Session校验。已持有屏障时只由可信内部调用传递 `_barrier_held`，HTTP不能指定，避免Windows不可重入屏障自锁。暂停控制也受原授权DB事务序列化，行准入在事务内重核。

准确运行边界：页面在当前登录/CSRF下按原确认每4秒尝试推进未准入行；关闭页面/退出后，未准入行保留，回到原入口继续。已准入Task由原Worker独立运行。未创建绕过当前Session的后台批次派发器，不将页签关闭后的待准入任务宣称自动完成。

状态来自原Reader：待解析、待补证、重复、失败/Unknown、已提交、待审核、已收录待共享、已收录并共享。`submission_complete`仅表示本次有限行集合已处理，不表示全部视频分析完成或审核通过。已完成本人原行在新意图中只读取原关联状态，不计新任务。

15行隔离测试包含4个真实Upload/Task、11行无有效媒体或文字待补证；其中两个通过真实Human/类型/共享，另一条真实媒体指纹重复被拒，一个排队。没有为凑15个Task提升待补证内容。网页独立场景已有3个Task，确认15行仅新建1个，状态与本次新建数分别展示。
