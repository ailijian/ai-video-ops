# CASE_EXCEL_IMPORT_1 V0.3 B0 架构审查入口

状态：CASE_EXCEL_IMPORT_1_V03_B0_READY_FOR_ARCH_REVIEW。V0.3产品模板已由Founder冻结；导入Adapter与候选机器合同未批准、未实施。本目录是唯一可编辑审计入口，inputs保留原附件同字节快照。

1. [当前事实](CASE_EXCEL_IMPORT_V03_CURRENT_TRUTH.md)
2. [40项字段/类型映射](V03_FIELD_AND_TYPE_MAPPING.json)
3. [Case正式类型及共享Delta](CASE_CLASSIFICATION_CONTRACT_DELTA.md)
4. [未核手工说明Delta](MANUAL_EVIDENCE_CONTRACT_DELTA.md)
5. [Import Batch/Row/Intent及来源Delta](IMPORT_BATCH_CONTRACT_DELTA.md)
6. [News只有1个新主题的根因](NEWS_NOVEL_CAPACITY_ROOT_CAUSE.md)
7. [实施Gate与隔离测试设计](IMPLEMENTATION_GATES_AND_TEST_PLAN.md)、[16条虚构输入及变体](ISOLATED_TEST_INPUTS.json)
8. [原Owner/函数/行号/SHA](SOURCE_OWNER_MAP.json)
9. [附件身份、CRC、字段核验](TEMPLATE_V03_VERIFICATION.json)
10. [原Owner实际测试](evidence/EXISTING_OWNER_TEST_RESULTS.json)、[运行/工作树保护](evidence/PROTECTION_RESULT.json)

MANIFEST.json和SHA256SUMS.txt校验包内全部文件（不自引用Manifest），外层ZIP CRC及SHA另见ARCHIVE_VERIFICATION.json。审查包是本目录快照，不能编辑原附件、旧Batch Baseline/Plan、老收据或历史SHA。源码片段S01–S33对应精确Checkpoint，未包含数据库、客户原始材料、真实视频或凭据。

完成本轮审计后停止，等待独立架构审查与后续指令；无Commit、Push、Merge、4090、真实模型、业务写入或AUTH/OIDC。
