# Delivery Baseline — CREATION_BATCH_UX_1

> 唯一当前 Baseline：`docs/deliveries/creation-batch-ux-1/BASELINE.md`。本 chat 用户要求冻结，并明确采用 D-P01 类型定义、D-P02 方案A和 D-P03 Novel默认/Repurpose独立选择，现为 **Approved / Frozen，Baseline Revision 1**。批准范围是本页目标与保留约束，不是 Plan 冻结、功能验收、实施或生产授权。第1～9节保留原 BL-0 审计快照，其中“本轮”、Draft、未决和测试结论均按原审计时点理解；当前产品决定以本页 Key Decisions 和 Acceptance Criteria 为准。原 [BR-01](BASELINE_REVIEW_RECORD.md)、`.local` ZIP、Manifest、证据及历史 SHA 保持原样，关联见 [交付入口](README.md)。已批准目标后续只能经明确批准的 Amendment 修改。

Delivery: creation-batch-ux-1
Scope: iteration / BL-0 CREATE_BASELINE_ONLY
Status: Approved
Baseline Revision: 1
Planning Ready: No — 本 UI/UX Delivery 待 Design Readiness 及独立 Plan Review
Review state: Baseline Approved / Frozen；BR-01 Current Truth批准保留；Plan Freeze / Execution Not Authorized
Audit date: 2026-10-22（Asia/Shanghai）

## Goal

[FOUNDER_ACCEPTED / TARGET] 以已验收的原生News/Mix系统为依据，明确按阶段和自由组合的一批创作目标，并冻结可核验的当前事实，为后续经独立批准的正式Plan提供依据。

## User Outcome

[FOUNDER_ACCEPTED / TARGET] 代理商从客户进入独立配置，自动复用已有资料，选择阶段或自由配比，一次启动合法授权的整批任务，在保留原生Human Gates下查看进度、失败、恢复及集中确认，并按类型下载两种已验收新版Excel。**这是目标，不是当前实现声明。**

## Non-goals

- 本轮不创建Checkpoint，不写正式PLAN.md，不做B1～B4、不改功能代码、不创建新创作模式。
- 不Commit/Push/Merge/部署4090、不真实模型调用、不AUTH/OIDC；不修改客户数据、Authority、Receipt、Closure或Ledger。
- 不把本报告写成生产资格、真实模型质量、40并发或移动端全面UAT通过。

## Key Decisions

[FOUNDER_ACCEPTED / TARGET] 原目标输入见 [FOUNDER_TARGET.md](FOUNDER_TARGET.md)：两种方式、三阶段20/40/每周期8的推荐、各类型可0的自由组合、后续可扩展类型。News属原生News；人设/故事/高转化是Mix业务类型。该附录及原提案中的历史“未决”不覆盖以下已明确批准的产品规则。

### D-P01 — Mix三种业务类型：已批准的目标定义

三类均归 Native Mix，creative_style 与 production_profile、operating_stage、delivery_template 分开。批准的是下表业务语义、来源、事实/人物约束、禁止主张、目标结构和可区别判据；不表示当前已有三种正式生成策略，也不批准候选机器版本、失败代码或实现方案。

| 维度 | persona（人设型） | story（故事型） | conversion（高转化型） |
|---|---|---|---|
| 业务语义 | 适用真实出镜人的观点、判断、经营原则或本人经历，解释此人如何判断、为何这样做 | 一个有来源的真实事件或经历，按证据支持的情境、行为、结果或反思表达 | 已批准服务价值与用户需求、选择情境匹配，给出获准且有限的行动引导 |
| 允许来源 | Approved Business事实/价值观与准确Approved Speaker，限其获准第一人称和经历范围 | Approved事实中可定位事件、行动和结果；反馈须已获准作为本客户事实引用；Case研究只提供结构 | Approved服务内容、适用条件、价格、真实差异、需求场景和获准公开CTA；不挪用Case商业事实 |
| 必备事实/人物 | Speaker身份及当前Business版本绑定、具体观点/经历来源、第一人称权限；品牌不能冒称经营者本人 | 可引用的事件主体、至少一项可证行为及受支持结果；人物讲话/客户quote需对应授权；未知时间不编日期 | 至少一个可证价值与适用需求；价格附限定条件；人物背书需权限；CTA须有原生可验证规则 |
| 禁止主张 | 发明经历、职称、身份、关系或资历；把观点塞给无权Speaker；将观点升级为客观保证 | 虚构冲突、对话、因果、转折、前后效果、第三方关系或结果；把Case研究当亲历 | 虚假稀缺、优惠、绝对收益、效果保证、未批准比较/关系；隐去价格条件；未授权联系方式/行动 |
| 目标结构 | 已证情境→本人观点→可证判断依据/有限经历→边界 | 事件情境→可证行动顺序→已知结果/反思；缺失不得补造圆满结局 | 明确需求→已知服务/价值与条件→适用边界→合法且已批准CTA |
| 可区别验收 | 可指出具体Speaker观点及来源，正文为观点解释 | 可定位具体事件及行动/结果引用，不能仅给通用介绍加“有一次” | 可定位需求—价值—条件—CTA链，不能给其他类型随意追加购买号召 |

