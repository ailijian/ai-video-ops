# CREATION_BATCH_UX_1 — Plan Revision 5（开工准备齐备，待独立批准）

Delivery: creation-batch-ux-1
Plan Revision: 5
Scope: iteration / 有限批次创作配置与原生编排、审核及派生交付
Baseline: [BASELINE.md](BASELINE.md) / Status Approved / Revision 1
Baseline Scope: iteration / BL-0 CREATE_BASELINE_ONLY（保留原审计身份；本计划消费已批准目标与后续明确规划授权）
Baseline SHA-256: 13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3
Code checkpoint: ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd
Resolved PLAN: docs/deliveries/creation-batch-ux-1/PLAN.md
Resolution source: 既有Delivery PLAN / 用户要求完成全部开工准备
Mode: Revise（无Baseline Amendment，无B1～B4 accepted checkpoint）
Workflow collection: ai-native-workflow-2026-09-06-governance-verification-1
Planning Preflight: PASS（附重要说明；R4实际输入SHA f9cea03c7c160f586d8d3dda24515ca5400763056f4388b5c17931bf3b439e8e）
Execution authorization: Plan Freeze Not Authorized / Implementation Not Authorized

本轮用户授权完成全部开工准备，沿用已选implementation-planning方法细化合同、UI细则、职责、环境和送审材料；本轮只改文档/本地证据，不实施B1～B4。先在R4实际输入完成Preflight PASS，再形成本R5。独立Plan裁决、合同范围批准和实施许可仍须真实作出，不能从“完成准备”推断已获得。

本轮[Planning Preflight](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/evidence/PLANNING_PREFLIGHT_RESULT.json)消费原R3 Design PASS、R4生产者的适用性记录和I-01～04；Baseline、DESIGN_OPTIONS与PRODUCT_DECISION_REGISTER保持原字节，不重做Design裁决。原R3预检时28项上游输入逐字节匹配的事实仍保留其时点。R4完整文档/Manifest、当前方法和环境证据均保留新目录；当前R5的独立审查尚无结果。

## 1. Outcome、范围与保留约束

从客户进入独立配置，继承已批Business/Speaker与当前限制；阶段/自由组合形成有限批次。四业务类型与production_profile、creative_style、operating_stage、delivery_template分开。D-P01三Style事实/人物/禁称规则、D-P02合计推荐后明确分配、D-P03 Novel默认及Repurpose独立计数只归Baseline，不在Plan重定义。

本轮已确认的UX归[PRODUCT_DECISION_REGISTER](PRODUCT_DECISION_REGISTER.md)和[DESIGN_OPTIONS](DESIGN_OPTIONS.md)：总0不启动；初显1周期仍须明确有限N；采用B逐次安全生成并累积待审、告一段落后集中核对；部分结束仅停未派发，保留成果/在途/未知与差额，其他合法内容按原Gate审核交付。最终最多News/Mix各一份汇总，零合法行不出空文件。没有重新打开产品选择。

不做：第二Review/Compatibility/Export/Ledger Authority、静默换类型/来源或凑量、重写客户事实/历史Receipt/Closure/Ledger、AUTH/OIDC/qudao、付费模型、生产/4090或自动Git控制。新合同/状态/API均PROPOSED / NOT IMPLEMENTED；Stage预设和产品定义不授Native资格。当前News v1.2仍只在已有合法隔离范围使用。

## 2. Authoritative references与实际输入

| 来源 | 拥有范围 |
|---|---|
| [Baseline](BASELINE.md)、[既有批准来源BR-02](BASELINE_APPROVAL_RECORD.md) | 已批准目标、精确AC-01～10与保留约束；实际用户冻结及三项选择，不重新签署 |
| [Operations Index](../../operations/README.md)、[Authority Map](../../operations/AUTHORITY_MAP_V1.md) | 原Business/Speaker/Pattern/Compatibility/Request/Human/Export/Closure/Ledger唯一Owner；SQLite仅投影 |
| [Productized UI](../../design/鲸汤%20AI%20视频代运营工作台｜Productized%20UI%20&%20Information%20Architecture%20Freeze%20V1.0.md)、[Internal Console](../../design/AI%20Video%20Ops%20MVP%20V1｜Internal%20Console%20UX%20&%20Interaction%20Freeze%20V1.0.md)、[NAV1](../../design/NAV1_CUSTOMER_LIST1_IMPLEMENTATION_REPORT.md) | 上游Design PASS已解析的呈现/响应式、原交互/Human/权限、客户导航局部范围；不证明新功能已实现 |
| [Compatibility](../../operations/PROFILE_COMPATIBILITY_V1_1_CONTRACT.md)及原News可执行Owner | 独立审批、准确source/release与撤回；不是Stage或Style开关 |
| [Publish Copy/Delivery](../../operations/PUBLISH_COPY_V1_CONTRACT.md)、[Mix Anchor](../../operations/GENERATION_EXPORT_ANCHOR_V1_CONTRACT.md) | 原发布稿确认、原writer委托及历史验证；open attempt whole-Ledger fence不弱化 |
| [News Export Recovery](../../operations/NEWS_NATIVE_EXPORT_RECOVERY_V1.md)、[News Generation Recovery](../../operations/NEWS_NATIVE_GENERATION_RECOVERY_V1.md) | 已派发未知不重发、精确源/actor、Native Prepared/Receipt/Closure及幂等 |
| [tools/README](../../../tools/README.md)、[Pipeline test layers](../../../ops-pipeline/tests/README.md)、[Console pyproject](../../../internal-console/pyproject.toml) | 既有验证、隔离、全仓范围及项目内存储规则 |

