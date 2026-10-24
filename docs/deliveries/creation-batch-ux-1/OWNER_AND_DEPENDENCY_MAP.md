# Original Owner、源码审查与依赖 — R5

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


## 原Owner保持唯一

Business/Speaker事实、Case/Pattern、Compatibility/Release、Request、Human、Publish、Export/Closure/Ledger的完整当前关系仍归 [原Native图](AUTHORITY_AND_SOURCE_GRAPH.md) 与 [Authority Map](../../operations/AUTHORITY_MAP_V1.md)，本轮不改其Current Truth。下面是本agent沿原组件Owner边界的只读源码审查，不是代替原有权人员批准新合同。

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


## 原Owner可行性审查结果（CODE_PROVEN事实与PROPOSED结论分开）

| Finding | 原Owner / 精确证据 | 已证明现状 | 本次候选与真实批准状态 |
|---|---|---|---|
| OR-01 | Request：generation_request_handoff_v1._active_in_flight_request_exists:279；create_generation_request_handoff:744；NR01/02/04 | 同Business/profile现有active拒绝，Business锁与相同key恢复；无Batch scope例外 | C04新增原Owner受限Admission，legacy保持；A03 NOT_NATIVE_APPROVED，不能删check |
| OR-02 | Quality/Novel机会：novel_news_opportunity_v1.project_novel_news_opportunities:83；NR05；content_quality原Owner | 仅Approved事实＋原Ledger投影，当前price_offer_led隔离范围，不含未审机会唯一预留 | C05同语义排斥与单机会占用、各源当前资格，2独立合法机会才能试2待审News；无实际客户容量数据，不承诺Novel10 |
| OR-03 | Native generation/recovery：resolve_generation_batch_v1.augment_and_validate_batch:775、novel_news_generation_recovery_v1.snapshot、publish_copy_v1._current:278；NR07/08/10/12 | 概念/历史memory绑定，未完成尝试whole-Ledger fence；未知dispatch不能按无输出重发 | C04～06需审phase/预留/并发及外部Ledger变动，本文方案未被真实接缝验证；A03/G-04 OPEN |
| OR-04 | Mix Review：review_generation_batch_v2.review_generation_batch_v2:543；NR09 | 准确source content IDs、人审/修订/拒绝，已有合法partial subset | C02/C04将同Style K与稳定Slot精确关联，修订只追加版本。三Style参数当前不成立（NR02），产品定义批准不等于实现 |
| OR-05 | Novel export/Quality：novel_news_v1.export_novel_news:620；close_generation_export_v1.close_generation_export:408；NR17/18 | 导出前再验novelty/Business、原Ledger追加与冲突判断；不凭Request创建消费semantic | C05不能另建账本，C08只读合法parent链/delta0；多未审时序需原Owner正式确认，不能假设所有历史reader都支持 |
| OR-06 | Publish/Delivery：publish_copy_v1.prepare:217、confirm:387；creation_delivery_v1.export:134、validate_completed:79；NR11/13～16 | source/draft独立确认、singleRequest prepared/exclusive publication/Receipt/Completion及历史验证 | C07复用原人审；C08扩多parent/两Profile文件，由原writers委托，A04 NOT_NATIVE_APPROVED；原文件复制拼接不够 |
| OR-07 | Task/worker：BackgroundTaskRunner._reconcile_business_state:187；NR20/21 | 两执行lane各1worker；部分Native unknown会被reconciler明确阻断，不代表所有规划阶段已安全覆盖 | 候选dispatch预算需跨相关入口真实约束，不把每lane1误写成现有全局只会1个模型调用；C06缺覆盖即停 |
| OR-08 | Admission数量：generation_request_handoff_v1.validate_confirmation:470；content_creation_entry_v1.build_content_creation_entry:466；NR03/06 | requested/confirmed整数1～20；Novel selected opportunity要求1视频；容量不足缩量/阻断 | 新Style/Profile的K必须逐项由原Owner批准/验证；Batch20/40 UNKNOWN / NOT_VALIDATED |