事实不足、Speaker scope不符、Pattern/Compatibility不支持或当前限制冲突时阻断，不更换标签凑数。产品定义批准不替代原Pattern、Compatibility、Release、事实、媒体权利及Human Review Gate。

### D-P02 — 阶段一/二合计推荐＋代理商明确分配：已批准方案A

阶段一推荐新闻10条、人设＋故事合计10条，总计20；阶段二推荐新闻10条、人设＋故事合计30条，总计40。显示合计推荐，人设/故事初始为“未分配”，由代理商明确填写；未填不等于0，未完成分配不能开始，不预设5:5或15:15。

各项数量可编辑、可为0。两项之和必须等于用户明确确认的本次实际合计。修改推荐后同时显示推荐总量与本次实际总量并确认，不强迫回到原推荐数。稳定期仍为每四天一个内容周期：新闻1、人设3、故事2、高转化2，合计8；周期数量须明确选择，不能无限期自动生产。

### D-P03 — News推荐默认Novel、Repurpose显式另选：已批准

阶段推荐的News数量默认指Novel：阶段一/二各10条，稳定期每周期1条。Repurpose作为不同创作来源显式独立列项，不自动抵扣或冒充Novel推荐量；来源不足不得后台改为Repurpose凑数。用户主动修改实际目标时，须明确确认其对新增语义目标和视频总数的影响。

确认与结果分别列出Novel、Repurpose、交付视频数量和新增语义数量；Presentation History保留独立身份。Novel按原Native新内容语义写入，Repurpose semantic delta为0；两者保留各自Request、Human Review、Semantic Ledger及Presentation History。视频内部4～8个Beat/Slot不等于多条视频，Publish Copy与再次派生导出不增加语义。

## Preserved Constraints

[FOUNDER_ACCEPTED / CODE_PROVEN] 现有Business、Speaker、Case、Pattern、Compatibility、Release、Review、Export、Closure、Ledger保留其唯一Owner；阶段预设不能授予资格，任务完成不能批准内容，AI/Case研究不能创造客户Truth、媒体权利或Proof。原批准lineage和历史Receipt不可改写；News novel与repurpose及semantic delta不能混用。证据 CT03、CT10～CT26。

## Acceptance Criteria

- AC-01：独立审查者可复核准确HEAD、Checkpoint branch/full SHA/parent/内容、相对冻结版本增量及全部工作树保护。
- AC-02：Current Truth、Founder目标、未知/阻断明确分开，每项关键当前结论可追到源码函数/行号/SHA和实际测试范围。
- AC-03：四层类型维度与Native Owner清楚；不得将Mix通用角度直接声明成三个正式业务类型已支持。
- AC-04：News Novel与Repurpose的来源、审核、导出、Ledger语义分别可查，原恢复与幂等边界保留。
- AC-05：20/40批量、真实成本/限流/时长和移动端验证不足均明确标记，不跨版本借用UAT。
- AC-06：本轮A～H工件与脱敏源码证据可独立检查，ZIP CRC、SHA-256及文件manifest可校验；没有实施Plan或功能变更。
- AC-07：[TARGET，尚未验收] 后续产品达到FT01～FT11的体验和保留约束；其正式Plan必须等待独立批准，不能由AC01～06的审计通过替代。
- AC-08：[TARGET，尚未验收] 三种Mix业务类型分别满足D-P01的语义、允许来源、事实/人物约束、禁止主张、结构和可区别判据；缺少事实或适用资格时阻断，通用Mix输出换标签不能作为支持证明。
- AC-09：[TARGET，尚未验收] 阶段一/二显示人设＋故事合计推荐10/30，初始未分配、代理商明确分配；不自动均分，未分配不可开始；修改后按显式确认的实际合计及总量校验。
- AC-10：[TARGET，尚未验收] News推荐量默认Novel，Repurpose显式独立选择，来源不自动互换；确认和结果可准确对账视频数量、新增语义及Presentation，Repurpose不重复累计semantic。