机器字段以原脚本/Schema为准，精确函数/行号/raw SHA继承R4的38份源码证据，本轮另补S01～08消费者/组件路由。NCR-01～08和旧测试是Observed Evidence，不升为产品Authority。当前代码main/ceac，未提交交付文档存在；不能把HEAD单独当完整实现起点。原BL-0审计与旧UAT只在其准确版本/范围继承。

## 3. Documentation Delta

Update:
- 原Native Request/Planning/Generation strict contract与相应Console接口说明：原Owner在B1/B2消费前同步Style/请求上下文/恢复版本，避免新字段被旧reader忽略。
- internal-console/README.md与原机器Schema说明：B1配置/单Request、B2协调与恢复、B3集中Human/派生交付各在真实能力形成并验证时更新Current Truth，不能先把本提案写成已实现。
- docs/operations/PUBLISH_COPY_V1_CONTRACT.md及Authority Map适用Owner路由：B3原Owner批准并验证multi-parent委托后补准确范围，保留旧Receipt/历史读法；不创Batch Export Authority。
- 本Delivery执行/Gate/测试/Owner导航与Manifest：各批准、实现和验证发生后由有权控制者保留原结果和输入。设计/产品来源文档只在真实语义变化时由其Owner维护，不能机械改编号使Design交接失效。

Create:
- none（无新长久产品/架构Authority文档；候选合同仍在既有MACHINE_CONTRACT_DELTA_PROPOSAL送审）。

Generated:
- B1/B2/B3原机器Owner产生的新版本Schema/验证材料、不可变协调记录及原Native运行记录；只有真实人审/执行才能产生业务Approval/Receipt，不由Plan作者写入。
- 各Stage测试/浏览器/资源与恢复证据、当前文档Manifest及最终XLSX/row manifest由对应writer在真实步骤生成，文件SHA不能代替许可。

Unaffected:
- Business/Speaker/Case事实与批准lineage、媒体Rights/Privacy/Proof；不借Style、Batch或Case研究创造客户Truth/素材权。
- 原Ledger语义、CIU/novelty、Repurpose semantic0、旧Canonical/Closure/Receipt/Anchor；预留只协调未完成意图，不是第二曝光历史。
- 既有认证/Session/CSRF/共享客户范围、单进程/GPU guard和原生产Runbook；不引入多租户/OIDC或部署。

## 4. Implementation Delta

Current State为单Native流程、mixed/none、原active/equivalent语义和单Request交付。Target差异是：原Mix链真实消费版本化Style及稳定身份；同客户有限配置/Slot精确关联；原Request/Quality受限Admission及pending语义排斥；协调多个原Human/Publish动作；原Export/Delivery内两Profile multi-parent派生；真实可对账的失败/结束/恢复投影及逐级验证。

本轮技术审查及开工细化建立了具体路线，不授新能力：C01～08仍须原Owner版本/范围审查；工程合同决定在依赖实现前，A01/A02运行资格在实际生成前；A03/A04分别在B2/B3实现前。未签审批不等于当前Authority不明；本轮已把“未知如何实现”具体化为原Owner可审的差异/反例/关闭证据，没有把Native审批标PASS。

## 5. Stage Progression与比较边界

每Stage只有在Required Verification及Required Gates都满足后才有资格形成Git checkpoint。第一Stage从届时实际ceac checkout加相关staged/unstaged/untracked、机器合同/fixture/release/config与环境开始，由控制责任方记录可恢复输入；后续仅引用已真实存在的accepted checkpoint，不预造SHA。修复不移动原始比较边界。

所需Code Review统一采用所选collection的`skills/code-review/SKILL.md`及其input contract，绑定原Stage比较边界、实际候选、风险/约束焦点、已有验证与历史finding。同范围代码审查不重复设Gate；原业务人审及合同批准仍独立保留。本轮不自动调用该Skill、不选择未经验证的执行器，也不签独立Code Review。

本Plan不Commit、Push、记录接受或自动推进。阶段执行仍需当次明确授权；下游不以规划PASS代签原人审。异步非blocking不能满足必需Gate；迟到真实blocker重开受影响范围，既有接受保留其原身份。当前无B1～B4接受史可改写。

## 6. Stage overview与及时反馈

| Stage | 顺序与最早可运行结果 | 依赖/关键反馈 | 关闭责任 |
|---|---|---|---|
| B1 | 获批单Style/单Native Request从配置到原Human/Publish/导出的真实薄切片，含一次非法输入拒绝；再扩三Style/配置 | I-01、C01～03适用合同/资格先定；最早接缝后独立Code Review与轻量Human E2E，不堆到阶段末才集成 | B1实现/验证Owner；控制方指派阶段接受者 |
| B2 | 先2～5中的同Style K=2及至少2合法机会的待审Novel；验证精确Slot、单派发、unknown/重登/结束恢复 | B1关闭、A03/C04～06正式审查；先原Native交互及代表故障，后扩协调UI/组合 | 原Request/Quality/recovery实现Owner与独立Reviewer |
| B3 | 先两个已合法完成parent的同Profile严格汇总/中断恢复，再News＋Mix与集中审核/发布流程 | A04/C07/C08先审；复用原Human/Publish与父Receipt；早期源/恢复审查 | 原Human/Export/Delivery Owner；控制方指定集成证据负责人 |
| B4 | G-08/09后20→40→明确有限N；真实三端旅程与最终完整回归 | 每级源/资格/证据满足才升级；失败停在已验证范围，不padding/换源 | 控制方在执行前指定唯一最终证据汇总/关闭责任人；独立验证＋Founder UAT |

