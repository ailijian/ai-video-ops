# Native Machine Contract Delta Proposal — R5

Delivery: CREATION_BATCH_UX_1
Plan Revision: 5（开工准备细化；工程范围与原生资格均不代签）
Status: Draft / Pending Independent Review / Plan Freeze Not Authorized / Implementation Not Authorized
Baseline: Revision 1 / Approved / Frozen
Baseline SHA-256: 13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3
Previous independently reviewed PLAN SHA-256: fb845c980df7feb15e81e543a5bbcb5543ee917a8c82f0bdda6212e7c58c4a1c
Prior Preflight input Plan R3 SHA-256: 8d7e82a3abf9e0eb1b5bfb993192640062fddedab641695df7524651f928ddf7
Input Plan R4 SHA-256: f9cea03c7c160f586d8d3dda24515ca5400763056f4388b5c17931bf3b439e8e
Prior delivered Plan R2 SHA-256: 2a7081e10340cdb680d72f96e59f3357924529e29546ad233c6bf218ed4f5dbb
Historical R2 working-input SHA-256: 0fd6aeff228cfc5f90a8e09ac175fb4c47a261319de6c63bd2037767d26765cd

依据：[唯一Baseline](BASELINE.md)、[真实批准链BR-02](BASELINE_APPROVAL_RECORD.md)、[独立Plan裁决来源](PLAN_INDEPENDENT_REVIEW_RECORD.md)。已批准产品规则（含已确认DR-01/02）、当前机器事实与待批Native合同分开记录。所有新增Schema/API/状态均为PROPOSED / NOT IMPLEMENTED；本轮不写功能代码或Native业务Receipt。


## 合同登记与事实边界

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


C01～08只是提案代号，未创建任何Schema、API、数据库迁移或运行Authority记录。名称/版本须原Owner做strict reader覆盖和冲突检查，不把现有v1.0强塞新字段。R4源码审查证据见继承包evidence/NATIVE_SOURCE_EVIDENCE.json的NR01～25，源码SHA与真实函数/行号逐项可核；静态审查不是原Native Human审批。

## C01 — Versioned Style Catalog

候选creative-style-catalog-v1.0：稳定style_id、version、definition SHA、D-P01产品来源、production_profile、允许事实/人物/结构/禁止主张/CTA、适用Pattern/Compatibility scope。新Style可版本化扩展，不永久硬编码四种全部能力。产品规则批准不批准Catalog机器格式、Pattern或release；旧内容不追溯贴标签，不覆盖已绑定版本。目标时长可空且仅建议，没有新数值承诺。

## C02 — Mix请求、分组与修订身份

候选mix-style-intent-v1.0及原Owner审核的新generation-request版本。当前NR02固定content_intent=mixed、cta_intent=none，NR03只证明数量1～20输入有效，不证明三Style支持。新Style/CTA与对应Profile/Pattern/release需原消费者实际识别验证。

无环身份：Catalog＋确认Batch Intent→Style intent（预定Native Request ID，不引用尚不存在的Request SHA）→Native Request SHA→Source/Content Plan→逐Slot与final Concept绑定→content→原Human/修订/Approved→Publish→Delivery。绑定事件引用已存在两端，不回写旧Intent互相hash。

一个同Style子组含K个逻辑视频Slot；每Slot有稳定logical_slot_id、style/version、Native request_id、final concept_id/ref、effective batch_ref及content_id。真实K须原Owner批准新Style/profile的数量范围与容量；旧1～20不自动继承为新资格。数量关系为目标K、合法生成G、审核通过A、实际交付D，满足D≤A≤G≤K；不足部分保留精确差额，不重排剩余结果占位。

NR08验证concept_ref属于final选择及semantic/source匹配；NR09用content_id审核，允许部分通过/拒绝。新Slot合同必须在修订前后保持逻辑Slot和source content identity；title/narration改变产生原Native允许的Approved版本和新的SHA，映射事件追加新version，不改旧content、Review或Receipt。超出原意图的重作只能经明确的新attempt/操作合法绑定，旧映射保留，不能靠完成顺序或标题相似度收养结果。

首个试验只需2～5视频：同Style K=2的原Mix Request，再逐步加入独立Style/News组合。它是未来合法隔离路径，不是本轮已运行试验；新Style没有Pattern/CTA资格时停在G-03，不用通用Mix填三类。

## C03 — 有限配置与Batch Intent

候选creation-batch-config/intent-v1.0。草稿revision/hash与确认后的immutable intent分开；单Business，服务端Batch/Slot ID，当前actor/permission，stage/free模式、推荐/实际类型量、News来源分项、明确N、Speaker及当前Persona/限制/资格refs、可空时长建议和确认范围。修改失效旧preview；已绑定Native历史不变。

