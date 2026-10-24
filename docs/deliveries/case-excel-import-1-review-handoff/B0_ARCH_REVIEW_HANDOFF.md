# CASE_EXCEL_IMPORT_1 V0.3 B0 审查交接

当前状态：`CASE_EXCEL_IMPORT_1_V03_B0_ARCH_REVIEW_PENDING`。Founder只冻结产品模板；A1/A2/A3均待原Owner合同审查，不签发批准。本次沿用原40项映射、33处源码与16条虚构测试向量，不重新审计或实施I1～I3。

原ZIP SHA-256：`797a326a5792ec01ce5f52299ac4476bc2e3cb7a4925d37132a5ea623e8a9ee8`，55文件CRC及原Manifest逐项复核通过。旧ZIP/Manifest/证据/工作文件原字节不变；原READY状态是提交时身份，当前PENDING是新交接状态，两者不互改。

Excel/JSON V0.3 SHA分别为`d720aa257d90955a0c8209756b1d6d8da49a789d250e28cf716890ab21a8664f` / `95463b7faf241bd090afda70bdc34a09584b386645bb0a1981673a5c1fbe1e08`。B0包包含模板身份、正式/排除表、人工说明等级、类型建议与正式分类的区别、Source/Media/Proof、Case Approval/Shared两个独立Receipt、Import Row幂等与停止条件。

| 待审范围 | 复用的准确最小Delta | 原Owner与需裁决内容 | 保留边界 |
|---|---|---|---|
| A1 Import Candidate | IB-01＋SI-01，[原文](../case-excel-import-1/IMPORT_BATCH_CONTRACT_DELTA.md) | 原Intake/Source/Task/Access：私有Batch/Row/Intent、cell及输入SHA、跨表分段/许可/重复视频关联、真实upload manifest与按行恢复；保存和解析授权分离 | 不新增Case批准器；无URL本地文件/其它平台只能待核来源，现Native不支持时停止，不伪造平台ID |
| A2 Manual Evidence | ME-01，[原文](../case-excel-import-1/MANUAL_EVIDENCE_CONTRACT_DELTA.md) | 原Evidence Review/Source/Privacy：手工观察作为未核说明，保留observed/未观看来源，后续仅绑定真实已有媒体证据ID核对 | 不能自动成为ASR/OCR/Frame/Shot/Proof；秒数不是机器切点，缺证只补证 |
| A3 Video Content Type | CC-01＋CC-02，[原文](../case-excel-import-1/CASE_CLASSIFICATION_CONTRACT_DELTA.md) | 原Classification/指定Reviewer/Shared：可扩展词典及版本化确认，六种建议、other说明和profile冲突；共享投影另绑正式确认与Case批准 | 原普通operator-label权限不升级；正式类型仅展示身份，不授予Mix/News生产、Pattern或Compatibility |

| 原合同文件 | SHA-256 |
|---|---|
| IMPORT_BATCH_CONTRACT_DELTA.md | `d56a81a2a9cf45ab70819f94884d908939bf7f262e6f24d3b74ae6e04821471d` |
| MANUAL_EVIDENCE_CONTRACT_DELTA.md | `ca000e79ead8ae4c61e0c788a33e69753f61440dd07709f60828566cb2dbd251` |
| CASE_CLASSIFICATION_CONTRACT_DELTA.md | `5d39b91abc85dee4c52eb0aed663a16bb5e13732c938e1586f7f9765a983a94c` |

后续审查顺序可先只审A1只读解析/预览范围；Candidate持久保存须A1/A2及来源接缝明确；正式类型/共享须A3及原生证据与当前Reviewer grant。各步仍须精确实施授权，本轮不产生Native Approval或代理签名。

与CREATIVE_CAPACITY_2的唯一接缝：合法Case候选→原Case证据/批准→Fingerprint/结构研究→原Pattern批准→独立Compatibility→Release/资格。导入和正式展示分类都不直接增加客户事实或Novel配额。容量研究不代批A1/A2/A3。

本目录只承载新交接记录。原B0事实/Delta唯一来源仍是旁边case-excel-import-1和原ZIP。[机器可读交接](B0_ARCH_REVIEW_HANDOFF.json)列准确来源、SHA、Owner与停止条件。
