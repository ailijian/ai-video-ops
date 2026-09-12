# 《Customer Intake & Persona Onboarding V1｜产品与工程冻结框架》

**Status：Freeze Candidate V0.1 · Pending Approval**
**Scope：首次客户采集 → Fact Extraction → Business/Speaker Persona → Human Approval → Production Readiness**
**Not in Scope：内容生成、Case/Pattern Research、最终视频制作、Performance Learning**

---

# 0. 本文解决什么问题

当前系统的后半段已经逐步标准化：

```text
Approved Persona
↓
Content Intelligence
↓
Novelty / Editorial Quality
↓
Production Profile
↓
Creative Pattern
↓
Script / Micro Beats
↓
Human Review
↓
Excel
```

但真正进入正式代运营后，最前面的：

> **客户资料 → Persona V1**

还不能依赖运营人员每次自行整理，也不能要求客户填写一张巨大、复杂、一次性的人设表。

因此本文件冻结：

> **客户第一次如何进入系统；需要提供什么；AI 可以做什么；什么时候算资料足够；谁有资格说什么；哪些事实可以进入 Production Authority。**

---

# 1. 核心产品原则

正式冻结：

> **Persona 不是一张填写完成的表，而是一个持续版本化的 Customer Truth。**

第一次 Onboarding 只建立：

> **Minimum Viable Customer Truth**

能够安全启动第一轮内容生产即可。

后续：

```text
Persona V1
↓
内容生产
↓
Historical Exposure 增长
↓
Novel Capacity 下降
↓
Content Gap
↓
定向补充采访
↓
Persona V2 / V3
```

因此：

> **首次 Onboarding 与后续 Replenishment 是同一个 Customer Truth 生命周期中的不同阶段。**

---

# 2. 明确拒绝“一次填满的人设大表”

V1 正式拒绝：

> 让客户第一次进入系统时填写几十个必填字段。

原因不是 UX 简化而已，而是 Authority 问题。

当用户不知道答案时，大表会诱导：

* 猜测；
* 泛化；
* 凑答案；
* 把愿望写成事实；
* 把行业常识写成自己真实情况。

因此系统必须允许明确回答：

```text
不知道
不确定
没有
不适用
稍后补充
```

这些状态不得被 AI 自动补全。

---

# 3. 初次 Onboarding 的产品形态

首次采集采用：

> **轻量结构化 Intake + 原始资料输入 + AI 定向追问**

而不是只能“填表”。

V1 应至少支持三种输入方式：

### A. Quick Intake

运营人员或客户回答少量核心问题。

### B. Paste Existing Materials

直接粘贴：

* 客户介绍；
* 访谈纪要；
* 微信整理；
* 门店介绍；
* 现有宣传资料。

### C. Optional Source Materials

允许提供：

* 菜单；
* 价目表；
* 服务说明；
* 官方宣传资料；
* 客户授权评价；
* 其他已有文件。

不同输入最终必须进入同一个：

> **Raw Customer Input Authority**

不能因输入方式不同建立不同 Persona 体系。

---

# 4. 初次 Intake 不是 Production Profile Intake

首次 Persona Onboarding 主要回答：

> 关于这个客户什么是真的？

因此不要求客户先决定：

> 新闻体还是混剪。

`news / mix`

属于 downstream：

> Production Profile Request

不属于 Business Persona Fact。

可以询问运营偏好，但只能作为：

```text
production_preference
```

不能改变 Fact Authority。

---

# 5. 两层 Persona 架构继续冻结

正式保持：

```text
Business Persona
+
Speaker Persona
```

---

# 6. Business Persona 的职责

Business Persona 是：

> **关于企业 / 门店 / 服务本身的唯一事实底座。**

至少可承载：

* Business Identity
* Industry
* Products / Services
* Audience
* Customer Needs
* Customer Use Cases
* Service Process
* Pricing
* Timing
* Differentiators
* Service Boundaries
* Customer Stories
* Business Principles
* Operational Facts
* Forbidden Claims
* Unknown Facts
* Information Requiring Review

同一 Business 的多个 Speaker：

> 引用同一个 Business Persona。

不得复制业务事实形成多份独立真源。

---

# 7. Speaker Persona 的职责

Speaker Persona 只回答：

> **这个“说话的人”是谁，以及他有资格用第一人称说什么。**

