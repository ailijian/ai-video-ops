# R2 实际消费者与恢复合同

本文件解释已获受限工程授权的R2实现；原提案、Manifest和历史SHA保留。它不批准正式Case或生产政策。

## Owner和不可变身份

唯一Owner为 `app.case_intake_service`，委托 `case_excel_import.py`；私有Canonical在 `ops-pipeline/data/case_intake_imports/<authenticated_user_id>/<batch_id>/`。不新增SQLite业务表，不向会自动派发的原 `case_intake_groups` 写候选。

Batch ID由服务端用户、原文件SHA、精确解析器源SHA和冻结注册表SHA确定。Row ID绑定原行号、案例21字段、全部分段和许可说明；Row SHA是实际不可变JSON字节SHA。Excel编号不是Case ID。原工作簿只在显式保存时私有保留。

Row仅代表投稿原文：`source_upload=null`、`formal_video_type=null`、`approval_granted=false`、`evidence_promoted=false`。当次真实上传绑定在不可变Intent的 `row_source_bindings` 中；过期或重传不能反向改写旧Row。Intent严格绑定主体、Batch/Row SHA、操作、上传和head；选择与Binding一一对应，回执SHA集合恰好等于绑定投影。客户端只选择upload_id，不能提供owner或伪造receipt/media SHA。

## 既有来源与媒体规则

页面明确确认上传权限/来源后调用原 `/api/cases/source-files`。保存在原 `source-upload:<id>` 锁内复用 `validate_for_submission` 和 `case_source_upload_v1.read_upload`，校验同用户、准确原视频、回执及媒体SHA/size、24小时和原Task使用限制。不延长生命周期，不借正式人审reservation。文件名不能证明媒体身份；纯文件名保持pending。

上传回执为操作人声明，不授予平台原创性、生产复用权或Proof。原source duplicate Reader仍控制实际Case身份；私有保存不创建/预留Case或Task。新import-source锁只协调私有候选，不是覆盖全部Native writer的全局Source锁。

同用户跨编号/文件同源投稿保留新原文，并关联本人已有引用，不另建原Case。其他用户的候选、Case、Task、媒体路径和回执不返回。候选所有人不继承Reviewer；相同来源不会成为跨用户探测私有资料的接口。

## 锁、head与发布

固定顺序：原backup shared barrier → actor/operation锁 → actor/Batch锁 → 所选source的排序import-source锁 → 排序原upload cleanup锁 → 短SQLite即时事务核对当前Session/CSRF/账号并发布记录。没有网络或模型派发；每行重验权限，撤权停止后续写入并保留已存字节。

JSON复用原 `write_once` 独占hard-link publication和文件fsync；工作簿使用同类原子二进制发布。顺序：operation reference → 原文件 → Batch → PREPARED Intent → Row → 私有source reference → Row Result → 最终Result。已发布文件不覆盖，未确定行不报成功。

head定义为Batch最后一个已准入Intent的实际字节SHA；`expected_head_sha256`形成单链，由原记录派生，无第二套可编辑真相。新意图在Batch锁内CAS；原准确意图可重放。链分叉、未知版本、主体或SHA不同均阻断。完成Result不表示Human Approval。

## 恢复、过期与取消

同actor/operation与同输入恢复原不可变Result；不同输入冲突。已完成重放不要求当年媒体仍存在；当前可用性另作读取投影。读记录时重新验证上传；过期、媒体变化或已被原Task使用则pending，旧绑定不能授权新操作。

中断从确定的原Row/回执恢复，不创建第二个候选或Task。I/O未确定时返回recovery_required投影，不伪造最终收据。已发布PREPARED Intent的记录支持页面刷新/重登恢复。Batch/Intent之前的中断需原文件和原意图重试，此时尚无候选行。不能重验旧媒体时明确阻断；可取消未保存行后用新意图明确重传，不静默换源。

取消是新用户意图，绑定当前head并留下定向取消引用；只关闭原操作未保存部分，已保存行和历史Result保留。定向取消不阻断未来新意图。Case Approval、原Receipt/Closure/Ledger不迁移。

持久化的取消Intent本身决定停止，逐行取消引用只是可恢复索引。即使刚写取消Intent就退出、逐行引用尚未发布，旧保存重放也直接遵守该决定；未保存且已取消的行不再要求过期媒体重新合格。这不会给任何新行放宽来源资格。同一页面、同一所选文件的上传引用可复用，但prepare/save始终由原Owner重新核验，不以浏览器缓存授予有效性。

## 网关与限制

| 接缝 | 行为 |
|---|---|
| 原POST `/api/case-excel/preview` | I1只读，无业务写入 |
| POST `/api/case-excel/imports/prepare` | 有界JSON/XLSX，计算精确身份，不持久化 |
| POST `/api/case-excel/imports/save` | 原Session/强制改密/CSRF后，仅保存候选 |
| GET `/api/case-excel/imports`、`/{batch_id}` | 仅本人、no-store，当前媒体状态独立投影 |
| POST `/{batch_id}/recover` | 本人、CSRF、原Intent SHA，恢复原保存 |
| POST `/{batch_id}/cancel` | 本人、CSRF、精确head，结束未保存部分 |

8MiB JSON只用于容纳原5MiB XLSX的base64及有界元数据，不是生产容量承诺。未知字段/版本、重复JSON key/选择、伪造回执字段拒绝。原XLSX安全校验复用；人工原文转义、不执行公式或模型。

证据覆盖进程级崩溃及真实合成视频检测；未做宿主机断电实验，未证明生产配额/retention/备份发布。生产、真实模型及I3继续独立Gate。以后若实施分析派发，仍须原Native Source/Task/Reviewer/Case Authority，本轮没有该按钮或后台消费。
