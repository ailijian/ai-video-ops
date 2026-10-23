# NEWS_SOURCE_UX_1 — 新闻体来源配置优化

状态：Founder 在统一 UAT 期间明确批准的局部实现候选，等待 ChatGPT 独立审查及 Founder 体验核对。此记录不是 Native Approval、Stage Acceptance 或生产授权。唯一编辑入口仍在本 Delivery；原 Baseline R1、Plan R5、原审查 ZIP 与 Manifest 字节保持不变。

本次批准来源：本 chat 的“NEWS-SOURCE-UX-1｜新闻体创作配置精准优化”完整要求。新闻体仍是一个视频内容类型，“创作新内容”和“改编已有内容”只是其内部来源方式；不是两个 Creative Style。直接展开的三阶段选择卡片保留。

## 当前身份与边界

- 根 HEAD：`8ce3da2443d2b0e83edb5c67a8578a18a00805a3`。
- 分支：`codex/checkpoint-creation-batch-ux1-plan-r5-20261022`；在现有未提交 B1～B4 候选上作增量，没有切回旧 `ceac16d...`。
- Baseline R1 SHA：`13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3`。
- Plan R5 SHA：`f1ebd4283dc0e341aca7675c245e2c515cbab1e314af8843eee3e426831e07bb`。
- B1/C01～C03、B2/A03、B3/A04 及 Policy2 隔离范围沿用 chat 中既有明确授权；原提案中的 PENDING 是历史送审状态。实施授权不等于 B1～B4 已被真人或独立 Stage Acceptance 接受。
- 本轮只改配置 UI/状态更新、原 Console 预检失败信息及对应测试。Native News、Pattern、Compatibility、Release、Human、Publish、Export、Closure、Ledger 脚本和正式 Request Schema 不作修改。

## 实现与既有 Owner

| 接缝 | 本轮行为与唯一 Owner |
|---|---|
| 页面分组 | `creation-config-view.mjs` 将新闻体展示为一个分组，内部是两个独立数量步进器；删除额外复选框及禁用数量逻辑 |
| 数量与草稿 | `creation-config-model.mjs` 仍维护唯一配置状态；步进、直接输入和保存使用同一数量。保留既有 `repurposeEnabled` wire 字段，仅在用户明确编辑改编数量时按数量更新，不在读取时猜测或迁移 |
| 来源列表 | 复用 `POST /api/create/news/preview` → `news_delivery_gateway.preview_news_creation` → `news_delivery_v1.preview_news_delivery`。只显示当前 Business/Speaker 下正式 Reader 返回的已审核/交付标题与状态，不补造日期、原制作方式或批准版本字段 |
| 精确选择 | 客户端保留真实 `repurposeSourceIds`，不自造 Source/Receipt SHA；Native `native_batch_v1.preview` 重读资格、Memory 与准确来源，`news_delivery_v1.batch_source_snapshot` 生成逐项不可变来源引用 |
| 预检及确认 | 复用原 `/api/create/batches/preview` 与 `/confirm`，确认时重算当前完整预检 SHA；客户、人物、来源、批准或 Memory 变化仍阻断。Console 只将已拒绝预检的容量/不可用选项翻译为业务原因，不改变数量和资格 |
| Request 与统计 | Novel 与 Repurpose 各沿用原 Request 类型，RP 使用 `news-delivery-request-v1.2`，一 Request 一视频。原 Batch Slot、Native Generation、原 Human、Publish 和 Delivery/Closure/Ledger 不变；RP 的新增语义为 0 |

现有合同已支持多个明确的不同历史来源，因此本轮无需 Native Contract Delta。已交付并不自动等于可改编：现有价格型 News 至少需要四个合格信息单元，Reader 拒绝不满足的历史内容；没有扩大其适用范围。

## 用户可见规则与兼容

- 阶段一/二默认 Novel10、RP0，阶段三每周期 Novel1、RP0；推荐数仍不授予资格。自由组合全0或准确恢复此前草稿。
- RP > 0 才显示来源选择。读取来源、改变数量/人物/来源都会使旧预检失效，并明确要求重新核对。
- 多选数量超过新目标时保留具体选择，显示差额并要求用户取消；不自动挑选保留项。RP 改为0则清除本次 source IDs 与隐藏兼容意图，0→1不会恢复旧选择。
- 旧合法草稿原样读取；旧开关与正数量冲突、或0数量残留来源时显示歧义提示，必须用户明确重新确认。旧 Batch、Request、Slot、Receipt、Ledger 不被归一化覆盖。未知字段/版本及重复 source IDs 的严格拒绝策略保留。
- 页面区分新闻体总数、两种来源数量、计划交付总量、新增语义目标和改编呈现目标；实际完成仍由原生证据决定。

## 验证、证据与限制

准确的命令、版本、状态、前后源码/完整增量、Native 参数和来源 SHA、已执行浏览器交互及校验文件，由本机[本轮证据结果](../../../.local/evidence/news-source-ux1-20261023/FINAL_RESULT.md)和[证据 Manifest](../../../.local/evidence/news-source-ux1-20261023/MANIFEST.json)记录，不从本文的实现描述推断测试通过。

本轮覆盖阶段默认、Novel2/RP0、Novel0/RP2、Novel2/RP1、3→2→0→1、合法来源不足、旧草稿、未知字段、重复来源、退出/重登、准确 Source SHA 变化及重放。浏览器实际操作覆盖1440/390/320 CSS像素，不是三种真机。隔离样例从原 Native 审核、发布确认及交付创建；只在外部模型返回边界使用虚构合成内容，不手写批准标记或放宽 Gate。

本专项消费原 B1～B4 证据并按本轮 Console/配置影响范围补验，不声称重新完成 B4 最终组合关闭。前一候选的1661项全仓 PASS 保留原身份；不能直接称为本轮改动后的全仓 PASS。B4最终关闭仍受最终组合回归、独立审查、真人 UAT 等原 Gate 约束。

没有自动 Commit、Push、Merge、4090部署、真实内容模型调用或生产 Authority 写入；真实模型质量、费用、限流和生产资格仍未验证。旧 `.local` 审查包、全部既有工作区和历史材料保留。
