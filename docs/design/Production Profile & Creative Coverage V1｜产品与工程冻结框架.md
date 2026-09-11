# 《Production Profile & Creative Coverage V1｜产品与工程冻结框架》

**Status：Approved / Frozen V0.1**
**Scope：Production Profile / Case Library / Pattern Coverage / Creative Matching / Storyboard Contract**
**Not in Scope：新的客户事实采集、Content Novelty 重设计、运营效果学习、最终视频制作**

---

# 0. 本文解决什么问题

当前已经跑通：

```text
Customer Truth
→ Content Intelligence
→ Novelty / Editorial Quality
→ Selected Concept
```

并正式冻结：

> **Content Uniqueness & Editorial Quality V1.0**

现在要解决下一层：

> **一个已经值得讲的 Content Concept，应该以什么视频形态表达？应该借用什么 Pattern、什么 Case、怎样组织画面？**

同时恢复并正式定义原有：

> **新闻体 / 混剪**

在整体架构中的位置。

本文件的核心目标不是增加更多 Case，而是建立：

> **Production Profile × Creative Pattern × Case Coverage**

让以后每增加一个案例，都明确是在增加什么创意能力，而不是单纯增加案例数量。

---

# 1. 总体架构冻结

正式采用以下分层：

```text
CUSTOMER TRUTH
Business Persona
Speaker Persona
Facts / Stories / Observations / Boundaries
        │
        ▼
CONTENT INTELLIGENCE
Opportunity
Historical Exposure
Novelty
Editorial Quality
Capacity
        │
        ▼
SELECTED CONTENT CONCEPT
“现在最值得讲什么”
        │
        ▼
PRODUCTION PROFILE
News / Mix
“这次要做成什么视频形态”
        │
        ▼
CREATIVE INTELLIGENCE
Compatible Pattern
Compatible Case
Opening Strategy
Narrative Structure
Visual Structure
Storyboard
        │
        ▼
PROFILE-SPECIFIC OUTPUT CONTRACT
News Excel / Mix Excel
```

长期原则：

> **Content Layer 决定讲什么。**
> **Production Profile 决定做成什么宏观视频形态。**
> **Pattern / Case / Storyboard 决定具体怎么讲。**

三者不得混淆。

---

# 2. Production Profile 正式成为一等公民

V1 正式支持两个 Production Profile：

```text
news
mix
```

它们不是标签，而是：

> **一套完整的生产形态合同。**

一个 Profile 至少决定：

* 内容承载形式
* Script Schema
* Storyboard 宏观结构
* Case eligibility
* Pattern compatibility
* Generator behavior
* Validation rules
* Excel Export Contract

---

# 3. News Profile 定义

正式定义：

> **News = 短、快、信息密度高，以连续信息节拍 / 文本表达为主要语义承载的生产形态。**

当前业务实现基线：

```text
新闻体视频制作文案导入.xlsx
```

当前 downstream contract：

```text
标题1
标题2
标题3
标题4
标题5
标题6
```

当前业务偏好：

> 单条约 6–8 秒，标题/信息节拍短而清晰。

但注意：

**“必须6格”“每格必须≤8字”“必须6–8秒”不冻结为长期产品事实。**

它们属于：

> **news profile 当前 implementation contract / configurable constraint**

未来下游视频系统变更，可以通过 Profile Contract Version 升级，而不改变 News 作为 Production Profile 的本质。

News 的核心语义是：

> **micro-information beats**

而不是：

> “Mix 的缩短版”。

---

# 4. Mix Profile 定义

正式定义：

> **Mix = 以口播 / Narration 为主要语义主线，由人物、过程、服务、产品、场景等真实视觉素材承接的生产形态。**

当前正式 downstream contract：

```text
视频制作标题
视频制作口播内容
```

Mix 当前已经验证：

```text
Business Persona
+
Speaker Persona
+
Content Quality
+
Approved Pattern
+
Approved Cases
→ Script
→ Human Review
→ Excel Export
```

因此当前：

> **Mix = Production Capable**

但 Creative Coverage 仍然较窄。

---

# 5. Hybrid 的地位

V1 **不新增第三个正式 Production Profile**。

允许 Case Source Classification：

```text
news
mix
hybrid
uncertain
```