V1 正式支持四类 Speaker Overlay：

```text
owner_founder
frontline_expert
brand
generic
```

这四类是 **Authority Template**，不是内容风格模板。

---

# 8. 用户不看到内部 Speaker 类型

用户看到的问题应是：

> **这个账号主要由谁来说话？**

选项：

| 用户选项       | Internal Type      |
| ---------- | ------------------ |
| 老板 / 主理人   | `owner_founder`    |
| 店里的专业人员    | `frontline_expert` |
| 以门店 / 品牌名义 | `brand`            |
| 暂时不突出具体人物  | `generic`          |

不得要求普通用户理解：

> Persona Overlay / Speaker Authority / Frontline Expert

等内部概念。

---

# 9. Speaker Type 决定“应该问什么”

Speaker 选择后，系统必须动态路由问题。

## Owner / Founder

可以重点询问：

* 创立背景；
* 真实经营决策；
* 关键转折；
* 为什么坚持某种做法；
* 本人真实观察；
* 可以公开的经营经验。

不能因为选了老板，就自动生成创业故事。

---

## Frontline Expert

适合询问：

* 实际负责什么；
* 工作中真实看到什么；
* 顾客实际问什么；
* 怎么处理；
* 什么情况需要判断；
* 哪些服务边界；
* 真实一线案例。

不应默认询问：

> 公司战略、融资、租金政策、品牌创立原因。

---

## Brand

适合：

* 官方服务事实；
* 品牌背景；
* 服务原则；
* 业务决定；
* 门店规则；
* 官方可公开数据。

不能伪造个人第一人称经历。

---

## Generic

仅消费：

> Business Persona 已批准事实。

不得生成：

* 创业经历；
* 第一人称现场观察；
* 客户私下评价；
* 未授权个人故事。

---

# 10. 多 Speaker 架构

同一个 Business 可以拥有：

```text
Business Persona
├── Owner Speaker
├── Frontline Speaker
├── Brand Speaker
└── Generic Speaker
```

V1 Onboarding 只要求建立：

> **一个 Primary Speaker**

即可开始生产。

未来可以新增 Speaker Persona。

新增 Speaker：

> 不复制 Business Persona。

---

# 11. 首次 Intake 六个核心模块

V1 初次采集只要求围绕以下六组事实。

## ① 你是谁

至少明确：

* 门店 / 公司名称；
* 行业；
* 核心产品或服务。

---

## ② 你主要服务谁

至少尽可能获得：

* 主要客户；
* 真实使用场景；
* 他们为什么会需要这个服务。

不要求客户提供市场研究。

真实经验即可。

---

## ③ 客户通常遇到什么问题

优先：

* 真正出现过的问题；
* 客户真实问过的问题；
* 客户真实需求。

不得把 AI 推测：

> “你的客户可能担心……”

直接写入 KNOWN。

---

## ④ 你实际上怎么提供服务

优先获得：

* 服务流程；
* 价格；
* 时间；
* 包含什么；
* 不包含什么；
* 个性化能力；
* 服务边界。

这是最重要的生产事实来源之一。

---

## ⑤ 谁来说

明确：

* Speaker；
* Role；
* 实际职责；
* 第一人称允许范围。

---

## ⑥ 有什么不能说

至少询问：

* 明确不能承诺什么；
* 哪些情况不确定；
* 哪些东西需要客户确认；
* 哪些内容不能公开。

这是初次 Onboarding 的正式组成部分。

不是后置审核补丁。

---

# 12. Optional 信息不能成为首次必填

以下信息很有价值，但不能要求第一次必须有：

* Founder Story；
* 顾客故事；
* 顾客原话；
* 商业数据；
* 营业额；
* 复购率；
* Before / After；
* 主厨多年经验；
* 行业观点；
* Proof；
* 品牌历史。

没有就保持：

```text
UNKNOWN
```

后续 Content Gap 会告诉运营什么时候值得补。

---

# 13. Raw Customer Input 是第一 Authority Source

所有用户回答首先只能成为：

```text
raw_customer_input
```

不能直接成为：

```text
KNOWN
```

标准链路：

```text
Raw Customer Input
↓
Fact Extraction
↓
Fact Candidate
↓
Human Review
↓
Persona Revision
↓
Approval
↓
KNOWN
```

AI 无权跳过这条链。

---