数量非负整数、未填不等于0；人设/故事初始未分配必须明确分配。总0阻断、初始N=1仍需明确确认、以及部分结束行为已按已确认DR-01/02取得产品确认；本候选机器合同必须忠实消费这些规则，原Owner版本/安全审批仍未完成。不能把点开始当全部内容批准、自动循环或平台发布许可。Batch只拥有配置/协调，SQLite仅执行与读投影。

## C04 — 候选B的Native受限Admission与稳定Slot

候选native-batch-admission-v1.0＋creation-batch-slot-binding/operation-v1.0，由原generation_request_handoff Owner验证，不在Console加skip/force参数。现有NR01/02 active检查保留于legacy/非本batch路径。例外必须绑定exact batch_intent、Business/Profile、actor当前权限、Style/source refs、原Owner授权上下文、scope版本、pending上限和dispatch预算/epoch；值由原Owner审查，不能用queue20或目标40推出上限。

仅在已批准A03的确切Batch scope内，前一Request有可信本地生成终态、仍待Human时，才可逐次admit下一项。多个待审不是并发调用授权；默认逐次Dispatch是候选调度约束，原单进程/GPU guard仍成立。其他Batch、legacy活动Request、跨Business、失效/revoked资格或不明执行结果不继承例外。

Admission必须在原Business/Request/Quality约束下完成资格复核与来源预留，并持久化可恢复intent→Native Request→binding；跨文件不宣称原子事务。先短锁持久协调意图，释放后原Gateway获取其原锁；返回短CAS补绑定，不持新Batch锁跨网络。崩溃重放相同server key＋exact payload，验证原结果再补缺项，不能造新key/Task。

NR25当前equivalent-active查找只含既有Business/Speaker/Profile/数量/opportunity维度，不含新batch/style/Slot scope。新Native版本必须同时收紧等价恢复与Admission：exact batch/style版本、ordered Slots、来源及操作意图都匹配才可恢复；相同数量的另一Style/Batch不能被收养为当前子组。仅在active拒绝处加例外而不修正等价恢复不成立，legacy路径保持旧语义。

生成未审、审核拒绝、部分批准各自是Native证据投影；协调器不得改Native lifecycle为终态来释放active。新待审许可的正式人审与来源限制见A03，缺批准即不执行。撤回使新Admission/Dispatch/Review/Export按原Owner fail closed；不能用已确认Batch绕过current source/Pattern/Compatibility/release校验。

## C05 — 原Quality Owner的机会唯一预留与memory边界

候选content-intent-reservation-v1.0，属原Content Quality/Native Ledger Owner协调伴随记录，绝非第二Ledger。唯一占用Key须包含Business、Native reuse/source kind、原semantic/Fact/CIU身份及原Owner等价判据；opportunity显示ID、Slot ID或文本标题不能独立代替语义排斥。跨Batch/Profile也核对已communicated及有效预留，Novel同机会不分给两Request；Repurpose保留原semantic source、只影响原Presentation规则。

预留绑定Native/Slot/operation、source和memory epoch、lease/fencing、parent及生命周期。NR05当前机会投影只读原Ledger，没有未审预留，故B目前不能直接运行。新增记录不得给Console分配语义Truth权；模型prompt的pending来源排斥也由原Quality消费者验证。

原Owner送审时序：在当前有效memory下逐次生成并积累待审，相关内容先由原Native Human核对，再由原writers逐项交付。Novel待审state会比较generation memory，而Human bundle/已完成draft与交付按各原reader验证；不能先导出A、再假定旧memory的待审B仍可直接审核。未完成Publish尝试仍保留whole-Ledger fence。外部Ledger变化阻断受影响open attempts并走原显式恢复；原门允许的其他合法成果继续。没有新增全局epoch Authority/跨文件事务前提，不能以UI结束解除fence。其他合法操作改变whole-Ledger时，已有未完成intent原memory fence仍生效，停下并按原协议处理，不能重绑或自动重发。NR17的导出前novelty与原Ledger追加校验仍保留。A03/G-04须审查各入口的预留/guard和原锁责任；“phase/epoch”只是协调范围的候选标识，不新增Ledger Authority或强制全局barrier，不宣称未建的reader已兼容。

