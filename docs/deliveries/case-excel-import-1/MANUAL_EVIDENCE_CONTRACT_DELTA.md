# 未核手工说明与原生证据接缝

状态：ME-01 / PROPOSED / NOT_NATIVE_APPROVED / NOT_IMPLEMENTED。

## 已有能力与限制

S11要求真实音频/视觉/Shot/隐私/Storyboard；S12要求原视频和全部源证据SHA；S13只接受原ASR segment及合法Frame ID，不能提交任意手填秒数；S16/S17保留独立Human Quality、Evidence Review和Case Approval。现有人工修订不是一个可把Excel文字转成机器证据的入口。

## 最小建议

由原Case Intake保留一个未经核实的手工说明companion，`case-import-manual-notes-v1.0`为候选版本。包含Import Batch/Row、external_case_key、原始XLSX/规则SHA、各sheet/cell定位、原始值及规范化值、observation_basis、topic/hook/summary/excerpt/visual/reference/risk、ordered segments、rights_claims、actor、时间和前版SHA。evidence_level始终submitter_claim/unverified；不得出现自动pass、approved、granted或生产权利。

分段序号是Excel内ordinal，不是Shot/Beat ID；人工秒数是hint。只有后续真实上传/获取后，Native Media检查出的duration可作为上界；单凭duration_seconds_hint不能证明分段时间合法。无真实时长时标记timing_unverified，不制造校验通过。

原生解析完成后，Reviewer可在私有界面对照这些说明与真实原声、Frame、OCR、Shot及风险。若需要结构化关联，提案只允许显式绑定现有segment/frame/shot IDs和SHA、核对人/范围/结果；不复制摘录到audio_v1、visual_v1或verified_proofs，也不篡改自动提取的原始证据。可复用原review-revisions纠错条件，条件不满足则补证/原生重析/不收录。任何更高效人工替代机器证据方案必须另交原Evidence/Source Owner批准，本提案不含此放宽。

rights字段都是投稿声明；未提供许可行时unknown；“声称允许”不提升为共享/封面或素材复用权。凭证编号只保留引用，真实凭证经独立安全上传并由原Owner核验。隐私自述“未发现”不等于privacy_gate_passed。

display_title_hint/display_structure_hint默认只能作私有建议：当前S21仅允许来源标题摘录及Native安全结构摘要。若要采用新的人工摘要，必须原Shared Owner扩展source-backed display policy并重新签发预览；不能直接把Excel原文发布出去。

只读显示手工说明与正式证据分区；文字-only可长期停留待补证，不创造Case/Attempt虚构身份。后续补证要新候选版本及显式来源关联，保留原XLSX和已核/未核字段边界。旧Candidate/Approved Case/Review/共享收据不迁移覆盖。

Gate：原Case Intake＋Evidence Review＋Privacy＋Shared Display分别审查适用接缝；只有保存未经核说明的范围先获批后才做I2。B0只提出合同，不编写消费者、不代签证据。