# 14. AI 在 Onboarding 中可以做什么

AI 可以：

* 整理答案；
* 提取 Fact Candidate；
* 识别缺失；
* 发现冲突；
* 判断 Speaker Scope 风险；
* 建议追问；
* 将非结构化资料映射到 Persona 字段；
* 生成 Human Review Pack。

AI 不可以：

* 自动补事实；
* 根据行业常识推断客户事实；
* 将营销语言改写成 KNOWN；
* 将客户愿望改写成现实；
* 自动解决冲突；
* 自动批准 Persona。

---

# 15. Fact State 继续使用现有 Authority

事实状态继续保持现有体系：

```text
KNOWN
UNKNOWN
REQUIRES_REVIEW
```

同时约束：

```text
FORBIDDEN
```

继续作为 Claim / Production Constraint。

不要再创建：

```text
LIKELY
PROBABLY_TRUE
AI_INFERRED_FACT
```

这类模糊生产状态。

---

# 16. UNKNOWN 的语义冻结

`UNKNOWN` 表示：

> 当前没有足够 Authority 支持。

它不等于：

* false；
* empty；
* N/A；
* 用户忘记填写。

必须与：

```text
not_applicable
declined_to_answer
not_yet_known
```

在 Raw Input 层可区分。

但进入 Persona Production Authority：

> 都不能当 KNOWN 使用。

---

# 17. REQUIRES_REVIEW

以下典型进入：

```text
REQUIRES_REVIEW
```

例如：

* 客户故事未确认公开权；
* 数据来源主体不清；
* 运营人员转述；
* 两份资料存在冲突；
* Speaker 是否有资格第一人称表达不确定；
* 价格是否仍有效不确定；
* 外部文章中的事实尚未确认适用于当前客户。

不得让 LLM 自行“选一个更合理的”。

---

# 18. Customer Story Authority

顾客故事必须单独处理。

至少区分：

* Story Fact；
* Customer Label；
* Quote；
* Scene；
* Image；
* Video；
* Review / Evaluation。

公开复用必须支持逐项授权。

没有明确：

```text
reuse_authorized
```

不得进入 Production Generation。

---

# 19. Business Fact 与 Speaker Fact 不得串线

例如：

Business Persona：

> 门店提供定期养护。

不意味着 Frontline Speaker 可以说：

> “我设计了这项服务。”

Business Fact：

> 公司决定降租金。

不意味着主厨可以说：

> “我们决定给商户减租。”

Speaker Persona 必须明确：

```text
first_person_allowed_topics
speaker_role_facts
speaker_forbidden_topics
```

---

# 20. AI Follow-up 的职责

Follow-up 不是为了把表填满。

它只能针对：

### Critical Missing Truth

例如：

> 到底提供什么服务？

### Authority Conflict

例如：

> 一份资料说免费，一份说收费。

### Speaker Scope

例如：

> 这个人究竟是不是老板？

### Production-critical Boundary

例如：

> 价格是否固定？

### High-value Content Gap

只有在初次 Intake 已经满足基本事实之后才考虑。

---

# 21. Follow-up 不得重复问已回答内容

系统必须维护：

```text
answered_topics
known_fact_atoms
open_questions
critical_unknowns
```

如果已经有：

> 素菜 8–10 元

不能换成：

> “你们素菜加工一般多少钱？”

再次询问。

---

# 22. Follow-up 的语言要求

优先询问：

> 真实发生过什么？

而不是：

> 你认为客户可能在意什么？

例如：

好：

> “最近有顾客问过哪些问题？”

弱：

> “你的客户通常有哪些顾虑？”

好：

> “有没有一个真实例子？”

弱：

> “你们的核心优势是什么？”

---

# 23. Conflict Handling

如果两个 Raw Sources 冲突：

```text
Source A:
清蒸 15 元

Source B:
清蒸 18 元
```

AI 必须产生：

```text
requires_review
conflict_refs = [A, B]
```

不能：

* 取最新；
* 取平均；
* 自行判断可信度；
* 两个都写进 Production Persona。

Human Review 解决。

---

# 24. Fact Provenance 必须保留

每个 KNOWN Fact 必须能够追溯到：

```text
raw_input_source
raw_answer / source excerpt
source type
confirmed_by
approved_at
persona revision
```

如果来自文件：

记录文件 lineage。

如果来自访谈：