## Authoritative References

- [Operations Index](../../operations/README.md)、[Authority Map](../../operations/AUTHORITY_MAP_V1.md) 路由现有机器Owner。
- [Publish Copy合同](../../operations/PUBLISH_COPY_V1_CONTRACT.md)、[Mix Export Anchor](../../operations/GENERATION_EXPORT_ANCHOR_V1_CONTRACT.md)、[Compatibility合同](../../operations/PROFILE_COMPATIBILITY_V1_1_CONTRACT.md)、Native News生成/导出合同及 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/schemas/`。
- [BASELINE_EVIDENCE.json](BASELINE_EVIDENCE.json) 绑定当前源码与证据；[FOUNDER_TARGET.md](FOUNDER_TARGET.md)是本轮目标附录。

## 批准边界与后续 Gate

D-P01/G02的产品类型定义、D-P02/G03的分配规则、D-P03/G05的来源计数规则已按用户明确选择确定；没有剩余阻止本次目标批准的上述产品问题。原 [GAP_REGISTER.md](GAP_REGISTER.md) 保留BL-0时点的登记，不据此改写为功能已完成。

- G02剩余的Pattern/Compatibility适用资格仍由原Owner独立批准，不因目标冻结自动获得；Stage和Style选择不能授予生产资格。
- G08的20/40条仍是目标数量，容量、并发、真实成本/限流/耗时及质量未验证；后续实施须逐级隔离验证，通过前不作生产承诺。
- G13保留News v1.2仅已有合法资格隔离范围；本次不向所有客户开放News，生产、4090和真实模型仍为独立Gate。
- 稳定期周期初始值/上限、全0配置、具体设备和其他UX/架构细节仍待设计及原Owner审查；本Baseline不冻结这些默认值，相关行为确定并经适用Gate前不能实施。
- 本次只批准Baseline目标。已有Plan及Proposal仍为冻结前草案，须针对本次目标变化重新判断适用性并完成Design Readiness和独立Plan Review；不自动冻结Plan，不授权B1～B4或任何实现。

## 1. Current Truth — 代码和Checkpoint身份

本节与以下Current Truth均为有出处的当前事实；目标只在上面的TARGET段和FOUNDER_TARGET出现。

| 项目 | 已核实的结果 | 证据性质/出处 |
|---|---|---|
| 当前实际分支/HEAD | `main` / `ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd` | CODE_PROVEN：只读Git、`../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/CHECKPOINT_AND_PROTECTION.json` |
| 当前tree | `ce933b32cbee61c2d1299a5db233ac76d3af1fff` | CODE_PROVEN：Git tree身份，不是业务artifact SHA |
| 最新Checkpoint branch | `codex/checkpoint-publish-copy-founder-uat-20261022` | CODE_PROVEN：local ref与Checkpoint报告，未联网/未Push |
| Checkpoint完整SHA / parent | `ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd` / `629a934d6a3a73525e7e14bec12f85e50f5fb4fa` | CODE_PROVEN；旧参考是父提交，未当最新Checkpoint |
| clean | Checkpoint报告当时clean；原BL-0审计起止main clean（见原终检证据） | CODE_PROVEN；同内容不等于新提交 |
| 相对上一News冻结629a934 | 56文件，+6482/-109；新增Publish Copy、versioned delivery、两模板、Ledger anchor/transition与测试，保留Native owners | `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/CHECKPOINT_CONTENT.json`含完整stat及56文件blob核对 |
| 先前Creation freeze | `1b6fc870bdf6768db10a561385f05ac81475c75d` | 两个对比范围均保留，不模糊“上次冻结”；该freeze以后还有Compatibility、generation recovery、News v1.2、REC-01/UI与本次Publish Copy |
| 源码一致性 | 641个受版本控制文件与主线exact-commit完整回归时raw SHA一致；Checkpoint新增56文件的Git blob和normalized当前内容核对 | CODE_PROVEN；raw CRLF与Git LF SHA分开，不用normalize校验业务Receipt |
| UAT来源关联 | Founder Publish A/B/C/D原在629a934上未提交工作区完成；保留p1的33/33改动生产文件与新Checkpoint报告字节一致；1个测试导入路径可移植性修改独立列出 | FOUNDER_ACCEPTED + CODE_PROVEN；没有声称在最新commit重新做过全部Founder UAT |

未发现关键已验收功能丢失：Mix核心、Novel News、Repurpose News及PUBLISH-COPY均有原生owner和当前继承代码。没有补代码或创建新版本。本机存有ignored环境/数据/qualified release/合成transport harness，这些是运行依赖和证据，不是缺失的正式功能代码；Checkpoint本身也不携带生产客户Authority、feature flag启用值或News生产资格。原独立UAT服务已由先前整理停止，本轮没有启动任何Console或浏览器运行节点。

## 2. 已验收能力与实际证据范围

| 能力 | 可成立的接受/验证结论 | 不可推广的结论 |
|---|---|---|
| Mix核心 | Founder历史隔离功能UAT通过：1条、修改后审核、导出与原Task/Closure/Ledger保护；最新代码继承且有准确版本回归 | 不证明三个业务subtype、20/40批量、真实模型文案质量 |
| Novel News | Founder A新内容核心路径完成；原生schema、独立Human、导出恢复有当前exact-commit离线测试 | 不证明所有新闻方向/客户、真实模型效果或生产资格 |
| Repurpose News | Founder B历史重表达核心路径完成；semantic+0、presentation history单列 | 不计为Novel，不增加新语义容量 |
| Publish Copy A/B/C/D | 源码匹配的隔离功能接受；两种新版Excel、draft edit/confirm、多beat映射及D中断补Receipt/Completion而Task/文件/Ledger不重复 | 等待体验仍OPEN，真实provider质量/生产未验证；接受报告不是业务Approval |

来源：`../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/FOUNDER_ACCEPTANCE_PROJECTION.json`（原报告路径/原SHA及脱敏结果）。本轮不重新执行付费模型或全套Founder UAT。

## 3. 产品结构与Native Authority Graph

Customer → Creation Entry → Qualification → Native Request → Task → Generation → Native Human Review → Publish Copy → Native Export / Closure / Ledger → versioned supplemental Delivery。

原生分支：Mix content planning/generation；Novel News one opportunity/4–8 Beats；Repurpose one historical semantic source/4–8 Slots。Task只是执行投影；当前系统无新的跨这些Request的批次Authority。各节点的准确Owner、函数、原行号、schema/版本、HTTP/Gateway、输入输出、SHA/Receipt、人工门、恢复/撤回和测试见 [AUTHORITY_AND_SOURCE_GRAPH.md](AUTHORITY_AND_SOURCE_GRAPH.md) N01～N18 与其机器版 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/CHAIN_NODES.json`。

