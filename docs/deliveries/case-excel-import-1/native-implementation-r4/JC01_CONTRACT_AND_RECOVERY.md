# JC-01 executable contract and recovery

## J1 / J3: explicit classification

目录版本为 integer，业务视频类型与制作 Profile 独立。目录支持 news/persona/story/conversion/other；unknown 不可确认为正式类型，审核员可明确暂缓为 null。其它说明必须是非空人工说明，保持私有。无冲突、保留独立维度、纠正投稿建议、暂缓分别严格使用 `no_conflict`、`preserve_dimensions_with_reason`、`correct_suggestion_with_reason`、`defer`。纠正与维度冲突要求原因；原 Profile、Excel 建议及其 SHA 保留在独立来源快照。

## J2: operation identity

| 操作 | 准确身份 | 持久 Owner |
|---|---|---|
| Human Command | 原32位小写十六进制，v1.6扩展 | 原 Review Command |
| 联合 Type Decision | `type_` + 同一 Human ID；独立记录 | 原 Classification Owner |
| 联合 Publication | 原 Human ID，记录原 intent/ref；独立 Receipt | 原 Shared Publication Owner |
| 历史独立类型确认 | `type_` + 32位小写十六进制 | Classification |
| 独立类型撤回 | `type_withdraw_` + 32位小写十六进制 | Classification |
| 独立 typed 发布 | `pub_` + 32位小写十六进制 | Shared Publication |
| Shared 撤回 | 保留原v1.0人工权限与expected-parent CAS协议，无新操作ID要求 | Shared Publication |

原 Command v1.0～v1.5 与 Publication v1.0/v1.1 不迁移、不改字节。联合 typed Publication 为v1.2，历史独立 typed发布为v1.3。类型决定为v1.1；目录为v1.0且整数version=1。新旧历史读取遵从各自严格版本。

## J4: exact consent

原 share-preview 签发可信、绑定当前 Reviewer grant、Case candidate/Attempt、Evidence scope、Excel Row/source、目录和当前父版本的快照。前端不预测未来SHA。原 Case Approval 成功后，读取真实持久化 Case 与 Approval Receipt 的SHA，形成独立类型决定，再形成独立发布收据。公开字段不超出原签名范围，未许可封面为占位，不用Excel声明或未核标题代替媒体证据。

## J5: durable stages

原 Human operation 下保留 intent/binding/result。Case已批准但类型写入失败：Case保留，原操作显示type_pending；类型已完成但发布失败：publication_pending；发布已完成而result中断：result_pending。刷新、换Session和进程签名key后通过原持久intent恢复缺失步骤，原Case和已完成收据不重写。每种completion由 Draft2020-12和语义校验器同时验证真实receipt、操作、来源与版本链。缺失有效收据不允许完整成功。

当前Reviewer撤权阻断继续；撤权再授予不借用旧grant扩大确认。Case/来源/目录变化要求重新核对，既有合法Case与决定保留，不静默变更展示范围。类型撤回/变更或来源失效立即令旧typed投影不可见；读取不回退较早legacy版本。合法Shared撤回先核对当前历史和权限，不要求重新获得发布资格。

## Native media cleanup seam

真实上传薄切片暴露：原分析成功清理会在awaiting_review删除Human scope所需视频。修复位于原 Upload/Retention Owner：仅读取已存在的精确 EX-S1 reservation、Intent/association/principal/Task/source/receipt SHA；等待审核时保留该原视频。损坏reservation使清理失败关闭，不能成为删除依据。旧非Native attempt保持原策略，未增加媒体使用权或另一套保留Authority。终态清理继续由既有Owner处理，本轮不承诺新的生产保留期限。