上述Owner是职责，不虚构审批人姓名。角色指派在相应依赖工作前明确。原Owner技术约束与证据反例见OWNER_AND_DEPENDENCY_MAP；没有新增独立审批系统。

## 7. Engineering evidence mapping

| 约束/风险 | 原Owner及真实入口 | 最早工作包与反例/证据 | 依赖边界 |
|---|---|---|---|
| Style不是通用标签；事实/人物/资格不越界 | generation_request_handoff / resolve_generation_batch / review_generation_batch_v2；原Pattern/Compatibility | B1-P1，exact Style/prompt/source贯穿且legacy未知版本拒绝；缺事实/CTA/scope负例 | 扩其他Style前反馈；缺资格不dispatch |
| active例外不串请求；语义不重复 | 原Request active/equivalent、Quality机会与CIU/Novelty | B2-P1，same key恢复同Request、外Batch/Style拒绝、同源竞争只一预留；admission后缺binding崩溃 | B2-P2及规模升级依赖该真实结果 |
| open memory不重绑，unknown不重发 | Novel state/recovery、Publish _current、原人审/导出 | B2-P2/B3-P1，生成/人审在有效memory下，合法已完成记录用原reader；外部append期间open attempt阻断且调用计数不增 | 不以全局新epoch事务为前提；受影响源变化按原恢复 |
| 停止协调不伪造Native终态 | resolve_generation_request原条件、Console abandon gateway | B2-P2，结束未派发量且保留在途/unknown/差额；不得批量调用旧abandon绕过blockers | B3计数/部分交付只读Native证据 |
| 汇总不授审批/曝光；历史与Business隔离 | 原三export writers→creation_delivery；strict XLSX、Anchor/Closure | B3-P2，两个parent/每行准确确认与来源；缺父/foreign business/半集合/已完成replay反例 | 扩两Profile前证明；全局最终证据B4刷新 |

## 8. Native合同与审批的真实状态

| ID | 候选合同 | 原Owner | Gate | 阶段 | 当前AC |
|---|---|---|---|---|---|
| C01 | Versioned Style Catalog | Pipeline原Mix规则消费者 | G-01 G-02 G-03 | B1 | AC-03 AC-08 |
| C02 | Native Mix Style / Request / Concept identity | 原Request/Planning/Generation及Review/Export消费者 | G-02 G-03 | B1 B2 | AC-03 AC-08 AC-09 |
| C03 | Batch draft / confirmed intent | Console协调入口＋Pipeline规范化合同 | G-01 G-02 | B1 | AC-07 AC-09 AC-10 |
| C04 | Native bounded batch admission / slot binding / operation | 原Request Owner；Task仅投影 | G-02 G-03 G-04 | B2 | AC-04 AC-07 AC-08 AC-10 |
| C05 | Owner-owned opportunity / semantic reservation | 原Content Quality/Native Ledger Owner | G-03 G-04 | B2 | AC-04 AC-07 AC-10 |
| C06 | Native phase evidence / generation epoch / recovery | 各原generation/planning/Publish recovery Owner | G-04 | B2 | AC-04 AC-05 AC-07 |
| C07 | Source-bound aggregate Human command | 原Mix/Novel/Repurpose Human与Publish确认Owner | G-05 | B3 | AC-04 AC-07 AC-08 |
| C08 | Two-profile multi-parent supplemental delivery | 原Export writers明确委托既有creation_delivery_v1 | G-05 | B3 | AC-04 AC-07 AC-08 AC-10 |

NCR-01～08技术审查与组件证据使上述差异可具体规划；它们不是正式审批。A01/A02管Style相关Pattern/Compatibility/release，A03管Native受限Admission/预留/源与恢复限制，A04管原writers multi-parent委托，A05管每项真实内容及Publish确认。G-00～14沿用已有登记，不再新增通用readiness Gate。

Implementation Readiness Obligations按上游I-01～04分别进入B1、B2、B3及UI/设备验证；每项有原Owner、可观察关闭证据和依赖截止点。Owner拒绝某合同或真实接缝推翻假设时，停止其依赖并回到影响范围复评；不静默改A或文件列表。

## B1 — 视频类型、配置与单Request真实薄切片

Goal:
让合法单Style在原Native链形成可审核/交付的真实结果，并提供已确认的有限配置。

Authoritative References:
Baseline D-P01～03/AC08～10；上游Design I-01/I-04；原Request/Planning/Generation/Human/Pattern/Compatibility机器Owner。

Deliverables:
- B1-P1：原Owner确定C01/C02严格版本及消费范围，建立合法单Style最薄路径（只合成外部transport）；原source/事实/人物/Pattern/Compatibility/Human/Publish/Export真实参与。成功及未知Style/越权事实拒绝反馈、独立Code Review后，再扩其他Style/数量。
- B1-P2：C03有限draft/确认意图、客户上下文继承、stage/free统一配置；P/S初始未分配，总0拒绝，N初显1仍明确确认，来源/推荐与实际数分开；修改使旧preview失效，double click同payload同server key。
- 所需版本化Schema/Style策略/strict消费者及最小fixture/runner在此建立，不能把新字段塞旧v1.0。样本用于可区别规则/结构验证，合成模型输出不证明真实模型质量。

Non-goals:
不调度多个Request，不做20/40承诺、Native资格自动授予或新Review/Export Authority。