保留 Raw Answer。

不要只有：

> “AI 总结后的一个字段”。

---

# 25. Time-sensitive Fact

价格、服务时间、活动、营业规则等容易变化。

V1 至少支持：

```text
observed_at
confirmed_at
```

以及可选：

```text
freshness_class
```

但：

> 不冻结自动失效天数。

系统不能因为“30天了”自动判 false。

后续可以增加 freshness review policy。

---

# 26. Privacy Boundary

Raw Intake 可能包含：

* 电话；
* 地址；
* 顾客姓名；
* 订单；
* 聊天记录。

因此：

Raw Input
≠
Remote Model Safe Input。

所有远程模型调用继续必须：

```text
Privacy Projection
→ Safe Prompt
→ assert_safe_for_external_model
→ Network
```

不得为了 Persona Extraction 绕开现有 Privacy Authority。

---

# 27. Human Persona Review Pack

Persona Human Review 必须让 Reviewer 不打开原始 JSON 也能判断。

至少展示：

| 内容                | 要求                       |
| ----------------- | ------------------------ |
| Fact              | 抽取出的事实                   |
| Source            | 原始回答 / 摘要                |
| State             | KNOWN Candidate / Review |
| Persona Scope     | Business / Speaker       |
| Speaker Authority | 是否允许第一人称                 |
| Conflict          | 是否存在冲突                   |
| Privacy           | 是否可进入 Production         |
| Risk              | 是否有 Claim 风险             |

同时展示：

```text
UNKNOWN
REQUIRES_REVIEW
FORBIDDEN
```

不能只展示准备批准的好信息。

---

# 28. Human Review 的动作

Human Reviewer 至少可以：

```text
approve
reject
reclassify
request_clarification
```

例如：

AI 抽取：

> “所有菜都可以代炒。”

Reviewer 可以：

```text
reject
```

并保留原 Raw Input。

不得删除历史来源来掩盖错误抽取。

---

# 29. Persona Lifecycle 继续使用现有体系

不要新建：

```text
onboarding_persona
production_persona
persona_profile_v2
```

继续使用现有：

```text
build_persona_v1.py
approve_persona_v1.py
Persona Revision
```

Initial Onboarding 最终创建：

```text
Business Persona Revision 1
Speaker Persona Revision 1
```

后续 Replenishment：

```text
Revision 2
Revision 3
...
```

---

# 30. Persona 不允许静默覆盖

Approved Persona Revision 不可直接改写。

新事实：

```text
Raw Input
→ Fact Review
→ Persona Revision N+1
```

旧 Revision 保留。

---

# 31. Onboarding Readiness 与 Persona Status 分离

不要把“资料够不够”做成新的 Persona lifecycle。

新增 Derived Readiness：

```text
onboarding_readiness
```

建议仅表达：

```text
insufficient
persona_review_ready
production_ready
```

其中：

### insufficient

缺失关键事实。

### persona_review_ready

资料足以做 Human Persona Review。

### production_ready

Business Persona + 必要 Speaker Persona：

> 已 Human Approved。

---

# 32. production_ready 不等于“资料完整”

非常重要。

Persona Production Ready 的含义是：

> **已有足够真实事实支撑安全开始生产。**

不意味着：

* 所有字段填满；
* 可以生产 100 条；
* 拥有所有 Case；
* 有完整顾客故事；
* 有 Performance Data。

---

# 33. Minimum Production Readiness

V1 不冻结精确字段数量。

采用能力组判断。

至少必须具备：

### A. Business Identity

知道：

> 谁提供什么。

---

### B. Customer / Use Context

至少知道：

> 谁在什么场景使用。

---

### C. Production-bearing Facts

至少存在足以形成真实内容的业务事实，例如：

* 服务流程；
* 价格；
* 使用方法；
* 时间；
* 具体服务能力；
* Differentiator；
* Boundary；
* Specific Use Case。

不要求所有类别都有。

---

### D. Speaker Authority

若使用具体 Speaker：

必须明确：

* 身份；
* 职责；
* 第一人称允许范围。

---

### E. Critical Constraints

不存在未解决的关键冲突。

明确的：

* Forbidden Claims；
* Critical Unknown；
* Requires Review。

不能被忽略。

---

# 34. 不使用字段完成率作为 Readiness

正式拒绝：