以上证据均由实际源码字节、函数def行和摘录SHA绑定在新包 `evidence/NATIVE_SOURCE_EVIDENCE.json`。NR25另证明旧equivalent-active匹配没有新batch/style/Slot维度，C04必须一并审核，不能只删除active拒绝。完整source链接可从原图和exact Checkpoint取得，未声称“原Owner已正式签字”。本轮没有人审权限授予、Pattern批准、资格release、生成或运行数据改写。

## 不可行时的准确升级

- F-ACTIVE：当前legacy active合同确实阻断候选B；只有原Owner批准新scope/context、预留、memory和正式人审/来源限制后才可实现。若多待审会使原memory/review/export合同无法保持，报告失败source/反例及范围给ChatGPT/Founder，不能自动退回A。
- F-SOURCE：合法独立Novel机会不足时是来源容量阻断，不是增加并发可解决的问题。2～5隔离试验须有原Owner认可、符合原合同的合成事实/资格fixture，仅供隔离测试，不构成客户事实或生产资格；不能改真实客户资料、反复用同一机会或把Repurpose算新增。
- F-MIX：当前没有可独立传递的三Style正式身份、转换CTA策略或新K验证。需C01/C02和合法Pattern/Compatibility，不能用原mixed/none充当正式三类型。
- F-EXPORT：当前Owner only-singleRequest，缺multi-parent授权/Set完整性reader；由C08/A04解决或给出明确机器阻断，产品仍是两份汇总，禁止文件列表降级。

## 依赖及最终责任

Baseline与原Design PASS→R4实际输入Planning Preflight PASS及继承的Native合同技术审查→R5独立Plan Review/Freeze与明确阶段许可。对应工程范围批准先于其依赖实现：B1的I-01合同→原资格齐备后的单Request，B2的A03→小容量多待审，B3的A04→两文件；再B4逐级验证与最终候选。当前所有实现箭头未执行，不能把本轮预检解释为上述审批已完成。

Console协调器只拥有draft/intent/Slot及操作协调，不拥有生成、Approval、Export或Ledger真相；SQLite仅投影。新模块名/落盘schema/版本仍候选。原Owner负责其生产入口和严格reader兼容；集成/最终证据由控制方在实施前指派唯一汇总责任人，实际Reviewer和有权控制者也须明确，不伪造具体审批姓名。

Stage开始时保存原始比较边界、staged/unstaged/untracked内容、实际合同/fixture/release/环境与可恢复输入；之后修复不移动该边界。只有适用验证/Gate通过后才有资格形成accepted checkpoint，Commit/Push及继续权限仍由当次用户授权。

历史Canonical、Approval、Receipt、Closure、Delivery effective chain、Ledger anchor与其他工作树成果保持原身份；权限/源/资格变化阻断新写入，旧记录按原version reader验证。不得为恢复补造旧snapshot，也不得把媒体Case研究升级为客户事实/使用权/Proof。

## 本轮设计交接与剩余责任

DR-01/02产品决定已有当前用户明确答复；P06/P07/P08/P10不再待Founder选择。原Request/Quality A03须证明安全范围、来源预留与未决调用影响，既保护fence，也让原Gate允许的合法成果继续审核/交付；原Export/Delivery A04仍须正式委托与严格父链/恢复验证。这些是原Owner工程/Authority义务，不是新增设计决定或已签Native批准。具体浏览器/组件/状态及无障碍证据由Planning指定责任人，在依赖实现或验收前闭合。

## R3 Preflight后的分层交接

当前R5通过R4生产者适用性记录消费原R3 Design PASS与I-01～04，不修改其实质设计输入。NCR-01～08完成技术审查，精确来源见新证据目录NATIVE_CONTRACT_SOURCE_EVIDENCE；继承R4的38份摘录只证明当前源码，原2行renderer只证明已有组件投影/校验，本轮另有S01～08路由证据。