Affected Surface:
原create入口、Request/handoff、source/content planner、generation、Review、Publish/Export消费者及客户配置页。

Architecture Impact:
- Material — Authority Map唯一Owner、原strict reader/事实/人物/资格及immutable lineage；变更共享Native身份/消费边界。
- Structural Enforcement: 复用原Schema/strict reader、source/权限/资格验证；为新版本补最小正反契约校验，拒绝未知字段/版本而非默默降级。

Review Need:
Code Review — 共享Native新旧reader、Style实际prompt/策略消费、source SHA/人物scope与CTA限制；需最早薄切片后反馈，不能仅看标签。

Dependencies:
- I-01：原有权方先对C01/C02版本与策略边界作工程合同决定，再实施其消费者；适用A01/A02 Pattern/Compatibility/隔离release在实际依赖生成前真实齐备。不得要求尚未实施的生成能力先签运行PASS，也不伪造fixture资格。
- 设计输入与用户规则已确认；组件/状态/响应式细化由设计/前端责任人在依赖UI前完成，不能改产品含义。
- 首次实际比较边界按第5节捕获，包含未提交内容；R3/R4/R5只是规划输入，不是accepted implementation checkpoint。

Risk:
- Level: High
- Rationale: 影响所有Native消费者与事实/人物/版本兼容，误放行会污染后续审批/导出。

Verification Scope:
- Profile: Affected Integration
- Rationale: 局部版本/Native薄切片跨多个原Owner，需受影响集成；无需每阶段全仓重复。

Required Verification:
- 复用Pipeline原generation_request、resolve_generation_batch、Native Human、Publish契约测试能力和Console/JS隔离路由；在此建立缺失的新Style/config用例后才依赖。
- 记录三Style exact来源/不同策略输入与规则、至少单Request真实成功/非法事实或scope拒绝；原Approval/Export/Receipt不被stub，legacy路径保持。
- 原始边界确定后使用真实`python tools/verify.py --mode affected --base <实际起点ref>`；占位符须执行者替换为可恢复实际ref，并保存dirty输入。CI选择不明按原runner规则扩大。
- 轻量Human E2E在首次合法配置→审核→交付薄切片进行；设备/角色/版本明确，未执行端NOT_VALIDATED。

Asynchronous CI:
- Workflow: None（未选择新异步workflow）
- Blocking for Stage Progression: Not applicable；下列必需验证与Gate仍blocking。

Required Gates:
Self Verification；针对以上边界的Code Review；Stage Acceptance（共享身份基座需独立证据判断）；早期Human E2E；原资格/合同前置。

Stop Condition:
G-07适用证据齐全：至少最薄成功/拒绝及随后三Style真实消费、配置语义/legacy兼容可核；尚未通过的Style不得声明支持。通过所需Gate前B2不得依赖新消费者。

## B2 — 原Request/Quality内的小容量跨Native协调

Goal:
在原Owner受限上下文中逐次生成多个待审Request，稳定Slot与语义预留可恢复且不重复。

Authoritative References:
Baseline AC04/07/10与REC-01/C3-05；上游I-02；原Request/Content Quality/Novel/恢复Owner；NCR01～04/07/08。

Deliverables:
- B2-P1：原Owner实施经审查的C04/C05，same Batch/Business/Profile上下文、Style/ordered Slots/source/actor及server replay key同时约束admission和equivalent恢复；其他Batch/legacy不继承例外。原Quality的pending预留不是已communicated Ledger。
- 先以同Style K=2及至少2独立合法Novel机会的真实Owner路径验证；Native admission完成但binding缺失、同语义竞争和重登回放有证据后，才扩slot/调度投影。
- B2-P2：C06复用每provider intent/dispatch/response/result、exact source/memory及原actor/fencing；明确pause/end只停未派发，不循环旧abandon将未知终态化。unknown不因lease释放/重发，saved response只本地恢复，late worker不能跨Slot采用。
- 先成功与代表性dispatch后未知/绑定中断，再扩2～5组合；所需新fixture/runner在依赖前建立，调用计数及资源真实观测。

Non-goals:
不构建第二Ledger/Approval/生成真相；不删除旧active check，不全局提高并发或验证40，不改变原open-memory fence。

Affected Surface:
原Request/equivalent、Quality机会/CIU及各相关legacy入口、Native Task绑定、既有单进程队列/worker、批次进度恢复视图。

Architecture Impact:
- Material — 原Request/Quality/恢复Owner、single-process与原GPU guard；跨Request预留/持久恢复/身份及并发边界。
- Structural Enforcement: 复用原schema/source/novelty/lease验证与业务锁责任；最小新version/binding/reservation检查随能力建立，Console SQLite不得成为语义真源。

Review Need:
Code Review — 原Owner受限例外、跨Profile/legacy排斥、crash后同key恢复、Windows父子锁不重入、未知/释放/late worker；在B2-P1真实接缝后先审再叠加控制功能。

Dependencies:
- B1适用关闭与执行授权；A03的Native范围/预留/人审与来源限制正式审查并批准，批准来源可归属，不能从Preflight推断。
- 2个合法独立Novel机会与测试资格是小容量输入条件，缺失即源/资格阻断；当前price_offer_led范围不扩成全部News支持。
- 原entry的锁责任与journal/恢复协议先明确：短提交、原Gateway/child调用、短CAS；不跨模型调用持Batch/Business锁、不让child重入父进程同锁。
- 比较边界为B1真实accepted checkpoint及实际配对输入，无该checkpoint不预造SHA。