每个已发attempt pin准确memory SHA及其预留身份，后续新增预留不能通过随意改旧intent逃过fence；预留校验不能仅用会随他项变化的全局head强行使已完成结果失效。合法未dispatch取消可释放；已dispatch未知不能超时释放后再分配/重发；晚到worker按原epoch/fence归原Request，不能跨Slot采用。审核拒绝/部分结束的释放须原Owner确认已无未知副作用且未曝光；已approved未export继续占用，closure合法消费一次。

## C06 — 每provider阶段的原恢复协议

规划、Mix生成、Novel、Publish分别列原Owner intent/dispatch/response/result/Task证据与当前actor/source/memory；已有REC-01/C3-05复用，缺覆盖则停在blocked/unknown，lease过期或无输出不证明未调用。协调阶段标识仅可为原Owner受限上下文的additive证据，不修改旧intent/receipt或发明全局事务。

未知外部结果不自动重发、不换key或释放机会；保存response仅本地恢复；晚到旧worker不能替换新head。C3-05仅原initial zero-output合法范围，不能扩成质量拒绝/partial/已Human后的自动再生成。显式有权retry仍新operation＋parent和原费用/范围确认。批次暂停阻止新admission/dispatch，不撤回已发；本轮确认的结束意图只停止未派发工作，保留成果/在途/未知与差额；不撤回已发调用，不抹成completed。原Gate允许的合法成果仍可审核与交付。

## C07 — 集中核对与Publish确认

候选creation-batch-review-command-v1.0只协调准确Native kind/request/content/Beat/Slot、source version/SHA、每项decision、当前actor/permission、expected head及stable operation。调用原Mix Review V2、Novel review、Repurpose approve和原receipts；多Request部分成功不是事务，恢复只补原未提交项。修订后exact映射追加，拒绝保留差额，不能悄悄另取来源补满。

Publish继续从各自准确Native Approved产生title/body/topics与News制作短标题，≤5 targets/call，不挪用制作稿Approval确认发布字段。集中确认也逐Request绑定exact draft_ref；source/权限/事实失效即阻断。生成/审核/已交付等批次计数只读Native，不保存第二approved权威。

## C08 — 原Export/Delivery Owner内的两份Multi-parent汇总

候选creation-composite-delivery-{intent,prepared,receipt,completion}-v1.0由原Mix/Novel/Repurpose export writers明确委托现有creation_delivery_v1；当前NR14～16是singleRequest，不能直接宣称支持。正式输出最多News.xlsx与Mix.xlsx；Mix同一文件包含三Style，News同一文件包含Novel/Repurpose。该组实际合法行数为0不出无意义文件；不复制拼接旧XLSX冒充新正式交付。

可信输入域只包含同Business、原Owner验证通过的Native Approved、当前适用Human/Publish confirmation、原Delivery Receipt/Completion、Closure及authentic Mix history anchor。每行绑定logical Slot、binding/attempt、style/version、Native request/content/concept、原approval、exact draft/confirmation、parent Delivery row/receipt/completion、Closure/anchor和source语义。部分交付Scope是用户可见的明确subset，显示目标差额、被排除项及原因，不能把未批准/未知行纳入正式导出。

Template维持Mix5列/News4列，header row4/data row5、一个视频一行，不新增Style列、不把News的Beats拆多视频。准确Style/reuse身份由文件组和不可变row manifest对每行编号绑定，其SHA纳入独立Supplemental Receipt。Mix模板SHA `75edbcca01a03c49750c2184d74bfe1edb4ab086d299dd5b7f50f350b246cab0`，News模板SHA `5f33e04db8cc35cb70578830b8cfd4a01267f36ffadce19a4b2e48f08cd54d84`。

新Set Intent绑定已知ordered parents、row scopes、template SHA、expected parent/effective head和actor；渲染完成后的Prepared再绑定output与row-manifest SHA，Intent不引用尚不存在的输出；用原严格OOXML renderer/validator渲染，不把父文件存在当Proof。原核心未闭合只能由原writer完成一次，汇总不能给其补造Closure或Ledger anchor。

每文件Prepared→独占原子发布→Receipt均按原机制验证；两个文件的集合不是跨文件原子事务。Set Completion仅在所有非空预期文件及其Receipt完整匹配后成立，崩溃只恢复缺失一致步骤；一个文件已发另一个缺失时不能冒充完整集合，也不回滚或覆盖前者。明确partial delivery要有其自身合法scope/intent，不能把事故中间态自动命名为部分成功。

独立Supplemental Delivery Receipt记录实际XLSX/manifest SHA、所有parent/行来源、模板、actor、prepared/completion与预期head；所有semantic/exposure/presentation delta均0，不建立第二业务Closure。completed replay复用原operation/Task/文件/Receipt，不再render、建Task、更新时间或Ledger。Source/permission/revocation和历史有效性分别用原reader判断，不能用当前Ledger伪造历史snapshot。