明确的共享门：Current Approved Business/Speaker、Business/Speaker SHA binding、Known Fact、first-person scope、隐私、Pattern已批准支持scope、Compatibility独立Human决策及active release/live control、novelty/content memory、内容Human Review、媒体Rights/Privacy/Event Relationship/Proof边界。脚本生成没有授予媒体权利。存在derived restriction时News路径仍fail closed（CT25），不能由旧UAT或阶段选择消除。

## 4. 类型能力Current Truth

| 维度 | 当前事实 | 证据 |
|---|---|---|
| production_profile | 入口限定mix/news；Registry/Pattern/Compatibility约束实际可用性 | CT01/CT03/CT24 |
| creative_style | 有内部 primary_angle/narrative_mode，不存在Founder三类独立正式请求参数 | CT08，检索范围在证据中明确 |
| operating_stage | 无本轮三阶段preset或周期数量配置合同 | CT01/CT04/CT27；与FT03～05的差距是正常delivery delta |
| delivery_template | 只呈现已批准/确认内容；新版Mix5列、News4列，exact模板SHA校验 | CT21/CT22；模板并不赋予类型资格 |

| 能力 | 状态 | 有限解释 |
|---|---|---|
| Native Mix | VERIFIED_SUPPORTED | 隔离原生链；不能推广为三业务类型 |
| Novel News | VERIFIED_SUPPORTED | 一个视频/Request；当前v1.2 price_offer_led隔离资格 |
| Repurpose News | VERIFIED_SUPPORTED | 一个presentation/Request；semantic+0 |
| 人设型 | PARTIALLY_SUPPORTED | 内部first_person_viewpoint/operator_principle；正式业务类型合同UNSUPPORTED |
| 故事型 | PARTIALLY_SUPPORTED | 内部bounded_known_story/quote；正式业务类型合同UNSUPPORTED |
| 高转化型 | UNSUPPORTED | 未找到正式独立规则、可选策略/配额/身份；content_intent=mixed、cta_intent=none |