但生成侧 V1 最终必须 resolve 成：

```text
target_profile = news
```

或：

```text
target_profile = mix
```

`hybrid` 只是：

> **源案例具有混合结构特征**

不是新的 Excel Contract，也不是新的 Generation Pipeline。

以后真实业务需要时，可以另行决定是否建立 Hybrid Profile。

本轮不做。

---

# 6. 上传 Case 时，“新闻体 / 混剪”选择继续保留

这是正式冻结决策。

运营人员上传案例时继续回答：

> **“这个案例主要属于哪种视频形式？”**

用户可见选项：

| 选项  | 简单说明                  |
| --- | --------------------- |
| 新闻体 | 短、快，以连续文字 / 信息节拍为主    |
| 混剪  | 以口播 / 旁白为语义主线，由真实画面承接 |
| 混合型 | 两种特征都比较明显             |
| 不确定 | 交给系统分析                |

但运营人员选择只产生：

```text
operator_profile_hint
```

它不是最终 Authority。

---

# 7. Case Profile Authority

每个 Case 最终需要区分三个概念：

```text
operator_profile_hint
observed_source_profile
compatible_generation_profiles
```

例如：

```text
operator_profile_hint = news

observed_source_profile = hybrid

compatible_generation_profiles = [
  news
]
```

或者：

```text
operator_profile_hint = mix

observed_source_profile = mix

compatible_generation_profiles = [
  mix
]
```

最终 Matching 使用：

> **compatible_generation_profiles**

而不是：

> operator_profile_hint。

---

# 8. Profile 判断必须来自结构证据

系统不得仅凭：

* 文件名
* 上传人员标签
* 时长
* 是否有人说话

直接确定 compatibility。

应综合已有证据：

```text
Transcript
Visual Evidence
On-screen Text
Storyboard
Shot Structure
Narration Structure
Fingerprint
```

系统判断回答的是：

> **这个 Case 的创意结构是否可以作为某个 Production Profile 的参考。**

而不是：

> “这个视频表面上看起来像什么”。

---

# 9. Case Library 保持统一

正式拒绝：

```text
/news_cases/
/mix_cases/
```

这种物理隔离式架构。

保留一个 Canonical Case Library：

```text
Case
├── Source Evidence
├── Privacy Projection
├── Narration
├── Visual Structure
├── Storyboard
├── Fingerprint
├── Profile Metadata
├── Pattern References
└── Lifecycle
```

UI 可以：

> 按 News / Mix 筛选。

底层仍然是一套 Case Authority。

---

# 10. Production Profile 不能重置 Content Novelty

这是本文件最重要的冻结规则之一。

`production_profile` 属于：

> **Presentation Identity**

而不是：

> **Semantic Content Identity**

因此：

```text
Mix:
“素菜加工费通常8–10元”
```

如果已经正式发布，

下一条：

```text
News:
“代炒多少钱？”
“素菜8-10元”
```

不能被 Content Quality Engine 认为：

> 新信息。

所以：

```text
production_profile
```

进入：

> **Presentation Signature**

不得进入：

> Semantic Novelty Reset。

---

# 11. Content Ledger 跨 Profile

同一个 Business：

```text
news
mix
```

共享：

> **Historical Semantic Exposure**

不能建立：

```text
news_history
mix_history
```

两个互相不知道的内容历史。

Content Ledger 条目允许记录：

```text
production_profile
```

用于：

> 表达历史分析。

但 Semantic Novelty：

> **Business-wide**

跨 Profile 生效。

---

# 12. 允许显式 Cross-profile Repurpose

这里不能简单规定：

> “News 说过，Mix 永远不能再说。”

现实运营中有时确实需要：

> 同一重要信息，用不同 Production Profile 再传播。

因此 V1 允许未来显式模式：

```text
reuse_intent = cross_profile_repurpose
```

但必须明确：

> **这是旧信息的再次表达，不是 Novel Content。**

它：

* 不计入 Novel Capacity
* 不伪装成新 Content Concept
* 应能追溯原 Historical Exposure
* 可单独进入运营 Campaign

默认 Production Request：

```text
reuse_intent = novel_content
```

本轮不需要立即实现复杂 Repurpose Workflow，但这个边界正式冻结。