Risk:
- Level: High
- Rationale: 语义重复、外部费用、跨请求错绑或错误恢复可造成不可逆重复消耗。

Verification Scope:
- Profile: Affected Integration
- Rationale: 新协调与多个原Owner交互，需要最早真实Provider/Consumer及故障证据，独立stub队列不能替代。

Required Verification:
- 记录2～5每Slot→Native Request→final Concept/content/source/attempt；Mix同Style K条与News每Request1视频的映射分别验证，Beat不计视频数。
- 同源跨Batch/Profile竞争仅一有效占用；重复点击/重登不多Task/Request；数量不足/拒绝留差额；未知不自动remote再次调用、不超时释放来源。
- 真实Native接缝覆盖源/资格/actor撤回、dispatch前后、saved response、late worker、partial生成及显式结束；覆盖相关legacy入口，不能只测UI按钮。
- 相关生成与Human在有效memory窗口完成；外部Ledger变化使受影响open attempts按原协议阻断，原安全门允许的其他成果可处理。不得重绑memory或假造全局事务。
- 用既有affected路由绑定实际阶段起点；新runner只在建立后记录真实命令，不虚构现有Batch API命令。

Asynchronous CI:
- Workflow: None（未选择新异步workflow）
- Blocking for Stage Progression: Not applicable；下列必需验证与Gate仍blocking。

Required Gates:
Self Verification；聚焦恢复/预留/锁边界的Code Review；Stage Acceptance（不可逆外部副作用/幂等证据需独立判断）；首次可操作批次Human E2E；A03及原资格前置。

Stop Condition:
G-08小容量真实结果和代表故障能对账，所有已发/未知项有准确身份、恢复/保留，不以编排stub或40个mock任务代替；未通过不升级容量或让B3依赖未经证明的绑定。

## B3 — 集中原Human与两Profile multi-parent交付

Goal:
集中协调各原Human/Publish确认，并在原Delivery委托内交付准确News/Mix汇总。

Authoritative References:
Baseline AC04/07/08/10；上游I-03；Publish Copy/Delivery、News恢复、Mix Anchor与原Human writers；NCR03/06。

Deliverables:
- B3-P1：C07逐exact Native kind/request/content/Beat/Slot、source/version、actor与decision调用原Owner。内容审核与Publish exact draft确认分开；已成功Native决定由原reader验证后恢复协调结果，不能重复调用immutable审批伪造第二receipt。
- 相关生成/人审在有效memory下完成，再由原writers逐项闭合；未完成Publish仍受whole-Ledger fence，已完成draft及Native/历史交付用原reader。partial提交只补缺项，失败/unknown/差额保持准确。
- B3-P2：C08经A04委托扩展原creation_delivery_v1；最小两个同Business、已合法完成parents的同Profile汇总先验证，再扩News＋Mix两文件Set。逐行Slot/Style/来源/Native Approved/Publish确认/parent Receipt/Completion/Closure/anchor绑定不可变row manifest。
- 原模板/列/row4、row5不变；每文件Prepared→独占发布→Receipt，Set Completion只在非空预期文件全部验证后成立。明确partial scope不等于事故半集合；completed replay复用Task/文件/Receipt且三类Ledger delta0。

Non-goals:
不增加第二Export/Review/Ledger Authority；不复制拼接旧XLSX冒充新交付，不把未审/未知或foreign Business行装入文件，不重写旧历史。

Affected Surface:
原Mix/Novel/Repurpose Human和Publish gateways、原三export writers、creation_delivery、strict renderer/validator、Native下载/历史及批次集中视图。

Architecture Impact:
- Material — 原Human授权、Export/Delivery委托、multi-parent不可变父链及历史保护。
- Structural Enforcement: 复用原Native Human/Receipt/Closure/anchor、publish source/confirmation和严格OOXML；新composite版本验证器须在其消费者前形成。

Review Need:
Code Review — 父/行来源、准确人审与Publish确认、同Business、current权限/撤回、prepared/Set恢复、零重复Task/Receipt/Ledger；先最小汇总和故障窗反馈，再扩两文件。

Dependencies:
- B2最小合法映射有效，A04 multi-parent范围/原writer委托及C07/C08正式审查批准；不能由本规划代签。
- 可信parent必须已由其原writer闭合或验证；历史Mix必须有authentic anchor，不补造旧snapshot。没有合法parent则停新汇总，保留已有成果。
- 设计/前端责任人按已确认规则补状态/集中动作；不从“集中”推导一次批准所有内容。
- 实际比较边界及owner/renderer/template/fixture/release输入绑定到B2已存在的accepted checkpoint。

Risk:
- Level: High
- Rationale: 跨parent错源、误批、重放副作用或历史损坏影响正式交付可信性。

Verification Scope:
- Profile: Affected Integration
- Rationale: 要穿过原Human、Native父交付和新聚合消费者，需真实受影响集成及全部关键中断窗。

Required Verification:
- 最早两个parent真实汇总穿过原Native approved/确认/Receipt/Closure/anchor，不能只测renderer；R4既有2行组件probe仅作复用依据。
- News/Mix各一文件；Mix persona/story/conversion逐行style/version准确，Novel/Repurpose来源和semantic分开；零合法行无空文件，partial row集合与目标差额可对账。
- prepared前后、发布后缺Receipt、Set部分完成及completed replay均有fault evidence；重放Task/Receipt/Closure/Ledger计数及已发布字节/时间戳不变。
- 外Business、缺确认、source变更、错误模板/SHA/隐藏OOXML/错误row manifest/孤儿文件必须拒绝；使用原reader判断current与历史有效性，不能放宽校验。
- 既有Native/Publish/anchor/recovery测试与受影响Console/JS路由，新增multi-parent消费者真实harness在最早包建立；集中人审/发布/下载Human E2E。