三业务类型的实际结果可区分性 **UNKNOWN / NOT_VALIDATED**，不存在足够证据将通用Mix输出认定为三套正式策略。每项10维核对（owner、prompt/Pattern/style、approved规则、结果、gates、Compatibility、测试、时长、数量、批量身份）见 [CAPABILITY_MATRIX.json](CAPABILITY_MATRIX.json)。目标时长仅guidance；不证明最终视频时长（CT28）。

## 5. 批量能力和容量Current Truth

| 审计项 | 当前实际支持/限制 | 分类/证据 |
|---|---|---|
| 一次配置多种业务类型 | 当前一次只选mix/news及单quantity；无stage或四种独立配额 | CODE_PROVEN CT01/CT27 |
| 一次创建多个Request | 当前confirm只建立/恢复单Request；没有multi-request批次admission | CODE_PROVEN CT04/CT09 |
| 多Request同客户 | 历史按Business关联可列出；同Business/profile active Request会阻断或复用，不能声称批量同时建立 | CODE_PROVEN CT04/CT27 |
| 稳定Slot/结果对应 | Mix有本Request内content_id/concept_ref/slot_id；News有beat_id/slot_id；无跨Request Batch Slot ID/类型合同 | CODE_PROVEN CT07/CT10/CT11 |
| 数量精确对应 | requested/confirmed区分；容量不足需缩量/阻断且不padding；Human可只批准子集，partial生成可能不足 | CODE_PROVEN CT01/CT07/CT12 |
| 20条 | 单Mix入口整数上限20；不是20条真实成功或整批能力验证 | CODE_PROVEN admission；RUNTIME批容量 UNKNOWN / NOT_VALIDATED |
| 40条 | 超单Request上限，且无40混合batch合同/端到端测试 | UNKNOWN / NOT_VALIDATED CT01/CT18 |
| 并发/限流 | standard background与operation executor各1 worker；task_queue_max默认20、GPU pending/user默认3；不是provider QPS/RPM或40并发 | CODE_PROVEN CT18；真实API限额 UNKNOWN |
| cancel/pause/retry/resume | 有合法unapproved Request disposition、单operation恢复；无整批状态机/控制合同 | CODE_PROVEN CT14～18 |
| 单项故障不连累其余 | item级Human subset/Publish partial可保留；新批次跨Native任务的失败隔离无合同和测试 | PARTIAL / 新Batch UNKNOWN CT07/CT12/CT20 |
| 重复点击/重登 | 当前key/operation/parent/SHA、UI in-flight dedup、stable principal恢复存在；不等于新Batch幂等 | CODE_PROVEN CT04/CT14～18/CT27 |
| 语义去重/memory | business-wide Ledger+CIU/semantic/presentation，Mix planning内去重；无跨新Batch Request的预留语义机制 | CODE_PROVEN CT30 |
| 集中审核 | Request内item/Beat/Slot审核可复用；无跨整批统一批准合同 | CODE_PROVEN CT10～12 |
| 组合导出 | 原Request版本交付、Mix多row / News单row；无新Batch按subtype汇总跨Request导出 | CODE_PROVEN CT21/CT22 |
| 扩展新视频类型 | 当前没有可证明的正式业务subtype扩展合同；未来可扩展是目标要求 | CODE_PROVEN 当前入口；FOUNDER_ACCEPTED FT06 |
| 成本/Token/真实吞吐/耗时 | 不从历史个案或provider配置猜测 | UNKNOWN / NOT_VALIDATED G08/G16 |