---

# 13. Pattern 与 Profile 的关系

Production Profile 不是 Pattern。

Pattern 是：

> **某种可复用的创意组织结构。**

例如当前已批准：

```text
pcv1_narration_led_process_projection
```

它表达：

> Narration 为主要语义主线，真实业务 / 服务 / 过程画面作为视觉投影。

它天然与 Mix 高度兼容。

但不能因为：

> Pattern 已 Approved

就自动认为：

> 它也适用于 News。

---

# 14. Pattern Approval 必须 Profile-scoped

一个 Pattern 可以：

```text
compatible_profiles = [mix]
```

未来也可能：

```text
compatible_profiles = [news, mix]
```

但兼容性必须经过证据与 Review。

正式规则：

> **Pattern 在 Mix 下 Approved，不意味着 News 下 Approved。**

跨 Profile Compatibility 必须显式确认。

---

# 15. Pattern Lifecycle 保持现有 Authority

本框架不重新设计现有：

```text
Fingerprint
Pattern Hypothesis
Pattern Candidate
Approved Pattern
```

生命周期。

现有阈值和 Human Review 机制继续有效。

本文件只增加：

> **Profile Compatibility**

不建立第二套 Pattern Lifecycle。

---

# 16. Case 不是 Pattern

继续冻结：

> **Case = Evidence。**

> **Pattern = 从多个 Approved Case 中提炼出的可复用结构。**

不能因为某个 Case 表现好：

> 直接把 Case 当 Pattern。

也不能因为多个 Case 重复：

> 声称 Pattern 有效果。

Performance Authority 仍然独立。

---

# 17. Creative Coverage 正式定义

Case Library 以后不再主要回答：

> “我们有多少 Case？”

而应该回答：

> **“我们覆盖了多少种 Creative Capability？”**

因此建立：

# Creative Coverage Matrix

基本关系：

```text
Production Profile
        ↓
Creative Pattern
        ↓
Approved Cases
        ↓
Creative Capability Coverage
```

---

# 18. Creative Capability Coverage 的维度

V1 冻结“必须评估这些类别”，但不冻结具体 taxonomy。

至少观察：

### Opening / Hook

例如：

* 问题
* 数字
* 冲突
* 场景
* 人物
* 结果
* 反差

---

### Narrative Progression

例如：

* 问题 → 回答
* 过程 → 结果
* 故事 → 观点
* 误解 → 纠正
* 事件 → 解释
* FAQ
* POV

---

### Visual Projection

例如：

* 人物
* 过程
* 产品
* 场景
* 顾客
* 文本
* Proof
* Before / After

---

### Speaker Mode

例如：

* Owner
* Frontline Expert
* Brand
* Customer
* Narrator

---

### Trust / Proof Structure

例如：

* Process only
* Customer Feedback
* Numeric Fact
* Real Result
* Before / After
* Document / Dashboard

仍然遵守：

> **Process ≠ Proof。**

---

### Closing / CTA

例如：

* 无 CTA
* 信息收口
* 问题收口
* 行动 CTA
* 评论互动

---

### Content Job Compatibility

Pattern / Case 能否自然承载：

* service explanation
* customer story
* pricing
* process
* boundary
* trust
* conversion
* FAQ

Content Job 仍来自 Content Layer。

这里只记录：

> Creative Structure 是否适配。

---

# 19. Coverage 不是数量分数

例如：

```text
20 个几乎一样的
老板口播 + 干活画面
```

不能认为：

> Coverage 很高。

应该视为：

> Case Quantity 高
> Creative Coverage 低。

因此新 Case 的价值取决于：

> **它增加了什么新的结构能力。**

---

# 20. Case Acquisition 的目标改变

以后收集 Case 不再以：

> “多找几个爆款”

为目标。

而以：

> **填 Creative Coverage Gap**

为目标。

每一个新 Case 在收集前最好对应：

```text
target_profile
coverage_gap
desired_new_capability
```

例如：

```text
profile = mix
gap = customer_story_structure
```

或：

```text
profile = news
gap = number_led_local_service_flash
```

具体 Pattern 名称不能提前硬造。

只是定义：

> 我们为什么需要这个 Case。

---

# 21. Case Acquisition Priority

V1 可以产生：