Asynchronous CI:
- Workflow: None（未选择新异步workflow）
- Blocking for Stage Progression: Not applicable；下列必需验证与Gate仍blocking。

Required Gates:
Self Verification；聚焦原Human/委托与父链恢复的Code Review；Stage Acceptance（正式派生交付与历史证据判断）；Human E2E；A04及每项A05真实人工Gate。

Stop Condition:
G-09两Profile准确交付及零重复/恢复证据成立，所有未决项/差额可见，原历史字节保留；在最小接缝未证实前不扩集合。

## B4 — 逐级容量、真实三端与最终关闭

Goal:
在最终候选组合验证当前Baseline所有AC和保留约束，容量只按实际证据逐级升级。

Authoritative References:
Baseline AC01～10、G08/G13范围；既有仓库验证/生产存储边界；上游I-04和各原Gate。

Deliverables:
- G-08/G-09后2～5→20阶段一→40阶段二→明确有限N稳定期；各级按实际客户/隔离合法事实与资格对账，不假设某客户有10个Novel机会。
- 按全部已确认配置/单类型/组合/零项/部分结束/失败/unknown/重登/集中审核/两份下载/历史运行真实旅程；建议Windows Chromium、Android Chrome、iOS Safari，由责任方约定真实版本/设备。
- 最终完整隔离回归、独立验证/阶段接受与Founder操作；准确关联代码/dirty state、catalog/contract/fixture/release/config、命令、原结果、synthetic model calls/资源峰值与耗时。
- 控制方指派唯一最终证据汇总与关闭责任人，逐AC评估当前证据及需刷新范围，不累加历史PASS代替最终状态。

Non-goals:
不宣称40并发、真实provider限额/费用/质量或生产资格，不为过容量制造事实/资格或换Repurpose，不运行未授权真实模型/4090。

Affected Surface:
最终组合的配置、Native协调/审核/交付、真实浏览器/设备、历史与其他工作树保护。

Architecture Impact:
- None — 本Stage整合证据，不引入新结构；如暴露实现变化则由其实际Owner刷新相应验证/审查。

Review Need:
独立最终证据/Stage Acceptance判断。继承仍适用的前阶段Code Review，改变实现或交互范围交原Reviewer补审，不因最终阶段默认再全量代码审查。

Dependencies:
- B1～B3适用关闭及每一级前一容量证据；真实源/资格不足停止升级并报告缺口，不能静默替换目标。
- Planning/控制方在UAT依赖前指派真实设备/账号角色与验证负责人；未覆盖端保留NOT_VALIDATED。
- 起点是B3实际accepted checkpoint及实际配对环境，不预造未来commit；任何最终修复绑定同一原始阶段边界。
- 生产、4090、真实模型属于独立G-14，当前仍禁止，不是隔离验证自动授予。

Risk:
- Level: Normal
- Rationale: 主要风险是证据错配、容量误报或遗漏最终组合约束，继承各原实现边界风险而不再次发明架构。

Verification Scope:
- Profile: Full Regression
- Rationale: 最终涉及全仓Native/Console/Shared Authority/FRP等整合和全部AC，完整回归是明确的最终关闭要求。

Required Verification:
- 在最终候选执行实际`python tools/verify.py`完整隔离回归；package-only/affected及旧ceac PASS不能代替。观测失败先聚焦修复，再在最终状态重跑要求的完整路由。
- 各级Request/Task/Slot/result、失败/拒绝/unknown/未审/已交付数量独立对账；调用次数含显式重试/unknown，不能以计划数猜实际消耗。
- 真实设备旅程记录版本/设备/权限及source状态；桌面viewport/目标手机图不能签三端UAT。
- 旧Canonical/Approval/Receipt/Closure/Ledger/anchors与保留工作树按起点证据复核；不把旧BL-0“不写Plan”时点结论错误应用到当前实现。
- 20/40容量及synthetic质量只按实际覆盖范围报告；真实成本/限流/模型效果继续UNKNOWN，除非另获授权并取得相应证据。

Asynchronous CI:
- Workflow: None（未选择新异步workflow）
- Blocking for Stage Progression: Not applicable；下列必需验证与Gate仍blocking。

Required Gates:
Self Verification；独立最终验证/Stage Acceptance（全部AC与历史保护需最终组合判断）；Founder Human E2E；blocking完整回归。

Stop Condition:
最终候选的全部当前AC/保留约束有可追溯、适用的证据，无已知blocking回归；缺某级容量/真实端/必须Gate即对应范围未完成。工程完成、Plan/生产审批、部署与真实模型结果分开，不无限等待未经要求的运营观察。

## 9. Acceptance Criteria coverage

AC原文及含义只归Baseline。本表逐字沿用R3已有覆盖关系，不创建或重编号Delivery级AC。AC01～06的首次证明归BL-0历史审计，B4核对其保留和当前消费范围；历史审计不是新Batch通过。

