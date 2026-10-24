# CC-01 / CC-02 精确候选协议 R2

状态仍为 PROPOSED；没有新的分类或共享审批。原 Case Approval 与独立 Shared Publication 两份 Authority 继续存在，类型决定不代替二者。

## CC-01 目录与人审

原 case_classification 当前只确认行业和 observed source profile，且明确 operator_labels_only；Shared display 当前 video_type=null。R2 提议原 Owner 追加独立目录/决定，不把现有行业/profile记录重解释成内容类型批准。

目录候选含 news/persona/story/conversion/other/unknown，引用 catalog_id/version/SHA，成员可按后续批准版本扩展。unknown 仅是投稿/待判断，正式值 null；other 需非空人审说明，不能自动生成 Style。目标类型与 Native Production Profile/Pattern/Compatibility 是不同 Authority。

首期正式类型确认 **在原 Case Approval 完成之后**：绑定 case_id、原生 attempt_id、approved Case SHA、原 Approval Receipt、目录 SHA、真实 Reviewer grant、准确父类型决定和操作身份。这样不把候选 SHA 的决定自动带过原生批准时的字节变化。批准前 Excel 类型仍是建议；若以后要求批准前同步正式类型，先独立审查准确 Source Transition 合同，不靠“同一个case_id”承接。

对于普通既有 Native Case，import origin 可为 null；对带 Excel primary-origin 的新 Task，必须准确绑定其 association，不能借 null 绕过。旧 Case JSON、Approval、行业/profile确认及原 Row 均不改写。

在原 Case 锁+原 reviewer 锁下，确认当前授权与来源后 write-once `data/case_governance/cases/<case_id>/content_type/operations/<operation_id>/decision.json`。先验证同操作原记录，再比较当前 parent；同意图可读原结果但不重写。新操作 parent 过期返回409；操作ID改输入也409。唯一有效头由可验证 parent链决定，不按文件名/mtime猜测。confirm_type、defer_type、revoke_type 都追加事件；defer/revoke 正式投影为 null。撤回类型需要当前合法 grant 和准确原决定，不因源内容已失效而阻止安全撤回。

profile/建议冲突：允许有理由地保留独立维度、有理由地更正正式类型或推迟；不自动更改 profile 或投稿原文。该处置和批准后首次确认、unknown/null 及 typed 失效规则均列为 P-R2-01～05 的待批产品建议。

Reviewer grant 使用原真实 `{namespace,user_id,capability,event_id,event_sha256}`，不是虚构的文件 SourceRef。新预览、写入和 ME-R1 读取必须当前有效；已提交历史决定用原 `validate_authorization_evidence` 核验当时 grant，后续 revoke 不抹掉历史合法性。重新 grant 后旧预览不再能授权新写入。显式类型撤回/来源变化、目录当前版本变化才按对应有效性规则让新操作重验；不修改原 grant 历史。

## CC-02 typed 发布

采用新的候选 `case-shared-display-v1.2-proposal` strict reader，不能让旧 v1.0/v1.1 接受任意新字段。继续由原 Shared Owner 管理同一条 sequence/parent 历史；v1.2 publish/withdraw 也写原 receipt_<sequence>.json，允许版本化混合历史，所有旧字节保持。每个新操作另有原 Human operation 的稳定意图和完成结果；receipt绑定operation，响应丢失能定位原序号，不按“最新一个”冒认。

typed preview 由服务端聚合当前批准 Case/Receipt、有效当前类型决定/目录、原 display policy、隐私/Proof/来源/封面展示权、actor/grant、当前 publication parent，返回准确 preview digest。客户端不填造 display/approved 字段。publish 必须明确 `publish_exact_preview`；在原 Case→reviewer 锁下重新核验所有来源并原子 write-once 新 receipt。审批流程不得因 Excel 建议或一次“保存”自动开始共享。

新类型改变或撤回时，旧 typed receipt 继续留存，当前 typed 投影因绑定不是当前有效决定而停止公开，等待新的准确 preview 与明确共享确认；不把旧receipt内容改成新类型。原 v1.0/v1.1 null 投影按旧 Reader 继续，不能因新增目录就自动补类型或改历史。目录版本变化/Case SHA变化/旧决定失效同样阻断新 typed 发布，原 Publication Authority 决定是否当前可见；P-R2-03 明确请求接受上述保守 typed 失效规则。

withdraw 与 publish 分开输入：当前合法撤回 grant、Case identity、准确原 publication/parent、operation ID、理由、显式撤回即可。不要求重新取得有效类型、媒体许可、Case Approval 或发布 preview；这些失效时更应允许安全撤回。仍验证原历史完整性与当前 parent，不能覆盖更晚发布。已写receipt但响应/结果文件丢失，只补同一操作结果，不新增sequence。损坏历史先阻断并恢复准确原记录，不凭空发一个撤回收据修补链。

## 必须证明的消费者范围

Case Classification Reader/Writer、原 Case Access/Reviewer、review command 的 exact Human intent、Shared history/preview/publish/withdraw、列表/详情/封面 projection 和权限反馈一起审查。类型来源与 display projection 在 UI 明确；正式类型筛选不得使用 Excel hint。普通投稿者不能因存在候选就获得 Reviewer 权限。

不改变原 Evidence Review、Case Quality、Approval receipt、Pattern/Fingerprint/Compatibility/Release、媒体生产复用权或 Customer Truth。未取得正式类型时，原 null 安全语义保持。

## 精确机器记录补充

CONTRACT_CANDIDATES_R2.json 中 TypedPublication 是 Human publish binding companion；真正追加进 receipt_<sequence>.json 的新版本严格使用 TypedHistoryReceipt（case-shared-display-receipt-v1.2-proposal）。其 sequence、parent_sha256、actor、Case/Approval SHA、operation ID 和 Human decision ref 共同绑定原历史；publish 的 sources 指向由原 Shared Owner 保存且复验的不可变展示/clearance snapshot，不能由客户端指定任意来源。withdraw 记录继承原 Case/Approval 历史 SHA，display={}、allowed_fields=[]、sources=null、cover_clearance=null，不能被错误送入 publish 资格校验。

TypedPreview 使用原 _policy 产生的 version/validator_sha256 对象，不伪造 policy 文件 ref。公开 display 继续保留原五字段，video_type 为准确目录的显示标签，projection 另有 video_type_id；other 的人审备注不自动公开。正式类型筛选使用正式目录身份/标签，仍不使用 Excel hint。

客户端只提交 TypeDecisionInput / TypedPublishInput / TypedWithdrawInput，actor、grant、sources 和最终 receipt 全由原 Owner 组装；schema 禁止客户端冒充这些 server record。撤回类型读取准确历史决定，不要求源媒体仍可发布；新写操作仍需当前合法授权。

审核说明输出严格限定为 BoundNotesProjection.notes 的 V0.3 字段白名单；来源文件路径、provider_reference、supporting_document_ref 和无关行不返回。纯人工秒数等转换为未核展示字符串，空单元为 null，不修改原行。新版共享预览的 source_clearance_snapshot 是原 Shared Owner 保存的不可变派生预览记录，准确字节 SHA 同时绑定 preview 与 receipt；不新增来源或许可 Authority。
