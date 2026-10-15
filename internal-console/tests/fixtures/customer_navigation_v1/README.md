# NAV-1 离线创作参考夹具

这些 JSON 表示完全虚构、预先存在的已审核参考库，用于隔离应用验证。不是运行时 fallback，不代表真实 Case、Pattern 或生产权限。

只在 `browser_customer_speaker_intake_v1.py --navigation-fixture` 的全新测试根初始化时复制；不覆盖任何已有运行根。客户及出镜人仍通过正式登录、事实审核和独立 Persona Approval 建立。正式 Creation Entry、matcher、SHA、Compatibility、Constraint、Request 和消费 Gate 不做 mock。模型边界仅使用已有虚构 Golden 输出。

Case 无生产媒体使用权；此夹具只能证明脚本创作入口与导航，不能证明真实模型、媒体生产或生产发布。News 仍为 research_coverage_insufficient。

Aggregate Compatibility Owner 固定要求三条历史 Case ID 和指定 reviewer。测试 aggregate 显式标记 `fixture_only`，历史引用为不匹配的占位 SHA；这些条目不能授予本夹具独立的虚构 Case（7999999999999999902）任何兼容性。虚构 Case 仅通过自己的精确 SHA sidecar 进入匹配。删除该 sidecar 的隔离负向测试必须继续阻断可创作。fixture reviewer 不是本轮真实 Founder Approval 记录。