原Request/Quality及Export/Delivery的唯一Owner和最低版本差异已确定，故Planning Architecture Impact为Material；R3把“未正式签A03/A04”直接写成整个架构Unresolved过宽。技术审查不代签：审批仍是依赖实现前的真实条件。缺批准、早期接缝失败或来源不足时停依赖并报告；不能提前把能力写成Current Truth。

| 上游义务 | 承接位置 | 关闭证据与时点 |
|---|---|---|
| I-01 Style/Native资格 | B1-P1，C01/C02 | 原Owner版本合同及适用Pattern/Compatibility/release审批，依赖生成前；随后真实单Request成功/拒绝及reader兼容 |
| I-02 Admission/预留/恢复 | B2-P1/P2，C04～06 | A03受限scope/锁责任/来源和Human限制正式批准，依赖实现前；随后2～5真实接缝与故障、调用数/来源排斥 |
| I-03 原Owner两文件交付 | B3-P1/P2，C07/C08 | A04委托/父链及恢复版本批准，依赖实现前；随后两parent/全部关键中断窗及completed replay零重复 |
| I-04 UI/真实设备 | B1/B3依赖UI前细化，B4真实旅程 | Planning/控制方指定设计/前端与UAT责任人；按已确认语义补响应式/无障碍/状态和真实版本设备，不增加未批产品规则 |

当前代码始终main/ceac，相关未提交仅文档；没有接受的实现Stage。控制方在执行前指定唯一集成/最终证据责任人、真实Reviewer及有权审批方，未来checkpoint只能在事实发生后记录。原原生签批权、Session/CSRF和共享客户范围不改变。


## R5已落实的准备责任及外部决定

| 责任 | 本轮可归属承担者 | 当前事实与边界 |
|---|---|---|
| 准备、技术合同细化、源码审查、候选和环境检查、证据整理 | 本对话Codex | 已实际执行；仅作者/技术复核，不签独立PASS或业务Approval |
| 后续实现、自检、集成/最终证据整理 | 建议由本对话Codex在明确阶段授权后承担 | 当前是开工分工提案；不因准备指令启动B1，不自动Commit |
| 产品、工程合同范围、Plan冻结与阶段许可 | Founder/本对话用户，或其明确授权方 | 决定仍待实际作出；A03/A04沿原模块Owner边界审查，不要求寻找不存在的机器审批按钮 |
| 独立Plan Review | Founder要求的外部ChatGPT独立审查路线 | 送审准确R5包，当前无新裁决；当前作者不能充当独立批准者 |
| 独立实现Code Review/阶段判断 | 控制方在真实候选形成时按统一方法安排的独立Reviewer | 代码作者自检不能代替；角色/实际执行身份和结果在对应Gate真实记录，不虚构未来姓名 |
| Native Pattern/Compatibility/内容/Publish批准 | 原生系统中实际获grant的actor与原writer | 不从Founder文档批准推断账号权限；不修改真实客户或写试验Approval模拟已获资格 |
| Founder操作验收/真实移动设备 | Founder提供实际使用方/设备；获授权Codex组织并留证 | 最早薄切片及最终旅程的阶段义务，设备版本未知不填PASS |

开工入口只需其阶段适用的准备和许可。B1先C01/C02工程决定及配置细化，原A01/A02在实际生成前；A03在B2实现前，A04在B3实现前。运行test/release资格只能在真实合法fixture/代码路径形成后验证，不设“先通过尚不存在的新能力才允许开发”的循环。

本轮已定位S01～08的原Native消费者、可复用UI组件和现有隔离测试入口，环境检查支持开发工具可用。现有handoff fake_authorities单测只是局部测试，不当作新Style或完整Native资格证据；B1必须建立不stub原Gate的真实最薄路径。旧客户/Persona、Compatibility grant/release和Approval保持不变。