“批次”一词在原生Mix generation batch内已有用途，不能等同本专项的跨类型20/40条创作批次。

## 6. UX、权限和状态Current Truth

| 实际页面/动作 | 可复用实现 | 目标缺口/限定 |
|---|---|---|
| 客户列表/详情 | 运营列表derived action、“开始创作”，详情“去创作/检查创作条件”；按客户history | 文案并非所有入口统一“开始创作”；客户共享Console不证明多租户隔离 |
| /create客户上下文 | hidden Business、Approved Speaker选择、自动带入customer_context | 没有stage/free-combination配置；不重新录入原资料已部分满足目标 |
| 类型/数量 | mix/news radio；News novel/repurpose模式；Mix1～20，News数量锁1 | 没有人设/故事/高转化单独数量或0配额 |
| 资格/Request创建 | 查看可创作内容→容量/阻断→明确确认→Request/handoff/resolve sources | 当前多步骤，不是整批一次授权；opportunity/历史来源选择仍需用户理解 |
| Task进度/恢复 | CreationStepper、Task progress、继续原创作、explicit unknown retry提示/确认 | 这些是单Request/Task/Publish状态；无整批全部完成/部分失败等正式数据支持 |
| Human Review | item-level决定；News Beat/Slot；审核与生成完成明确分开 | 跨Request集中Human操作未实现；工程来源/证据details仍可见，不能宣称已消除全部工程概念 |
| Publish Copy | draft编辑/保存/单独确认、remaining target、unknown费用确认、导出恢复、上次已确认版本下载 | 不等于平台发布，不授媒体权利；存在等待体验open |
| Excel/历史 | 严格Native下载、exact receipt、版本链与原Request入口 | 无跨新Batch按类型聚合下载/history |

源码证据CT02/CT27/CT29，前端回归与客户导航测试见TEST_EVIDENCE。本轮没有把目标设计图当实际浏览器截图，也没有启动服务重做视觉验收。

历史移动范围：`.local/evidence/publish-copy-ui-20261021/RESULT.json`记录1440×900、390×844、320×844，8项局部只读检查无横向溢出，覆盖Mix初始/Novel完成及未保存编辑/Repurpose待确认；**其UI文件SHA已不同于最新Checkpoint**，只作历史RUNTIME_PROVEN，不沿用为当前移动端PASS。原目标手机截图仅Founder Visual Reference，未取得可信原始素材SHA。当前exact-commit前端185测试通过只证明所测试DOM/行为，不证明当前手机真实视觉/完整UAT（G17）。

## 7. 关键恢复和不可变历史边界

- REC-01：durable dispatch无response=unknown；不自动重发；明确确认retry形成新parent operation。saved response本地恢复、late worker fence、exact sources/actor/memory。CT14。
- C3-05：仅初次zero accepted content且transport/response故障；不能将质量拒绝、partial、已Review/closed扩大成再生成权。CT15。
- News Native Export Recovery：Intent/Prepared绑定完整XLSX、source/template/actor；exclusive publication；unbound orphan不自动收养；Receipt后缺Closure只补缺失原步骤。CT16。
- Publish Copy：最多5 targets/call；partial/edit保留；所有制作行完整并显式确认才导出；不知道调用结果时不重发。CT19/20。
- 新Delivery在原Request内有version chain，先验证原Native结果，Mix依 authentic historical anchor；0 semantic/exposure/presentation delta；原Task/Receipt/Closure/Ledger不重复。CT17/22/23。
- Cross-business：导航owner不一致、foreign target、source SHA及Ledger Business不匹配会阻断；当前shared-customer access并不证明未来代理商租户授权。CT26；不做AUTH/OIDC扩展。

## 8. 执行证据、保护和适用性