```text
case_acquisition_priority
```

优先级来自：

* Profile 是否当前没有 Production Coverage
* 是否补新的 Pattern Hypothesis
* 是否补新的 Hook Structure
* 是否补新的 Visual Grammar
* 是否补新的 Speaker Mode
* 是否补新的 Proof Structure
* 是否高度重复已有 Case

具体权重：

> configurable。

不要冻结。

---

# 22. Profile Readiness 与 Creative Coverage 必须分开

一个 Profile 应有两个维度。

### Operational Readiness

回答：

> 能不能安全地投入 Production？

例如：

```text
not_ready
research_ready
production_ready
```

---

### Creative Coverage

回答：

> Creative 表达能力丰富到什么程度？

例如概念上：

```text
none
narrow
developing
broad
```

具体阈值不冻结。

---

# 23. 当前真实状态冻结

基于目前已经验证的 Production Foundation：

### Mix

```text
Operational Readiness:
production_ready

Creative Coverage:
narrow
```

原因：

* 已有 Approved Pattern
* 已有 Approved Cases
* 已有 Generator
* 已完成真实客户生产
* 已完成 Human Review
* 已完成 Excel Export

但：

> Approved Pattern Coverage 仍然只有一个主要结构。

所以不能自称：

> Creative Coverage 已成熟。

---

### News

当前：

```text
Operational Readiness:
research_coverage_insufficient
```

已存在：

* downstream Excel contract
* 原业务需求
* source collection capability

但没有：

> Approved News Pattern Coverage。

所以仍然禁止正式 Generation Fallback。

---

# 24. News 不允许 fallback 到 Mix

正式拒绝：

```text
target_profile = news
```

但系统因为缺 News Pattern：

> 偷偷用 Mix Pattern。

正确行为：

```text
research_coverage_insufficient
```

并输出：

> 缺少什么 News Creative Coverage。

---

# 25. Generation Request 必须显式带 Profile

正式 Production Request：

```text
target_profile = news
```

或：

```text
target_profile = mix
```

不能在最终 Generator 阶段仍然 unresolved。

未来可以支持：

```text
profile_preference = auto
```

但在进入 Generator 前必须 resolve。

V1 不需要实现 auto。

---

# 26. Profile 与 Content Planning 的顺序

默认推荐：

```text
Content Intelligence
→ Selected Concept
→ Profile
→ Creative Matching
```

因为：

> 先确定值得讲什么，再确定怎么表达。

但如果运营计划预先要求：

```text
target_profile = news
```

那么 Content Planning 必须把：

> Profile Compatibility

作为约束。

例如：

> 一个需要 30 秒人物故事才能成立的 Concept，不应硬塞成 6 秒 News。

---

# 27. Content Concept 增加 Profile Compatibility

Selected Concept 可以有：

```text
profile_compatibility = {
  news: ...
  mix: ...
}
```

回答：

> 这个 Concept 是否适合这种宏观表达形态。

它不是 Novelty 判断。

它属于：

> Creative Planning。

---

# 28. Matching 正式变成 Profile-aware

现有：

```text
match_generation_sources_v1.py
```

继续使用。

不要建立第二套 matcher。

它以后必须检查：

```text
target_profile
+
approved pattern compatibility
+
approved case compatibility
+
contract compatibility
```

Case Eligibility：

> 使用 `compatible_generation_profiles`

不得使用：

> operator hint。

---

# 29. Matching 不决定内容主题

继续冻结：

> Case / Pattern 不允许反向改变 Selected Content Concept。

Matching 只能回答：

> “这个已经选好的内容，可以借什么结构来讲？”

不能回答：

> “这个 Case 讲了什么，所以当前客户也来讲什么。”

Case-specific Facts 继续禁止转移。

---

# 30. Profile-specific Creative Contract

每个 Production Profile 应拥有自己的 Creative Contract。

至少定义：

```text
script_shape
storyboard_shape
case_eligibility
pattern_eligibility
validation
export_contract
```

---

# 31. News Creative Contract V1

News 至少需要支持：

```text
Micro Beat Sequence
```

每一个 Beat 需要有：

* semantic role
* text
* visual anchor
* order
* duration guidance（configurable）
* evidence / authority lineage

最终：

