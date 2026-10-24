# CREATION_BATCH_UX_1 — Gap Register

> 本文件是 [唯一可编辑 Baseline](BASELINE.md) 的配套交付文档。原 BL-0 审计结论、目标、状态和证据范围保持不变；文中的审查包、自检、MANIFEST及运行结果指原历史快照，见 [交付入口](README.md)。

Status: Draft — Planning Ready: No

仅列问题、来源、严重程度、影响和最小必要的事实/产品澄清；不是实施 Plan。
P0 = 会实质影响后续方案或信任边界；P1 = 核心目标缺口/适用范围；P2 = 限定体验/产品细节。
“规划关键”说明为什么不能把某项能力当成已经成立，不要求在BL-0开发该能力。

| ID | 严重度 | 证据性质 | 问题 | 来源 | 影响 | 规划关键/最小澄清 |
|---|---|---|---|---|---|---|
| G01 | P1 | CODE_PROVEN | 两个创作模式与 operating_stage 未出现在当前创建合同/UI | CT01/CT27 | 无法按阶段或自由组合配置一批 | 否 |
| G02 | P0 | UNKNOWN | 人设型/故事型/高转化型缺少正式类型规则与 approved Pattern/Compatibility 映射 | CT08/CT24 | 内部 angles 不能担保业务类型语义或资格；阻止冻结依赖它们的 Plan | 是：Founder/领域 owner 明确类型判据及可用原生资格证据 |
| G03 | P0 | UNKNOWN | 阶段一、二人设型和故事型的拆分未定 | FOUNDER_TARGET FT03/FT04 | 无法冻结默认拆分；不得默认为1:1 | 是：Founder 明确默认或明确由用户填写的产品规则 |
| G04 | P1 | UNKNOWN | 稳定期必须选择周期数，但初始值、范围和呈现未定 | FOUNDER_TARGET FT05 | 不能无期限生产，具体交互边界未冻结 | 否：保持产品未决 |
| G05 | P0 | UNKNOWN | 阶段/自由组合的“新闻体”是否允许 Repurpose 计入以及如何呈现新增/重新表达未定 | CT09/CT10/CT11；FOUNDER_TARGET FT02 | 可能把历史语义重复计成新内容，影响数量和Ledger语义 | 是：Founder 明确计数语义，保持 Native semantic delta |
| G06 | P1 | CODE_PROVEN | 无 multi-profile Batch ID、跨 Request 稳定 Slot ID、统一配置→多个 Request 的合同 | CT01/CT04/CT07/CT27 | 现有内容/Concept/Beat/Slot ID 仅本 Request 内；无整批精确关联 | 否 |
| G07 | P1 | CODE_PROVEN | 当前同客户同 profile 仅一个 active generation Request；News 每 Request 一个视频 | CT04/CT09 | 不能从现有入口直接一次排10条 News；重复点击可能复用 active Request | 否 |
| G08 | P0 | UNKNOWN | 20/40 条混合整批端到端、并发、恢复及质量未验证 | CT01/CT18；TEST_EVIDENCE | 1–20 admission 范围和 queue_max20 都不证明20条整批成功；40超单Request范围 | 是：在承诺容量/并发方案前取得隔离验证或明确待验证义务；不能宣称已支持 |
| G09 | P1 | CODE_PROVEN | 无整批 cancel/pause/resume/retry 和跨批次聚合状态 | CT15/CT16/CT18/CT27 | 已有 Request 处置及单任务 recovery 不能投影成批次全部完成/部分失败 | 否 |
| G10 | P1 | CODE_PROVEN | 现有去重/memory 不是新 Batch 内多个 Request 的语义预留合同 | CT30/CT04 | 拆成多个Request不能自动推导预留或不互相冲突的能力 | 否 |
| G11 | P1 | CODE_PROVEN | 有 Request 内 item/Beat/Slot Human Review，无跨原生 Request 的集中审核合同 | CT12/CT10/CT11 | 不能新增第二套批准真相；目标集中确认尚未实现 | 否 |
| G12 | P1 | CODE_PROVEN | 无多 Request 按业务 subtype 汇总导出合同；现有 supplemental delivery 绑定一个Request | CT21/CT22 | 不能将新批次导出误写成已支持；两种模板可复用 | 否 |
| G13 | P0 | BLOCKED | News v1.2 当前仅隔离 price_offer_led/已资格来源；生产 installation 明确拒绝，默认 rollout off | CT09/CT24/CT29 | 不能规划为所有客户立即可用的生产新闻体 | 是：安全Plan须明确隔离范围；生产资格由原Authority owner另行解决，BL-0禁止部署 |
| G14 | P1 | BLOCKED | 存在 derived restriction contract 的客户被非Mix消费者明确阻断 | CT25 | 不能因阶段规则、旧UAT或UI资格绕过客户限制 | 否：保留现有 Gate，适用客户范围须清楚 |
| G15 | P1 | BLOCKED | 无真实原 Ledger snapshot 的变更 legacy Mix history 不可补造 anchor | CT23 | 旧交付附加导出可能需要人工历史证据核对；不得改旧Receipt/Ledger | 否 |
| G16 | P1 | UNKNOWN | 真实模型 subtype 可区分性、copy质量、成本/Token/耗时/API限额 UNKNOWN / NOT_VALIDATED | FOUNDER_ACCEPTANCE_PROJECTION；CT08/CT18 | 合成transport通过不能证明真实模型质量或预算 | 否：不得给出猜测数值 |
| G17 | P1 | UNKNOWN | 当前 checkpoint 手机端完整流程未浏览器复验；Founder目标原始手机截图未可核验 | CT27；Founder Visual Reference | 只能证明源码和前端行为回归，不能宣称视觉一致或移动端UAT通过 | 否 |
| G18 | P2 | UNKNOWN | 自由组合全部为0时的产品行为尚未明确 | FOUNDER_TARGET FT06 | 每种可为0不能推导空批次是否合法 | 否：产品边界待确认 |
| G19 | P1 | CODE_PROVEN | 视频类型扩展当前无正式用户可选 subtype registry；入口仍限定mix/news | CT01/CT08 | 不能把四类型硬编码为全部正式生成能力，也不能称插件化扩展已实现 | 否 |
| G20 | P1 | UNKNOWN | 现有 shared-customer Console 边界不能建立未来代理商多租户授权矩阵 | CT26 | 对象身份隔离已测试，不代表租户访问隔离；AUTH/OIDC在本轮禁区 | 否 |
| G21 | P2 | FOUNDER_ACCEPTED | 等待体验/性能仍开放 | FOUNDER_ACCEPTANCE_PROJECTION | 历史合成样例约10s生成/6s确认导出仅个案，不是SLA或吞吐承诺 | 否 |
| G22 | P1 | CODE_PROVEN | 脚本/Excel交付之外的生产素材摄取、视频生产、成片QA不在当前实现范围 | Operations Index Current boundaries；CT28 | 本轮“视频条数”不可声称为自动完成真实成片 | 否 |

共 **22** 项；主分类 **UNKNOWN 9**、**BLOCKED 3**；规划关键 **5** 项。这些是去重登记的问题条目数量，不是所有字段/所有风险的计数。

未发现最新 Checkpoint 缺失已验收 Mix/Novel/Repurpose/PUBLISH-COPY 关键实现的证据；因此没有“Checkpoint缺功能”的 Baseline Blocker。上表仍有类型语义、默认拆分、新闻计数、容量承诺和News生产范围的关键缺口，不能把审查包就绪写成安全正式Plan已就绪。
