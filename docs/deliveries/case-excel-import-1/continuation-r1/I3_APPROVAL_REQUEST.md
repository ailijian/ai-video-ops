# I3 独立审批请求：CC-01 / CC-02

状态：`EXACT_SCOPE_PROPOSED / NOT_IMPLEMENTED / NOT_APPROVED`。

原 B0 补充裁决只认可版本化方向；本轮不把方向认可、Excel 投稿建议或普通候选保存转换成正式分类/共享授权。原 `CASE_CLASSIFICATION_CONTRACT_DELTA.md` 保持历史字节。

## CC-01：原 Classification Owner

候选版本：`case-content-type-catalog-v1.0-proposal`、`case-content-type-review-v1.0-proposal`。

- 目录初始包含 news/persona/story/conversion/other/unknown 的投稿与展示语义，正式消费者引用目录 ID/版本/SHA；不能永远写死四类，也不授予 Creative Style/Pattern/Compatibility。
- 人审决定精确绑定 Case ID、Attempt ID、候选或批准 Case 的实际 SHA、Import Row/SHA、当前目录、当前 reviewer grant、操作身份及 parent SHA。普通投稿者只能保留建议。
- 业务类型与制作 profile 是两个维度。冲突必须显式处置与给出理由，不能由 AI 或导入程序自动改成 Mix/News。
- `correct_suggestion_with_reason` 仅表示追加正式分类决定及理由；原 Excel 建议与原 Row 字节永久保留，不能解释为修改投稿原文。
- 提议处置为 `confirm_type` 或 `defer_type`；确认 other 必填说明。unknown/缺少决定继续保留正式 `video_type=null`。是否允许 unknown 形成已确认展示标签为产品待决，不自行冻结。
- 若修改或撤回分类，写新决定；旧 Case Approval、类型决定及共享 Receipt 不覆盖。失效条件包含 source/Attempt/目录/grant 变化。

## CC-02：原 Shared Display / Human Decision Owner

候选新增 typed shared projection/receipt 版本，不能给原 v1.0/v1.1 收据补字段。保持两个独立 Authority：Case Approval 与 Shared Publication；类型决定只授权类型展示。

新共享预览/决定绑定：真实 Case Approval 与 SHA、有效 CC-01 决定及目录 SHA、当前 source/privacy/proof/cover 权利、actor/grant、publication parent SHA 与显式 display decision。旧 `video_type=null` 兼容语义继续可读。

批准后修改类型不自动改变已公开页面。必须重新核对来源/权限并明确发布新版本；撤回使当前投影按原 Owner 规则失效，历史 Receipt 保留。Excel 展示标题/摘要建议不直接成为共享文案，必须通过原 source-backed display policy。

发布与撤回使用独立候选：发布要求当前有效的来源、类型、预览与独立 Human Display 确认；`case-shared-display-withdrawal-v1.2-proposal` 仅绑定当前合法撤回权限、准确原 publication/parent、操作身份、理由及明确撤回确认。不能因来源/类型已失效而阻止安全撤回，不要求重新取得媒体许可或重新生成发布预览。旧撤回路径与历史收据保留，同意图重放不新写收据，过期 parent 不覆盖更新的发布。

## 需独立裁决的精确项目

| 项目 | 原 Owner / 决定责任 | 本轮状态 |
|---|---|---|
| EX-S1 origin → Native Task 的准入身份、原子恢复和锁序 | Case Intake / Task / Source | 待批准，不实施 |
| ME-R1 特定已提交行向合法 Reviewer 的最小读取授权 | Case Access / Evidence Review | 待批准，不实施跨用户读取 |
| CC-01 目录、人审字段、profile 冲突处置与 unknown 语义 | Classification / 原 Reviewer 授权 Owner / Founder 产品决定 | 待批准 |
| CC-02 typed preview/publication 版本与失效规则 | Shared Display / 原 Human Decision Owner | 待批准 |

本轮唯一继续实现的是 EX-R1 本人列表/原文只读整合，不能因该部分通过便开启本表后续写入。最终完整链路验收还需获批的原生提交、真实证据/人审、独立共享及对应失败恢复。真实付费模型、生产和部署仍不在授权内。

## 审批检查表

- [ ] 明确 EX-S1 Task 与 Canonical companion 的单次准入/恢复证明，而非事后来源猜测。
- [ ] 保持旧 R2 Schema、Intent/Result 语义与历史 SHA；保存不自动派发。
- [ ] 同源跨用户结果不暴露私有 Case、Task、媒体或原文。
- [ ] 人工说明不升级为媒体证据、Business Truth、Proof 或复用权。
- [ ] 投稿建议与正式类型分离；Reviewer grant 实时验证。
- [ ] 明确 profile 冲突与 unknown/other 的产品处置。
- [ ] 旧共享 v1.0/v1.1 严格读取、null 语义与两份独立 Authority 保留。
- [ ] 来源/版本/权限变化失效、响应丢失、late worker、重放与取消验证范围明确。
- [ ] 仅在精确范围获批后实施；最后统一 Founder 验收，不代签。