```text
80% fields complete
→ production_ready
```

因为：

> 30 个没价值字段填满，不等于能生产真实内容。

应该判断：

> **是否形成了足够的 Production-bearing Customer Truth。**

---

# 35. Persona Approved 后计算 Initial Content Capacity

这是 Onboarding 与 Content Quality Engine 的正式交接。

Persona Approved 后：

```text
Content Opportunity
→ Novelty
→ Editorial Quality
→ Capacity
```

计算：

```text
initial_high_quality_content_capacity
```

例如：

```text
requested = 10
capacity = 4
```

应该告诉运营：

> 当前资料只能支撑 4 条高质量内容。

不能因为刚刚完成 Onboarding 就硬凑 10 条。

---

# 36. Initial Capacity 不决定 Persona Approval

即使：

```text
capacity = 3
```

Persona 仍然可以：

```text
production_ready
```

两者含义不同：

> Persona Ready = 可以开始安全生产。

> Content Capacity = 现在有多少值得讲。

不要把它们合并。

---

# 37. 低 Capacity 自动进入补充机制

如果：

```text
initial_high_quality_content_capacity
<
desired_initial_batch
```

系统可以生成：

> **Initial Content Gap Report**

然后：

> 建议补哪些信息。

但不能：

> 阻止 Persona Approval。

---

# 38. Initial Onboarding 与 Replenishment 的关系

冻结成：

```text
Initial Intake
        │
        ▼
Persona V1
        │
        ▼
Production
        │
        ▼
Content Gap
        │
        ▼
Replenishment Intake
        │
        ▼
Persona Revision 2
```

两者输入不同：

### Initial Intake

建立 Customer Truth 基础。

### Replenishment

只问：

> 历史内容没覆盖、当前最缺的事实。

但两者最终都汇入：

```text
Raw Customer Input
→ Fact Extraction
→ Human Review
→ Persona Revision
```

---

# 39. 不建立第二套 Replenishment Persona

已有：

`Content Capacity Replenishment Intake V1`

继续使用。

Customer Onboarding 不应该再建立：

> 第二套 Fact Authority / Persona lifecycle。

两种 Intake 可以有不同 Question Planner，但必须汇入同一 Persona Authority。

---

# 40. Intake Question 与 Persona Schema 解耦

用户不应该看到：

```text
customer_pains
differentiators
service_process
```

这些 Schema Field。

用户应该回答自然问题：

> “顾客一般为什么来找你？”

后台再映射到 Schema。

这是正式 UX 原则。

---

# 41. Intake 允许不完整答案

例如用户回答：

> “差不多十几块吧。”

AI 可以提取：

```text
price_candidate
state = requires_review
```

但不能写：

```text
price = 15
```

系统应该追问：

> “有没有现在正在用的价目表或更准确范围？”

---

# 42. Intake 不做“品牌文案创作”

用户回答：

> “我们比较认真。”

系统不能自动升级成：

> “坚持极致匠心。”

Persona 保存真实事实，不保存 AI 包装后的广告语言作为 Truth。

品牌语气可以以后作为：

> Presentation Preference

不能污染 Customer Truth。

---

# 43. Preference 与 Fact 分离

未来 Intake 可以收：

```text
tone_preference
content_preference
avoid_style
```

但这些必须是：

> **Preference Metadata**

而不是 Business Fact。

例如：

> “不想拍太营销。”

不能变成：

> “品牌坚持不营销。”

---

# 44. 用户首次创建 Persona 的 UX Contract

V1 冻结低保真流程，不冻结视觉。

建议：

```text
① 基本情况
↓
② 客户与服务
↓
③ 谁来讲
↓
④ 服务细节与边界
↓
⑤ AI 整理
↓
⑥ 必要追问
↓
⑦ 确认 Persona
```

不是 30 页问卷。

---

# 45. 第一屏不要叫“创建人设”

对普通本地商家来说：

> “创建 Persona / 人设”

很产品内部化。

用户可见建议：

> **先让我们了解你的生意**

或者：

> **先把你的真实情况告诉我**

具体文案留 UI 阶段，不冻结。

内部仍叫：

> Persona Onboarding。

---

# 46. 人工运营模式与未来自助模式共用 Contract

当前公司代运营阶段：

> 运营人员可以代客户填写 Intake。

未来产品化：

> 客户可以自己填。

两种方式：