> 多 Beat 组成一个极短信息单元。

不要强迫 News 使用：

> narration-led many-to-many storyboard。

---

# 32. Mix Creative Contract V1

Mix 继续保持：

```text
Title
Narration
Visual Anchor
Hero Shot
Supporting Shot Roles
Audio ↔ Visual Mapping
```

现有：

> Narration Track / Visual Track separation

继续保持。

Mix 不要求：

> 每句话都由画面字面重复。

视觉可：

> reinforce / supplement / contextualize。

---

# 33. Profile-specific Creative Quality

Content Quality 继续跨 Profile 共用：

* Novelty
* Material Information Gain
* Audience Relevance
* Customer Specificity
* Authority

Creative Quality 必须 Profile-aware。

News 未来应重点评估：

* Beat clarity
* information density
* first-beat hook
* text readability
* progression
* visual support
* semantic completeness

Mix 重点评估：

* Narration quality
* natural voice
* speaker fit
* narrative progression
* visual projection
* storyboard diversity
* shot support
* single-focus

具体评分权重：

> 不冻结。

---

# 34. Storyboard 必须 Profile-aware

不能只有统一：

```text
storyboard_v1
```

然后所有 Profile 都套同一种结构。

可以共享底层 Artifact，但必须存在：

```text
profile = news | mix
```

并遵守不同 Storyboard Contract。

---

# 35. News Storyboard 核心

News Storyboard 更偏：

```text
Beat 1
Hook

Beat 2
Context

Beat 3
Specific Information

...

Beat N
Payoff / Close
```

每个 Beat 可对应：

> Visual State / Text State。

重点不是完整 Narration Mapping。

---

# 36. Mix Storyboard 核心

Mix 继续支持：

```text
Narration Segment
↔
One or More Visual Shots
```

保留：

> many-to-many。

同时增加：

```text
hero_shot
supporting_shot_roles
avoid_recent_visual_anchor
```

用于视觉差异。

---

# 37. Storyboard Diversity 不得制造 Semantic Novelty

即使：

> 分镜完全不同，

如果 Content Semantic 已讲过：

> 仍然是旧信息。

Creative Diversity 不允许反向重置 Content Novelty。

---

# 38. Profile-specific Export Contract

当前正式：

### News

当前 downstream implementation baseline：

```text
标题1 ... 标题6
```

---

### Mix

当前：

```text
视频制作标题
视频制作口播内容
```

保持。

不要创建一个通用 Excel：

```text
profile
title
narration
beat1
...
```

去替代下游已经稳定的生产合同。

内部统一，外部仍然 Profile-specific。

---

# 39. Production Profile Versioning

每个 Profile 应版本化，例如：

```text
news@1.x
mix@1.x
```

版本变化原则：

小的配置变化：

> 不要求大版本变化。

若改变：

* Script Shape
* Storyboard Contract
* Export Contract
* Compatibility Semantics

则需要 Profile Contract Revision。

具体 SemVer 策略可以由工程确定。

---

# 40. Profile × Pattern × Case Coverage Report

建立一个正式 Creative Coverage Report。

建议：

```text
creative_coverage_report_v1
```

它回答：

### Profile

现在有哪些 Profile？

### Pattern

每个 Profile：

> 有哪些 Approved Pattern？

### Cases

每个 Pattern：

> 有哪些 Approved Evidence Cases？

### Creative Capabilities

覆盖了：

* Hook
* Narrative
* Visual
* Speaker
* Trust / Proof
* CTA
* Content Jobs

哪些能力？

### Gaps

还缺什么？

---

# 41. Creative Coverage Report 不是 Authority

Coverage Report 是：

> Derived Planning Artifact。

它不能：

* 自动批准 Pattern
* 自动批准 Case
* 声称 Pattern 有效果
* 修改 Profile compatibility

它只负责：

> 告诉运营 / Research 下一步应该找什么 Case。

---

# 42. Case Library 扩充后的飞轮

以后：

```text
Coverage Report
↓
发现 Creative Gap
↓
定向找 Case
↓
Case Analysis
↓
Human Case Approval
↓
Fingerprint
↓
Cross-case Research
↓
Pattern Hypothesis / Candidate
↓
Pattern Approval
↓
Coverage Report 更新
```