**本轮RUNTIME_PROVEN**：在 `ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd`、clean source上执行隔离focused checks：Pipeline四模块112 passed，Console客户导航+JS桥接23 passed；合计135 Python tests，桥接内185 JavaScript passed，0 fail。准确命令、case、原JUnit/log SHA和Node版本在 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/TEST_EVIDENCE.json` 与 `../../../.local/evidence/creation-batch-ux1-baseline-20261022/review/evidence/tests/BL0-*`。没有付费模型、生产root mutation或live Authority smoke。出现现有Starlette/httpx与anyio deprecation warning，非失败；本轮未升级依赖。

**历史exact-commit RUNTIME_PROVEN**：`.verify/cdfa4195/summary.json`记录 `ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd` full isolated `python tools/verify.py --windows-short-temp --timeout 1800` passed，source unchanged；1508 JUnit testcase nodes、185 JS嵌在1个Python桥接、30 FRP offline checks、27 verifier unittest checks。已读原summary与JUnit；本轮对641个tracked文件raw SHA逐项对照该回归的MAIN_SOURCE_IDENTITY，无漂移。不是本轮重跑full，不宣称生产/live/真实模型通过。

**历史和其他工作树保护**：当前Git仅root main一个registered worktree；19个旧worktrees原已retire/unregister而完整保留；本轮只核查不做move/prune。603个dirty原始备份SHA一致；各保留树当前源码/文档/合同及当时dirty路径复核无差异；5101个原保护文件SHA一致。Git all-refs bundles另有保留，当前只读verify；未追踪大型cache不声称逐文件全面重放。终检对本轮开始指纹再比对，不更改历史收据或归档。

原BL-0审查包、A～H历史快照、证据及原SHA继续保留在 `.local/evidence/creation-batch-ux1-baseline-20261022/`；原临时测试在 `.verify/cbbl0/`。可编辑的 Baseline 和配套交付文档已归位到 `docs/deliveries/creation-batch-ux-1/`，历史快照不再作为编辑入口。此次归位不修改产品目标、验收标准、事实Owner、Draft/Revision或独立批准边界。

## 9. Founder目标对照与审查结论

| 目标 | 当前对照 |
|---|---|
| FT01客户→独立创作/自动资料 | 部分已有：customer-scoped页面/Approved资料；当前入口文案不完全相同 |
| FT02两种方式 | 未实现；不要与News novel/repurpose模式混淆 |
| FT03/04三阶段前两段20/40 | 目标已记录；拆分未定；当前批量未验证 |
| FT05稳定4天8条×明确周期 | 目标已记录；无周期preset/整批合同 |
| FT06自由组合/0/扩展 | 目标已记录；无四业务类型独立数量；全0产品未定 |
| FT07一次启动/进度/恢复/集中审核 | 单Native Request可复用；跨类型Batch未实现 |
| FT08发布字段/两新版Excel/历史保护 | PUBLISH-COPY与两模板已继承；新Batch跨Request按类型汇总未实现 |
| FT09四层维度 | 本包严格分开；三Mix类型正式规则/资格未知 |
| FT10真实Gates | 原生拥有；目标必须保持，任何stage不授权 |
| FT11手机参考 | 仅目标参考；当前原始截图SHA未核验 |

Current Truth覆盖30项CT结论和18个链节点，每项有函数/行号、source SHA与原生所有权；具体已跑/未跑以TEST_EVIDENCE为准。Gap共22项，其中UNKNOWN 9、BLOCKED 3、规划关键5。**包已可独立审查，Draft尚未获批，安全正式Plan仍未就绪。**

原BL-0/BR-01交接（历史）：当时Revision 1为Draft，BR-01只批准Current Truth与差距范围、授权条件式Plan草案，没有批准G02/G03/G05产品规则或实施。该历史裁决不改写；原Manifest、ZIP及SHA继续只绑定其原审查快照。

当前交接：本页Revision 1已按用户冻结指令及三项明确选择批准。唯一当前目标为本页已批准Key Decisions、Preserved Constraints和AC-01～AC-10；第1～9节原审计事实及其测试范围保持历史身份。下一适用步骤为本UI/UX Delivery的Design Readiness，再由Planning Owner评估旧草案并完成独立Plan Review；本次不自动调用下游Skill、不改Plan、不实施、不Commit/Push/Merge或部署。