> 使用同一个 Raw Customer Input Contract。

必须记录：

```text
input_actor
```

例如：

```text
customer
operator
authorized_business_representative
```

如果只是运营人员自己推测：

> 不能伪装成 Customer Statement。

---

# 47. Operator Observation 不能自动等于 Business Fact

运营人员写：

> “我感觉他们客户主要是年轻人。”

只能成为：

```text
operator_observation
requires_review
```

不能进入：

```text
KNOWN core_audience
```

除非客户或其他 Authority 确认。

---

# 48. External Public Source 规则

Onboarding V1 不默认：

> 自动上网研究客户并写 Persona。

如果未来引入 Public Sources：

必须区分：

```text
customer_confirmed
official_public_source
third_party_source
operator_observation
```

第三方文章里的内容：

> 不应自动成为 Customer KNOWN。

本轮先不扩这个能力。

---

# 49. Initial Intake Artifact

建议新增唯一 canonical：

```text
customer_intake_v1
```

至少包含：

```text
intake_id
business_ref / provisional_business_id

input_actor
input_sources

speaker_selection

raw_answers

attachments / source refs

open_questions

conflicts

intake_readiness

created_at
updated_at
```

它是：

> Raw Input / Intake Authority。

不是：

> Persona。

---

# 50. Intake 不应该保存 AI 生成事实为 Raw Answer

必须区分：

```text
raw_answer
```

和：

```text
extracted_candidate
```

AI 生成的摘要永远不能覆盖：

> 原客户输入。

---

# 51. Suggested Derived Artifact

允许增加：

```text
persona_onboarding_readiness_v1
```

职责只回答：

* 当前缺什么；
* 是否可以 Persona Review；
* 是否存在 Critical Conflict；
* Speaker 是否足够明确。

它是：

> Derived Planning Artifact。

无 Approval Authority。

---

# 52. Artifact Discipline

优先新增：

```text
customer_intake_v1
persona_onboarding_readiness_v1
```

继续复用：

```text
persona_v1
persona_review_pack_v1
approval_receipt
```

不要新建：

```text
business_persona_onboarding_v2
speaker_persona_builder_new
customer_profile_temp
```

---

# 53. 初次 Intake 不应该直接写 Content Ledger

Content Ledger 只记录：

> 内容生产历史。

Onboarding：

> 只能更新 Customer Truth。

不得因为用户在 Intake 中说了一句话，就认为：

> 已经发布过这个内容。

---

# 54. Production Profile Registry 不由 Intake 修改

Persona Intake：

> 不允许注册 Pattern、Case、Profile。

它只产生：

> Customer Truth。

保持层级隔离。

---

# 55. Success Criteria

Customer Intake & Persona Onboarding V1 通过，需要证明：

### 1.

一个新客户可以在：

> 不填写巨大表格的情况下建立 Persona V1。

### 2.

系统能正确建立：

> Business Persona + Speaker Persona。

### 3.

AI 不补未知事实。

### 4.

Role Scope 不串线。

### 5.

UNKNOWN / REQUIRES_REVIEW 被保留。

### 6.

Human Review 能追溯原答案。

### 7.

Approved Persona 不被静默覆盖。

### 8.

资料不足时系统追问，而不是生成。

### 9.

Persona Approved 后能进入 Content Capacity。

### 10.

Capacity 不足时进入 Replenishment，而不是 Padding。

---

# 56. 建议第一批真实验证

实施完成后，不要继续使用林东方做 Initial Onboarding 测试。

因为我们已经知道他的答案，会产生 hindsight bias。

建议测试三组：

### Fixture A：信息充分客户

看系统能否快速进入 Review。

### Fixture B：资料严重不足客户

例如只有：

> “我开了一家宠物店。”

系统应该：

> `insufficient`

而不是自动编客户、痛点和差异化。

### Fixture C：角色冲突客户

例如：

> “账号出镜的是店员”

但输入里大量是：

> 老板创业故事。

系统应该：

> Business Facts 可保留；
> Frontline Speaker 不得第一人称继承。

测试通过后，再拿：

> **下一个真正新客户**

跑 First Real Onboarding。

---

# 57. 不冻结的内容

以下不作为 V1 Frozen Fact：