这是公司 Case Library 正确的增长方式。

---

# 43. 当前下一步 Case Research 优先级

按照当前状态，我建议：

## Priority 1：建立 News 最小 Production Coverage

原因：

> Mix 已 production_ready。

而 News：

> 仍然是 research_coverage_insufficient。

所以新增 Case 的第一优先级应该是：

> **收集真正具有 News 结构的案例。**

按照现有 Pattern 生命周期：

> 需要足够多个 Approved Cases 才能建立 Pattern Candidate。

不建议拿一个 News Case 就直接写 Pattern。

---

# 44. News Case 收集不要只找同一种视频

第一批 News Case 应刻意具有结构差异。

例如可以覆盖：

* 数字 / 价格驱动
* 本地新鲜事 / 服务发现
* 问题 / 提醒
* 场景反差
* 事件
* 具体利益点

这里只是研究方向。

不要提前把它们写成 Frozen Pattern。

真正 Pattern 必须从 Case Evidence 中产生。

---

# 45. Mix Case Research 同时继续，但按 Gap 收

Mix 下一阶段不应该继续大量收：

> “Narration + 干活画面”

因为这个已经有 Coverage。

应优先寻找当前明显不足的结构能力，例如：

* Customer Story 主导
* Frontline POV
* Proof / Result 主导
* Misconception Correction
* Strong Question / FAQ
* Conversion / CTA
* 人物情节驱动

具体哪些最终成为 Pattern，仍由 Research 决定。

---

# 46. Case Intake UI 冻结建议

未来运营端上传 Case：

```text
上传视频 / 链接

这个案例主要属于哪种视频形式？

○ 新闻体
○ 混剪
○ 混合型
○ 不确定
```

然后可选：

```text
为什么觉得值得收？
```

例如自由文本：

> 开头很抓人
> 顾客故事很好
> 画面很强
> 转化感好

这些只能作为：

```text
operator_notes
```

不是 Pattern Authority。

不要要求运营人员选：

> Narrative Pattern / Shot Grammar / Proof Structure

那是系统分析职责。

---

# 47. 明确拒绝的设计

本轮正式拒绝：

1. 取消“新闻体 / 混剪”选择。
2. 把 News / Mix 降成普通 Case Tag。
3. 把 Case Library 物理分成两个互不相通的库。
4. Operator 选择直接成为 Canonical Profile。
5. Mix Pattern 自动兼容 News。
6. News 缺 Pattern 时 fallback 到 Mix。
7. 不同 Profile 各维护一套 Semantic Ledger。
8. 换 Profile 后把旧信息当新内容。
9. Case 数量直接等于 Creative Coverage。
10. 多个相似 Case 自动证明 Pattern 有效果。
11. Hybrid 在 V1 直接成为第三个正式输出 Profile。
12. Profile 反向允许 Case Fact 转移。
13. 为统一内部架构破坏现有 Excel Contract。

---

# 48. 当前系统责任边界

冻结成：

### Customer Truth

回答：

> 关于这个客户，什么是真的？

---

### Content Intelligence

回答：

> 现在还有什么新的、有价值的东西值得讲？

---

### Production Profile

回答：

> 这次要做成什么宏观视频形态？

---

### Creative Pattern

回答：

> 这种 Profile 下，内容可以用什么可复用结构组织？

---

### Case

回答：

> 这种结构有什么真实 Evidence？

---

### Storyboard

回答：

> 这一条具体内容最终怎么落到镜头与信息节拍？

---

### Export Contract

回答：

> 下游系统具体接收什么字段？

这六层不得相互越权。

---

# 49. 工程 Artifact Discipline

V1 推荐尽量只新增：

```text
production_profile_registry_v1
creative_coverage_report_v1
```

现有 Case Artifact：

> 扩展 Profile Metadata。

现有 Pattern：

> 增加 profile compatibility。

现有 Generation Source Plan：

> 增加 target profile compatibility validation。

现有 Content Ledger：

> 增加 production profile presentation metadata。

现有 Storyboard：

> 增加 profile-aware contract。

不要再创建平行：

```text
news_case_v2
mix_case_new
profile_matcher_alt
news_generation_new
```

等影子体系。

---

# 50. Production Profile Registry

