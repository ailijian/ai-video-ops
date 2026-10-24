# Native 接缝与 I3：精确独立审查 R2

状态：`CASE_EXCEL_NATIVE_I3_R2_READY_FOR_INDEPENDENT_REVIEW`，不是批准、功能实现或完整流程验收。

请从 [准确审批请求](DECISION_REQUEST.md) 开始，再读 [范围 JSON](EXACT_APPROVAL_SCOPE.json)、[产品待决](PRODUCT_DECISIONS.json)、[原生提交协议](NATIVE_SUBMISSION_PROTOCOL.md)、[I3 类型/共享协议](I3_TYPE_AND_PUBLICATION_PROTOCOL.md) 和 [准入/恢复测试矩阵](RECOVERY_AND_TEST_MATRIX.json)。审批须绑定 `APPROVAL_SCOPE_BINDING.json` 的实际 SHA，明确 EX-S1 / ME-R1 / CC-01 / CC-02 及 P-R2-01～05；可分别批准、附条件或退回。材料本身没有签署位，不代签任何人。

当前已授权 I1/I2、EX-R1 保持：预检、私有保存、刷新查回、本人列表与原文读取。旧 R2 的 dispatch/model/approval/shared false 语义不变。本轮只修复 EX-R1 空 `row=` 错误退回整批的前端身份检查。正式 Native 提交、跨用户审核原文、正式类型确认与 typed 共享尚未实现。

R2 补齐 R1 的具体缺口：原子准入、worker 崩溃/unknown 持有、当前媒体清理、重复来源的最小关联、真实 grant 证据形状、批准后稳定类型身份、旧共享版本及安全撤回。R1 文件与旧审查 ZIP 均保留；R2 只替代尚未获批的候选设计，不迁移当前 Canonical。

本轮验证与最新基线限制见 [证据与版本](VERIFICATION_AND_SCOPE.md)。独立审查包在项目 `.local/evidence/case-native-i3-exact-review-r2-20261024/`，包含精确源码摘录、候选 Schema/SQL、原始聚焦 JUnit/JS、上一轮完整 Console 收据引用、Manifest/SHA/CRC。没有数据库、真实媒体、凭据或真实客户原文。