## 独立Native批准点与不可行处置

| Authority | 原审批范围 | 本轮真实状态 |
|---|---|---|
| A01/A02 | Style相关Pattern支持scope、Compatibility与release/activation | 现有原Owner保留，新范围未批准，Stage不授权 |
| A03 | 候选B的admission例外、pending/dispatch边界、机会预留与memory/phase、正式人审/来源限制 | 技术差异/反例已明确；正式批准仍NOT_NATIVE_APPROVED |
| A04 | 原Export/Delivery writers的multi-parent委托、Receipt/严格两文件验证与恢复 | 原Owner及renderer路线已核查，NOT_NATIVE_APPROVED；不能另造Exporter |
| A05 | 每项真实内容Human决定及Publish draft确认 | 必须由实际有权人按原Native scope执行，本轮无此业务操作 |

若原Owner证明B或C08在某合同、来源容量或资源条件下不能安全运行，列出准确source/反例/影响范围和最小替代供ChatGPT/Founder裁决。A、文件列表、放松事实/资格或提升并发均不是默认fallback。当前未验证20/40，真实限流/成本/吞吐/质量均UNKNOWN / NOT_VALIDATED。

## 本轮原生合同技术审查与最小可审字段（均非已实现Schema）

继承R4的NCR-01～08原始报告与38份源码摘录见[技术审查](../../../.local/evidence/creation-batch-ux1-planning-preflight-r3-20261022/evidence/NATIVE_CONTRACT_REVIEW.md)，本轮逐项核对当前源SHA未变。当前Codex是技术审查者，不代替原有权审批人。A01/A02、A03、A04的名称是已有Plan审批点代号，不是本轮签发的新Native业务Receipt。

| 合同 | 最小送审字段/责任 | 必须拒绝与恢复条件 |
|---|---|---|
| C01/C02 | 原Mix Catalog id/version/definition SHA、适用Pattern/Compatibility/release refs、Style intent、approved Business/Speaker/source、ordered logical Slots；新版本Request/handoff/plan/content/Human/Export读写一致 | mixed/primary_angle不等于Style；未知版本/越权CTA或人物拒绝；旧记录不追溯贴标签，K须新版本实际范围 |
| C04 | exact Batch intent ref、Business/Profile、Style ref、ordered Slots、server operation key/payload digest、原actor/permission和source refs；预定Native ID只引用ID，不与尚未存在的SHA成环 | admission与equivalent查找都验证同一身份；Native Request已写但binding未写时按原key找准同一结果补绑定，不能收养同数量的其他Batch/Style；Task仍原Owner |
| C05 | 原Quality协调记录：Business、原semantic/CIU/Fact身份与版本、owner Native intent/Request/Slot、source refs、attempt/lease/fence、单调事件与释放/消费证据 | 未审来源只预留，不标Strong Memory/communicated；相关跨Profile/legacy入口均检查。已派发未知不因TTL/结束释放，安全释放需原Native证据；最终仅原closure消费Ledger一次 |
| C06/C07 | 原各provider阶段证据＋exact Native human operation/source/version/decision/actor；生成/人审/导出阶段只是投影与受限上下文 | 不跨网络持新锁；Windows父持原business锁时child不重入同锁。旧abandon存在真实Human/Authority前提，不循环调用来实现Batch结束。已存在Native决定由原reader验证后恢复协调结果，不再写第二Approval |
| C08 | ordered same-Business parent Receipt/Completion/Closure/Anchor refs、每Slot与content/style/source/approved/draft confirmation对应、profile/template SHA、stable row order/row manifest SHA、每文件Prepared/output SHA、Set完整性与operation key/actor | 只在原三writers委托的creation_delivery版本内实现；原parent未闭合由原writer完成一次；跨Business/缺确认/错row/hash/半集合拒绝。已完成重放复用原Task/Receipt/输出，semantic/exposure/presentation delta0 |

锁不代表跨文件事务。短协调提交→释放协调锁→原Gateway/child按既有锁责任执行→短CAS补回结果；跨文件中断按同key/预期parent补缺失步骤。Console SQLite不保存第二业务批准/语义Truth。功能启用前须所有适用guard/strict reader一致，旧reader未知版本不默默降级；有未完成旧尝试时保留原fence与显式恢复，不能升级时重绑。

R4曾运行已有Excel renderer两Profile各2行组件验证及错误预期行拒绝，本轮仅继承其准确输入范围：没有Business Authority/Approval/Request/Task、模型或Ledger写入。新reservation/Style/multi-parent业务路径仍须在获对应批准与执行许可后建立最早真实接缝，测试证据不能由本报告替代。20/40及真实模型仍NOT_VALIDATED。


