# CASE_EXCEL_IMPORT_1 V0.3 当前事实与合同审计

状态：`CASE_EXCEL_IMPORT_1_B0_CURRENT_TRUTH_AND_CONTRACT_AUDIT`。提交架构审查，不授权实现或业务写入。

## 身份及保护

代码 HEAD `4287234e5aa7f711751d7ec06dd0935ad6acbab2`。原验收工作区 `E:/projects/ai-video-ops`，分支 `codex/checkpoint-creation-batch-ux1-uat-20261024`；新审计工作树 `E:/projects/ai-video-ops/.worktrees/cxi`，分支 `codex/case-excel-import-1-v03-b0`，从同一 Checkpoint 创建。首次较长路径 checkout 遇到 Windows 路径长度限制，改用项目内短目录及单命令 core.longpaths 后成功；未使用旧 Case 工作树或改动原代码。

原 Frozen Batch Baseline SHA `13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3`、Plan R5 SHA `f1ebd4283dc0e341aca7675c245e2c515cbab1e314af8843eee3e426831e07bb` 保持。Founder 已反馈原四条创作、发布和 Excel 查看跑通；按阶段20条 UAT仍因实际新主题不足阻断，不宣称全面验收。性能优化继续暂停，Case导入不进入创作 Batch、Mix、News、Publish Copy 的实施范围。

## 模板是已冻结产品输入，尚非已批准机器合同

`FOUNDER_ACCEPTED`：`CASE_EXCEL_IMPORT_V0_3_FOUNDER_TEMPLATE_FROZEN`，由本轮 Founder 指令确认。实际附件路径/字节与预期 SHA 均核对一致，虽然文件名不同。Excel 40,367字节；CRC通过；8张工作表，正式字段21/10/9；`使用说明!B3`身份准确；案例清单H/I/J准确。正式数据区实际0行，不能把六个DEMO示例当作真实候选。详见 TEMPLATE_V03_VERIFICATION.json。

JSON中`design_candidate_pending_current_native_case_contract_review`描述机器合同候选状态，不能改成Native已批准，也不否定Founder已冻结产品模板。两种状态并存。原附件和本包inputs是同字节快照，不编辑或重存XLSX，不使用V0.1/V0.2字段序。

## 关键 Current Truth

| 结论 | 分类与证据 | 对本专项的影响 |
|---|---|---|
| 原Case Intake处理已校验抖音链接，同一组最多10个有效视频；client_request_id、输入digest和用户绑定 | CODE_PROVEN S01/S02 | external_case_key只能关联Excel行，不可成为Case ID；模板101个预留填写行不是101条已支持容量 |
| 保存现有Intake组会进入dispatch_groups原Task admission | CODE_PROVEN S03 | Excel上传、预检及保存Candidate不得直接调用该自动派发路径，避免自动触发模型 |
| 现有Native Case需真实来源视频和ASR/视觉/Shot/隐私/Storyboard证据 | CODE_PROVEN S09–S18 | 手工结构、纯文字不能伪装成有效原生Case候选，更不能Approved |
| 本地视频上传也绑定抖音Canonical URL、平台视频ID、当前用户及真实上传回执 | CODE_PROVEN S05–S09 | V0.3要求接纳“只有文件无URL”的待核候选；当前尚无该导入保存入口，也不能进入正式原生解析/批准，需SI-01/IB-01审查 |
| 原分类只确认industry/profile，且是operator_labels_only；投稿者私有访问权不等于Reviewer批准权 | CODE_PROVEN S19/S20/S33及HTTP路由 | `video_content_type_hint`没有正式业务类型人审Owner消费者；必须CC-01，不可复用profile字段冒充 |
| Shared Display明确video_type=None、sources.video_type.kind=no_formal_taxonomy | CODE_PROVEN S21–S23 | 当前即使Excel写“故事型”也不能作为正式共享类型。CC-02需原Shared Owner批准新版本 |
| 原人工作业只修订已有音频片段与合法帧切点，不能接受任意手填秒数/ASR/Proof | CODE_PROVEN S12–S16 | ME-01先保存未核手工说明；若要作为正式证据，必须独立源证据/原Owner Gate |
| Case Approval和Shared Display保持不同Owner及收据，联合UI一次确认仍产生两份独立结果 | CODE_PROVEN S17/S22；原Owner隔离测试证据另列 | 不创建Excel专用批准器，不把Import保存回执当Case批准 |
| 原视频ID和真实媒体SHA已有去重；不同用户不得借重复投稿取得私有资料 | CODE_PROVEN S02/S25/S26 | 原去重继续执行，Import只增加稳定Row/Intent关联，不以Excel编号绕过 |
| News Novel只有1个并非Case数不足 | RUNTIME_PROVEN NEWS_CAPACITY_PROBE.json，CODE_PROVEN S28–S31 | 见独立根因报告；不可把导入Case当作扩充客户真实新主题的修复 |

完整字段映射40条见 V03_FIELD_AND_TYPE_MAPPING.json；准确函数、当前行号、源码SHA及版本见 SOURCE_OWNER_MAP.json，证据片段S01–S33。不存在的导入能力与新增合同均标记PROPOSED，而不是Current Truth。

源码身份分别记录审计文件SHA、原验收工作区文件SHA及HEAD blob SHA。部分既有文件经Git检出转换为CRLF，字节SHA不同；已逐项验证只差CRLF/LF、函数与行号一致。未通过重写源码来消除换行差异，也未把不同字节SHA冒称相同。

## 三种模式与当前边界

以下为FOUNDER_ACCEPTED的V0.3产品输入条件及PROPOSED的接缝边界；三种Import Candidate保存入口均未实施，不能当作现有可操作能力。五个基础必填键为external_case_key、source_platform、submission_mode、source_title、observation_basis。

A“链接/视频待解析”：五个基础必填键＋URL/真实媒体引用至少一项；topic/structure_summary可选，只保存待解析Candidate。合法抖音URL可在后续明确授权解析时复用原Task入口；独立文件/其他平台保留待来源核对，当前不调Native。

B“已整理结构待核验”：五基础键＋topic＋structure_summary＋URL/真实媒体引用；分段只作为ME-01未核说明。完成原生媒体解析和Reviewer核对前，不产生ASR/Frame/Shot/Proof通过标记。

C“仅文字待补证”：五基础键＋topic＋structure_summary，URL/媒体可空、平台可未知；停在私有待补证Candidate，无Case Approval/Shared资格。三模式都可填业务类型建议，证据级别不改变。

## 缺口与审查停止点

必须独立审查IB-01导入意图/候选/行恢复、ME-01手工来源说明、CC-01正式业务类型及CC-02共享类型投影；SI-01明确独立本地文件/未知平台如何成为待核来源，不能放松现有Approved Case来源规则。见对应Delta与IMPLEMENTATION_GATES_AND_TEST_PLAN。字段上限、枚举别名、部分保存策略、解析授权和超链接关系处理都只给候选规则，不冒称产品模板已冻结了这些机器参数。

本轮仅文档、只读附件/源码/运行投影审计和原Owner隔离测试；不实现I1/I2/I3、导入Adapter、正式Schema、业务写入或新批准。真实模型、40条生产、4090、部署、AUTH/OIDC均未进行。对已有Native合同的测试不等于Excel导入已实现。