建议 canonical registry 至少记录：

```text
profile_id
profile_version
status

script_contract
storyboard_contract
export_contract

case_compatibility_policy
pattern_compatibility_policy

validation_policy
```

当前至少注册：

```text
news
mix
```

Hybrid 不注册为 V1 Production Target。

---

# 51. Current Truth Backfill

实施时先不要收新 Case。

第一步应对现有：

> 三个 Approved Case

做 Profile Compatibility Backfill。

不要假设：

> 现有 3 Case = mix only。

应该重新基于结构证据判断：

```text
observed_source_profile
compatible_generation_profiles
```

但：

> 未经 Human Review 不升级 Canonical Case Compatibility。

---

# 52. Current Coverage Baseline

然后建立第一次：

```text
creative_coverage_report_v1
```

应明确显示：

### Mix

* Production Ready
* Approved Pattern：1
* Approved compatible Cases：当前实际数量
* Creative Coverage：narrow
* 已覆盖能力
* 缺失能力

### News

* Production Not Ready
* Research Coverage Insufficient
* Approved News Patterns：0
* Compatible Cases：按重新审计结果
* Missing Research Targets

---

# 53. Acceptance Criteria

这份框架进入实施后，我要求至少满足：

### Profile

* News / Mix 均成为正式 registry entry。
* Hybrid / uncertain 只存在 source classification。

### Upload

* operator hint 保留。
* operator hint 不具有 canonical authority。

### Case

* Case 保存 observed source profile。
* Case 保存 compatible generation profiles。
* Matching 不读取 operator hint 做最终判断。

### Pattern

* Pattern compatibility profile-scoped。
* Mix approval 不自动扩张到 News。

### Novelty

* Ledger 跨 Profile。
* Profile change 不重置 novelty。

### Generation

* Request 明确 target profile。
* Source plan 只能选择 target-compatible Pattern / Case。

### News

* 没有 Approved News Pattern 时继续：
  `research_coverage_insufficient`
* 不 fallback。

### Mix

* 现有真实 Production Flow 必须保持兼容。

### Export

* News / Mix 各自保持 downstream contract。

### Coverage

* 可以明确回答：
  “下一批 Case 应该找什么，而不是找多少个。”

---

# 54. 本轮不做什么

这轮不要：

* 收集新 Case
* 设计 News Pattern
* 生成人工 News Pattern
* 重新训练 Content Quality
* 新增 Persona Fact
* 做新客户
* 接 Performance Data
* 改 Excel 模板
* 做最终视频生成
* 做复杂 Case UI

先把：

> **Profile / Pattern / Case / Coverage**

关系冻结并映射进现有工程。

---

# 55. 推荐实施顺序

我建议后续 Codex 按这个顺序推进：

```text
Stage 1
Production Profile Registry
+
Current Contract Backfill

Stage 2
Existing Case Profile Compatibility Audit

Stage 3
Existing Pattern Profile Compatibility

Stage 4
Profile-aware Source Matching

Stage 5
Cross-profile Ledger / Novelty validation

Stage 6
Creative Coverage Report

Stage 7
News / Mix current-state baseline

Stage 8
Case Acquisition Gap Plan
```

做到这里先停。

**不要马上开始大量抓 Case。**

我们先看：

> Creative Coverage Report 到底认为 News 缺什么、Mix 缺什么。

再启动定向 Case Research。

---

# 56. 最终冻结判断

这套框架最核心的长期结构可以压缩成一句话：

> **Customer Truth 决定有什么可讲，Content Intelligence 决定现在什么值得讲，Production Profile 决定做成什么形态，Pattern 与 Case 决定怎么讲，Storyboard 决定具体怎么落地。**

其中：

> **新闻体 / 混剪继续保留，而且地位比之前更清楚了。**

过去它们更像：

> “运营人员给 Case 打的两个标签”。

现在它们正式成为：

> **贯穿 Generation Request → Case Matching → Pattern Compatibility → Storyboard → Export 的 Production Profile Contract。**

而运营人员上传案例时原来的：

> **新闻体 / 混剪选择也继续保留。**

只是从“决定真相”降级成：

> **`operator_profile_hint`**

这是我认为目前最稳健、也最不容易未来走偏的架构。