| Criterion | Source | Primary Stage/原证明归属 | Reverification Stage(s) | 复验目的与责任 |
|---|---|---|---|---|
| AC-01 | Baseline AC-01 | BL-0（历史审计） | B4 | 控制/验证Owner核对当前代码、全部必要输入与工作树保护；保留原Checkpoint身份 |
| AC-02 | Baseline AC-02 | BL-0（历史审计） | B4 | 验证Owner保持Current Truth/Target/Proposal区分，继承证据只覆盖其实际状态 |
| AC-03 | Baseline AC-03 | BL-0（历史审计） | B1、B4 | B1保持四层身份与Owner；B4拒绝把通用Mix标签或新配置当成策略支持证明 |
| AC-04 | Baseline AC-04 | BL-0（历史审计） | B2、B3、B4 | Native Request/Ledger/Delivery owners验证新编排、恢复和汇总不混Novel/Repurpose或重复semantic |
| AC-05 | Baseline AC-05 | BL-0（历史审计） | B4 | 验证Owner按2～5/20/40/N及三端真实范围记录结果；真实成本/限流/质量仍UNKNOWN，不扩大证明范围 |
| AC-06 | Baseline AC-06 | BL-0（历史包交付） | B4 | 证据Owner核对原A～H包/Manifest/CRC/SHA仍原样；旧审计“未实施Plan”仅适用于原时点，不借改写旧包适配新开发 |
| AC-07 | Baseline AC-07 | B4 | None（最终组合关闭） | 最终关闭责任人汇总FT体验、原Gate与保留约束在最终候选上的证据；不能仅累加历史PASS |
| AC-08 | Baseline AC-08 | B1 | B2、B3、B4 | Pipeline/Review owners先证明三Style在合法隔离Native路径的规则与可区别性，再验证编排/审核/交付不丢类型；不宣称真实模型质量已通过 |
| AC-09 | Baseline AC-09 | B1 | B4 | Console/Founder验证初始未分配、显式分配、可编辑实际合计；阶段20/40最终操作再次对账 |
| AC-10 | Baseline AC-10 | B2 | B3、B4 | Native owners证明来源/Request/semantic与Presentation计数；Delivery/最终验证Owner对账类型文件及视频/新增语义统计 |

AC07/08/10的当前交付须对应News/Mix两份，准确Style/Native来源/确认与差额；AC04/10须涵盖跨Request排斥及unknown安全。最终关闭责任人按当前组合建立证明，不改写旧包使历史结论看似适用于未来。

## 10. Plan-level stop condition

只有最终候选上全部当前AC及保留约束由适用机器证据、必要独立Code Review/Stage Acceptance、Founder真实操作与blocking完整回归支持，才能形成工程关闭候选。历史结果保留原版本/输入；共享合同或实现变化由其原责任生产者补验/复审。

当前计划交付停止在独立Plan Review前。适用的原生A01/A02资格未新授，A03/A04工程合同范围未批准，Plan Freeze/阶段实施未授权；后续控制必须取得对应真实批准才可执行，不能把Preflight PASS当执行命令或用文档写入模拟审批。Owner拒绝关键合同、早期接缝推翻假设或新输入影响核心条件时，停止受影响依赖并复评，不自动降级A/文件列表。

Git checkpoint资格不等于自动Commit/Push许可。已批准/交付历史不得回滚或删除；旧reader不支持新增版本时停新写入/保留兼容reader，不删新记录迁就回退。unknown保留身份/源与费用范围，不能超时重发或清空。实施完成、release审批、4090/生产部署和真实模型质量各自独立。

## 11. Planning limitations与当前证明范围

- 原生合同技术审查由当前Codex按原Owner入口执行，不等同有权Native人员正式签批；所有新Schema/API/生成策略/批次与multi-parent业务能力仍NOT IMPLEMENTED / NOT VALIDATED。
- R4两Profile各2行renderer/strict validator组件验证在其原范围实际通过，wrong-row被拒绝；没有Request/Task/数据库、Native Approval、模型或Ledger操作，不证明Multi-parent Receipt或20/40生成。新能力的真实接缝由相应最早包建立并验证，命令未存在前不伪造。
- 具体Native版本、预留字段和单调事件、row父链及逐锁责任以原Owner送审差异为准；新版本拒绝未知字段/冲突、原数据不迁移重编码。上线前有未完成尝试时按原owner/code/source fence评估兼容与受控恢复，不默默跨版本重绑；本轮无部署。
- DESIGN_OPTIONS与PRODUCT_DECISION_REGISTER刻意保持R3实际输入字节，使上游设计判定继续适用；R5只细化执行/合同/UI实现资产/验证与导航，不能因文件头编号不同推断产品未同步，也不改写设计判定。
- 新Model真实质量/成本/限流/吞吐与容量20/40未验证。当前News只已有合法资格隔离范围，源不足不是增加并发能解决；生产与真实模型G-14仍未授权。
- 无B1～B4接受/新Checkpoint；代码仍main/ceac加未提交文档。当前实际输入、预检原结果、继承的38份源码/组件证据、本轮8份路由证据、合同候选、旧R4快照和新Manifest在本轮独立证据目录保留。


## 12. 已完成的开工准备与准确放行请求

本节是对既有I-01～04和合同/执行要求的细化，不新增产品规则、AC、正式Stage或业务审批系统。可编辑提案仍归本目录MACHINE_CONTRACT_DELTA_PROPOSAL；机器可读候选、样本、环境和检查结果在本轮独立证据目录，不能被运行代码当Authority导入。

### 合同与资格的先后关系