## 开工前精确候选与送审范围（R5）

[八项合同字段候选](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/proposals/NATIVE_CONTRACT_CANDIDATES.json) SHA-256：`840206fa672860cb823e049ebb3028f94154e685f697ba33dedcfcb8a2cae79f`。[三Style正反样本](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/proposals/STYLE_ACCEPTANCE_SAMPLES.json)只说明规则，无客户事实或真实模型效果。[A03/A04范围表](../../../.local/evidence/creation-batch-ux1-prestart-r5-20261022/proposals/ADMISSION_AND_DELIVERY_REVIEW_SCOPE.json)含待批隔离边界。

候选根对象是review carrier，contracts内使用根$defs，不是八份已注册的运行Schema。当前只检查JSON/字段/引用完整性，未安装新validator，不宣称通过完整JSON Schema或Native验证。名称、字段与strict reader版本须有权方批准后由原机器Owner发布；现有generation-request-v1.0保持原读法，新Style需要明确新版本/伴随合同，不能让旧reader忽略新增字段。

| Style | 必要来源/人物 | 目标结构与拒绝依据 |
|---|---|---|
| persona | 已批本人观点或亲历事实及适用Speaker；第一人称依据精确可归属 | 问题/判断→本人依据→相关结论；拒绝虚构资历、情绪/经历或代表所有人发言 |
| story | 有来源的真实事件及叙述实际用到的人物/时间/经过/结果 | 背景→真实过程/选择→有来源结果；缺项不补编，参考Case事实不得移植 |
| conversion | 已批服务价值/适用需求和合法CTA scope；需出镜时沿用Speaker Gate | 需求→合法服务价值/边界→允许行动；拒绝效果保证、虚假稀缺/优惠或未授权CTA |

C01的structure/required_fact_roles/cta_policy必须由C02传至source/content plan、生成prompt/validator、Human/修订及Export消费者；单Style意图有exact catalog version/SHA，不以primary_angle/narrative_mode或展示label代替。正反样本是未来测试判据，本轮不生产内容。allowed_quantities由新scope实际批准，不能自动把旧1～20赋给三Style。

| 字段组 | 正常关系 | 必须拒绝/恢复 |
|---|---|---|
| Identity | 预分配Native ID→有SHA的Native Request→追加Slot/Concept/content binding；引用仅指已存在对象 | same key不同payload、跨Business/Style/Batch或缺完整source不收养；admission已写但binding缺失仅恢复原结果 |
| Reservation | 原Quality semantic等价键、source/memory、owner Request/attempt/fence及追加事件 | 有dispatch未知时TTL/结束不释放；审核拒绝也须证据确认无未知副作用；仅原closure消费一次 |
| Phase/locks | 原各provider步骤证据及当前actor；短协调提交→释放→原Gateway/child→短CAS | 不跨network持新Batch锁，Windows child不重入父持business锁；外部Ledger变化不重绑open attempt |
| Delivery | Intent已知输入→Prepared真实output/row-manifest SHA→原独占发布/Receipt→Set completion | 不对未来输出做hash环；任一parent/确认/anchor不足拒绝；事故半集合不冒充完整；completed replay零新Task/Receipt/Ledger |

建议A03首轮2～5逻辑视频、每Business本协调器Dispatch预算1、每Batch最多5待审Native Request，仅供隔离范围审查。该数值未获批准、不代表现有两lane全局并发或provider限额；20/40前原Owner按实际映射/已验证证据重新给确切bounded scope。A04只在原三writers委托内，全部semantic/exposure/presentation delta0。A03/A04工程决定不生成机器Approval Receipt；A01/A02和A05真实资格/人审仍用现有writer与grant。

当前工程合同候选已齐备可送审，批准仍PENDING_HUMAN_DECISION；B1只消费其C01～03及适用资格，C04～06留给B2、C07/08留给B3。没有因本次细化改变任何Current Truth或激活正式能力。

C07候选将内容Review和Publish确认拆为互斥scope：后者必须绑定exact draft_ref并使用原confirm动作，不把approve/revise沿用为发布确认。C08候选含Intent/Prepared/Receipt/Completion四种不同版本结构；文件数最多2，profile唯一性、逐行源及零delta仍由原Owner语义验证。Native News的Mix StyleRef可为null，业务类型/Novel或Repurpose身份单独保留；Mix必须有精确StyleRef。它们都是送审字段，非可直接导入运行的Schema。