* 必须几页 UI；
* 必须问几个问题；
* 每轮最多几个 Follow-up；
* 某个具体问题文案；
* Persona 必须多少字段；
* Initial Batch 必须 10 条；
* 使用哪个 LLM；
* Follow-up 是否一次一个；
* 是否语音采访；
* 是否需要 OCR；
* Content Capacity 具体阈值。

这些未来都可以优化。

---

# 58. 正式冻结的内容

如果批准 V1，我建议 Frozen 的只有这些：

### A.

Customer Truth 必须来自可追溯输入。

### B.

Raw Input → Fact Candidate → Human Review → Approved Persona。

### C.

Business Persona 与 Speaker Persona 分离。

### D.

Speaker Authority 决定第一人称边界。

### E.

UNKNOWN 不自动补全。

### F.

REQUIRES_REVIEW 不进入 Production Authority。

### G.

第一次 Onboarding 追求 Minimum Viable Customer Truth，不追求字段填满。

### H.

Persona Readiness 与 Content Capacity 分离。

### I.

Approved Persona 必须 Revision-based，不静默覆盖。

### J.

首次 Intake 与后续 Replenishment 汇入同一个 Persona Authority。

### K.

客户故事必须有独立复用授权。

### L.

运营人员推测不能伪装成客户事实。

### M.

Privacy Gate 继续适用于 Intake / Persona 远程调用。

---

# 59. 明确拒绝的设计

本轮正式拒绝：

1. 一张 50–100 字段的全部必填表。
2. AI 自动把空字段补全。
3. 表格完成率决定 Persona Ready。
4. Business Fact 自动进入任何 Speaker 第一人称。
5. 客户故事没有授权也进入生成。
6. Operator Guess 直接成为 KNOWN。
7. 第三方文章自动成为 KNOWN。
8. Persona Approved 后直接原地修改。
9. Onboarding 建第二套 Persona Schema。
10. Initial Intake 和 Replenishment 使用两套事实 Authority。
11. Content Gap 直接产生新事实。
12. 为第一批数量目标强行让客户回答所有问题。

---

# 60. 推荐工程实施顺序

后续交给 Codex，我建议：

```text
Stage 1
customer_intake_v1 Contract
+
Raw Input / Provenance

Stage 2
Role-aware Initial Question Planner

Stage 3
Fact Candidate Extraction
+
Business / Speaker Scope

Stage 4
Unknown / Review / Conflict Handling

Stage 5
Persona Onboarding Readiness

Stage 6
Human Persona Review Pack

Stage 7
Existing build_persona_v1 /
approve_persona_v1 Integration

Stage 8
Initial Content Capacity Hand-off

Stage 9
Insufficient Capacity
→ Replenishment integration

Stage 10
Fixture Validation
```

最后再跑完整 Regression。

---

# 61. 实施停止条件

如果 Codex发现必须修改以下 Frozen Authority，应该停下来报告：

* Persona lifecycle；
* Privacy Authority；
* Content Ledger semantics；
* Pattern / Case lifecycle；
* Business/Speaker ownership；
* Existing Persona Revision contract。

普通实现细节可以自主决定：

* 文件目录；
* 函数名；
* CLI；
  -缓存；
* Schema 内部组织。

---

# 62. V1 最终产品定义

我会把这套产品能力压缩成一句话：

> **第一次只问够用的真实问题，建立一个可以开始工作的 Persona；以后内容做着做着发现缺什么，再只补什么。**

这比：

> “先帮你创建一个完整人设”

更符合我们现在已经真实验证出来的系统。

---

# 63. 与整个 AI 视频代运营体系的最终关系

到这里，公司的内容生产飞轮可以完整表达为：

```text
首次轻量 Intake
↓
Business + Speaker Persona
↓
第一批内容
↓
Content Ledger
↓
Novelty / Capacity
↓
内容空间不足
↓
Gap-driven Interview
↓
Persona Revision
↓
新的 Content Space
```

与此同时另一条线持续：

```text
Case Acquisition
↓
Cross-case Research
↓
Approved Pattern
↓
Creative Coverage 提升
```

所以：

> **Customer Intake / Replenishment 不断扩大“讲什么”。**

> **Case / Pattern Library 不断扩大“怎么讲”。**

> **Content Intelligence 决定“现在最值得讲什么”。**

> **Production Profile 决定“这次用什么形式讲”。**

这四层现在已经可以形成一个完整、长期可增长的系统。