- B1：C01/C02的版本、三Style规则/消费者及C03配置合同先取得范围决定；再按批准范围实施。真正调用Native生成前，原Pattern/Compatibility/事实/人物及隔离release必须合法，测试能力由B1建立。不能先签新Style运行通过才能允许实现，也不能跳过运行前的真实资格。
- B2：C04～06/A03先批准受限Admission/预留/恢复范围；建议首轮仅2～5逻辑视频、每Business本协调器Dispatch预算1、每Batch最多5待审Native Request。它们是待批的隔离试验约束，不是provider真实限额或已验证容量。其他lane/legacy原约束及共享GPU guard仍存在，不能宣称全局只有1模型调用。20/40前依据实际Request映射、小容量证据再批准确切scope。
- B3：C07/C08/A04先批准原writers委托、逐行父链、补充Receipt和两文件恢复范围；Intent只绑定已知parent/row/template，Prepared才绑定实际output/row-manifest SHA。不得使Intent引用尚未生成的输出SHA形成身份循环。
- A03/A04是工程合同范围决定，沿原模块Owner边界审查，由Founder或其明确授权方批准；它们不是现有可点击的Native Receipt种类，不新建审批服务。A01/A02以及每项A05仍用现有原生认证/独立grant/精确source与writer执行，文档批准不产生这些运行资格。

### UI实现资产（I-04，忠实于已确认语义）

| 区域/状态 | 明确展示与动作 | 服务端和交互边界 |
|---|---|---|
| 客户上下文 | 从客户列表/详情进入独立配置，展示客户、已批Persona/适用Speaker及限制摘要 | 不重复输入已有资料；预检/确认/派发重新验证current权限和source，界面不可修改这些事实 |
| 阶段与组合 | 共用同一数量表；阶段一/二P/S空白待明确分配，News默认Novel，Repurpose显式另选 | 未填不等于0、单项可0、总0不启动；推荐与本次实际目标分列，修改失效旧preview |
| 稳定期 | 显示初始1个四天周期及8×N，确认前要求用户明确确认本次N | 初始值不是授权；无后台无限续期，无未批准比例/时长默认 |
| 开始确认 | 中文列出本次类型/来源/数量、客户/人物、资格限制及“生成后仍需审核” | 一次明确确认只建立有限Intent；相同payload/key双击恢复同一操作，改payload不得重用旧key |
| 进行中 | 原目标/未派发/在途/未知/生成成功/明确失败与差额；待审核/已批准/已交付另列维度 | 统计按稳定Slot和Native证据去重，维度不能直接相加误报完成；Task completed不等于批准 |
| 暂停/结束 | 暂停后续；结束前确认停止未派发、保留成果和未知，显示实际剩余目标 | 已发调用不取消、不超时重发；结束意图与Native结果分开，未全交付不能显示“全部完成” |
| 人审/发布 | 逐项显示准确来源版本和原Native审核动作；Publish稿另行确认 | 修改/拒绝保留Slot和历史；未知/失效不批准，不用一次确认全部内容的捷径 |
| 下载/历史 | News/Mix各最多一份，展示合法视频行数、明确subset及差额 | 零合法行无空文件；事故半集合不能标完整交付；completed replay不造Task/Receipt/Ledger |
| 阻断/过期 | 中文原因＋原生允许的下一步；可只读查看已有成果 | 401/403不静默重发，source/preview失效重新核对；技术码仅诊断，不能露raw JSON/内部字段 |

呈现沿原Productized UI：Mobile<768单列、Tablet768～1023、Desktop≥1024；仅一条主要Mutation Action Bar，保留Bottom Nav offset，避免多重sticky挤占。复用creation-components的Header/Stepper/Summary/State及安全消息，creation-entry-flow只作编排参考，不把它当新Batch writer。现有组件引用已绑定S04/S05 SHA。

配置输入有可见label/说明/错误关联；提交失败保留用户值、聚焦首个错误；异步进度用非侵入状态提示，键盘可达，状态不只靠颜色。结束确认明确受影响数量/未知项。上述为既有状态/无障碍边界的实现细化，不修改产品决策；如实现必须选择新的业务含义，先停止对应依赖并提出具体决定。

布局检查390/430/1440/1792沿原UI冻结，不能代替真实设备UAT。B1先验证Windows桌面真实路径；最终仍覆盖约定的Windows Chromium、Android Chrome、iOS Safari，记录实际版本/设备/角色与完整旅程；手机目前NOT_VALIDATED，不在本轮假填版本或PASS。

### 责任及放行

本轮准备/技术合同作者、源码复核、候选检查与证据汇总由本对话Codex承担，已实际完成。实施工程责任建议继续由本对话Codex承担，只有获得阶段许可后才生效；代码作者的自检不能代替独立审查。Founder（本对话用户）保留产品/合同范围和阶段授权决定；原生业务actor须使用其真实账号/grant。

外部ChatGPT独立Plan Reviewer按Founder已要求的路线对准确R5包裁决；当前没有该结果。B1/B2/B3独立Code Review按已选统一方法在真实候选形成时执行，当前不虚构评审者结果。最终集成/证据整理可由获阶段授权的Codex负责，独立阶段判断与Founder UAT仍分别保留。

本轮环境READY仅表示声明依赖、Python/Node/PowerShell/Git和canonical --list可用；没有跑新功能/全仓suite、模型或服务。开工前材料检查与运行能力验收分开。原Baseline与全部历史包不变；R5输入快照、提案及Manifest可恢复，Stage开始时刷新实际dirty输入边界，不建立新Checkpoint。

唯一外部放行清单见PLAN_REVIEW_CHECKLIST末节：准确R5独立裁决、工程合同范围决定、B1明确许可。A03/A04可一并评审，也可在B2/B3依赖前分别批准；不要求它们阻挡B1。任何肯定选择均须真实来源，不预填批准，不提前修改功能代码。
