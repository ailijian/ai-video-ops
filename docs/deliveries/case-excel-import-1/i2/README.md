# Excel I2 私有未核候选保存

状态：`I2_LIMITED_LOCAL_IMPLEMENTATION / LIMITED_FOUNDER_UAT_CONFIRMED`。

Founder 直接确认“批准该 I2 受限开发范围，最后统一验收”。[授权来源](SCOPE_AUTHORIZATION.json)仅记录工程范围，不是 Case Approval、Reviewer grant 或独立验收收据。准确 R2 SHA-256：`b483223d796fb7d2c233c436dfda100d2cdfe6a5ca6b7b21f33483824f4b58dd`；[原文件](../closeout-r1/I2_EXACT_WRITE_CONTRACT_R2_PROPOSAL.json)及其 Draft 字节保留。消费者保留其中 `v0.2-proposal` 的准确机器版本字符串，不表示正式 Case 已批准。

实现基底：`4287234e5aa7f711751d7ec06dd0935ad6acbab2`；原开发分支：`codex/case-excel-import-1-v03-b0`。Founder 已明确授权本地 checkpoint；本次检查点分支为 `codex/checkpoint-case-excel-i1-i2-founder-uat-20261024`，实际提交身份在项目 `.local/evidence/capacity-excel-checkpoint-20261024/` 的最终报告记录。V0.3模板、Creation Batch、C1/C2和旧审查包不改写。

## 当前功能

原 `/cases/excel-preview` 保留只读预检；选择文件后自动预检，同页核对问题、行选择及可选真实视频绑定，底部固定主按钮一次明确保存；成功后进入独立结果页。上传视频仍须明确确认权限与来源对应关系。只有最后的保存动作写私有未核候选，原 I1 `/api/case-excel/preview` 仍无业务写入。

三种提交方式均保留原21字段、分段、来源/许可原文及 SHA；人工说明保持未核。无视频或文件名未绑定仍为待补证，错误行不写候选。投稿类型只是建议，正式类型为 null。

用户可查看本人记录、刷新/重登后恢复已登记的中断保存、取消该操作未保存的行；旧行/Result/文件不删改。取消不封死将来的新意图。保存不写原链接分组，不调用 `dispatch_groups`，不触发模型、Task、Case Approval 或共享。

- [唯一Owner、身份、锁及恢复合同](I2_CONTRACT_AND_RECOVERY.md)。
- [实际验证与最后统一体验](VERIFICATION_AND_UAT.md)。原 I2 完整 Console 收据绑定其旧源码；当前 UI 增量的 125 项 Python、257 项 JS、浏览器恢复/取消/刷新证据分别位于 `.local/evidence/excel-import-flow-20261024/` 与 `excel-import-flow-followup-20261024/`，不跨版本借用全仓 PASS。
- 隔离入口：`http://127.0.0.1:18827/cases/excel-preview`。仅虚构数据、独立Cookie/库/Canonical；模型和其他网关关闭。登录仅留项目 `.verify/`，不入评审包。原18770、18825、18826保留。
- [原I1/B0](../i1/README.md)、[上轮完整Console与旧包](../closeout-r1/README.md)。旧965项结果不替代本轮回归。

I3分类/Typed Shared Display及新Novelty规则继续独立待批。本次只按 Founder 明确指令创建本地 checkpoint，不推送、合并、部署或调用真实付费模型。Founder 已确认三份预检结果及原两条投稿保存后的内容、未核状态和刷新查回；范围与准确答复见 `.local/evidence/capacity-excel-founder-closeout-20261024-151546/FOUNDER_UAT_RECORD.json`。该记录不代签 ChatGPT 独立评审，也不批准 I3 或生产。
