# 《Content Uniqueness & Editorial Quality V1｜产品与工程冻结框架》

**Status：Freeze Candidate V0.1 · Pending Approval**

> **Lifecycle：Historical Freeze Candidate / Superseded.** 当前 Content Uniqueness Authority 为 [CONTENT_UNIQUENESS_EDITORIAL_QUALITY_V1.md](../content_quality/CONTENT_UNIQUENESS_EDITORIAL_QUALITY_V1.md)；系统运行入口见 [Operations RUNBOOK](../operations/RUNBOOK.md)。本文保留为历史诊断与设计证据，不是当前 RUNBOOK。

## 一、B0 优化前基线正式冻结

这一轮优化不得修改现有真实客户 Approved Batch，而是把它作为对照组。

| Baseline           | 值                                       |
| ------------------ | --------------------------------------- |
| Request            | `real_shufang_mix_001`                  |
| Source Revision    | `revision_0005`                         |
| Source Batch SHA   | `446a1b07...622a98`                     |
| Approved Batch SHA | `a3ccc689...23c5a`                      |
| Excel SHA          | `1c64d2f4...54a910`                     |
| Scripts            | 10                                      |
| Speaker            | 林东方 / frontline_expert                  |
| Approved Pattern   | `pcv1_narration_led_process_projection` |
| Eligible Cases     | 固定现有 3 Case                             |
| Output             | 10 条正式 Excel 内容                         |

这个 Baseline 后面只能**分析，不能回写**。

建议实施时额外生成一个只读：

`baseline_content_quality_v1.json`

它根据旧 Approved Batch 反向计算 Content Signature、事实使用次数、内容聚类等指标，但不得改变原 Batch SHA。

我用最终 Excel 做了一个简单字面检查，标题+口播标准化后的最大 SequenceMatcher 相似度约 **0.435**。也就是说，传统 lexical duplicate 已经不严重；真正的问题确实已经进入了**语义重复和内容体验重复**层面。

---

# 二、V1 最核心的冻结决策

以后不能再把：

> `Angle + 一组 Persona Facts`

直接理解成“一条新内容”。

一条内容是否真正新，要由它的 **Semantic Content Identity** 决定。

冻结原则是：

> **改变 Speaker、Hook、措辞、Case、镜头顺序，都不能把同一个 Central Claim 变成一条新内容。**

例如：

林东方说：

> 素菜代炒通常 8–10 元。

品牌号说：

> 想知道素菜代炒多少钱？通常 8–10 元。

虽然 Speaker、Hook 都不同，但如果目标用户问题、事实组合、核心结论都一样，系统必须认为：

> **同一内容语义。**

所以你提出的 **角色 ID 去重是必要的，但它只能成为 Content Signature 的一个字段，不能成为“换角色即可解锁重复内容”的机制。**

---

# 三、Content Signature V1

每条候选内容增加两套 Signature。

### Semantic Signature——决定“是不是同一件事”

| Field                 | 作用            |
| --------------------- | ------------- |
| `business_id`         | 属于哪个客户        |
| `audience_need`       | 用户此刻想解决什么问题   |
| `content_job`         | 这条内容要完成什么任务   |
| `primary_topic`       | 核心主题          |
| `primary_fact_bundle` | 主要依赖哪些事实      |
| `central_claim_key`   | 用户看完最应该记住什么   |
| `exclusive_anchor`    | 这家客户特有的具体锚点   |
| `customer_story_ref`  | 是否消费某个真实故事/评价 |

### Presentation Signature——决定“怎么讲”

| Field                 | 作用               |
| --------------------- | ---------------- |
| `speaker_id`          | 谁说               |
| `speaker_type`        | 老板 / 一线专业者 / 品牌等 |
| `opening_strategy`    | 怎么开场             |
| `narrative_mode`      | 怎么展开             |
| `case_structural_ref` | 借哪个 Case 的结构     |
| `visual_anchor`       | 主要画面是什么          |
| `storyboard_shape`    | 分镜结构             |

**Semantic Signature 决定 Novelty。**

Presentation Signature 只能增加观看体验差异，不能洗掉 Semantic Duplicate。

有一个例外：

如果换 Speaker 后引入了真正新的 `speaker_specific_fact`，从而改变 Central Claim，那么它可以成为新内容。

比如：

品牌号：

> “少盐少辣可以提前说明。”

和林东方：

> “顾客告诉我少盐少辣，我在窗口会按这个需求来加工。”

第二条因为新增了**林东方本人参与加工的 Speaker Fact**，就有机会形成真正的新内容。

---

# 四、正式建立 Content Ledger

现在系统只知道“这一批有没有重复”，远远不够。

需要建立：

> **Content Ledger V1**

它是同一 Business 的历史内容记忆。

建议采用 append-only，至少记录：

| 字段                     | 说明                                  |
| ---------------------- | ----------------------------------- |
| content_id             | 内容身份                                |
| business_id            | 客户                                  |
| speaker_id             | Speaker                             |
| semantic_signature     | 内容语义                                |
| presentation_signature | 表达方式                                |
| fact_refs              | 消费事实                                |
| central_claim          | 核心结论                                |
| exclusive_anchor       | 独特锚点                                |
| status                 | approved/exported/published/retired |
| batch_ref              | 来源 Batch                            |
| timestamps             | 生命周期                                |

这里有一个很重要的规则：

> **只有 Approved / Exported / Published 内容形成强历史记忆。**

Generated 后被 Reject 的草稿不能永久阻止未来内容，否则一次失败生成就污染了整个内容空间。

当前这 10 条 Approved 内容，就是林东方 Business 的第一批 Ledger Seed。

---

# 五、Content Opportunity Graph

我仍然建议叫 Graph，但 **V1 不需要图数据库**。

它只是一个 derived planning artifact。

逻辑关系：

> Audience → Need → Business Fact → Speaker Authority → Content Job → Exclusive Anchor → Visual Anchor

例如：

> 不会掌握火候的年轻夫妻
> → 想有人帮忙加工
> → 代炒菜服务
> → 林东方有现场烹饪 Authority
> → problem/solution
> → “主厨现场加工”
> → 接菜 + 炒菜

另一条：

> 第一次来的顾客
> → 不知道多少钱
> → 8–10 / 15 / 18 元价格事实
> → 林东方/品牌都可以讲
> → price explanation
> → 具体价格数字
> → 价目表

注意：

**Case 不进入“讲什么”的 Opportunity Graph。**

Case 仍然只负责：

> **怎么组织内容与镜头。**

这是一个应该冻结的边界。

---

# 六、Generation 从“直接写 10 条”改成 Candidate Pool

这是 V1 最大变化。

以后 Request：

> `quantity = 10`

不再代表：

> 请模型直接写 10 条文案。

而是：

> **我要最终得到最多 10 条值得发布的内容。**

默认流程改成：

> 先生成约 30 个 Content Concept → Novelty Gate → Editorial Ranking → 选 Top N → 才扩写 Script。

30 只是 V1 默认值，属于可调参数，不是 Frozen Fact。

一个 Concept 不需要完整口播，只需要：

```text
concept_id
audience_need
content_job
primary_topic
primary_fact_refs
central_claim
exclusive_anchor
speaker
visual_anchor
why_publish
```

这样系统可以便宜地淘汰 20 条平庸/重复想法，而不是先花钱写完，再一点点修。

---

# 七、Novelty Gate V1

我建议分三档。

| Gate               | 规则                                                   | 结果     |
| ------------------ | ---------------------------------------------------- | ------ |
| **Hard Duplicate** | 同 Central Claim + 同 Primary Fact Bundle              | REJECT |
| **Hard Duplicate** | 同 Audience Need + 同 Content Job + 语义等价 Central Claim | REJECT |
| **Hard Duplicate** | 同一客户故事/评价 + 同一 takeaway                              | REJECT |
| **Strong Penalty** | Fact Bundle 高重合，但 Claim 不同                           | 降权     |
| **Strong Penalty** | 同一核心 Fact 已在近期内容高频使用                                 | 降权     |
| **Soft Diversity** | Speaker / Hook / Narrative / Case / Visual Anchor 重复 | 排序惩罚   |

最关键的一条继续冻结：

> **换 Speaker、换 Hook、换 Case、换标题都不能救活 Hard Semantic Duplicate。**

V1 不需要立刻上向量数据库。

优先利用结构化字段做确定性判断；边界 pair 可以让独立的 Semantic Judge 做一次模型判断。

Judge 只有：

> duplicate / materially different / uncertain

三种结果。

它没有 Authority 权，不允许改事实。

---

# 八、Role ID 怎么正式使用

你提到的 Role ID 我建议正式采用，但规则是：

> `speaker_id` 用于 Speaker History 与 Presentation Diversity，**不是 Semantic Novelty Reset Key**。

例如同一 Business：

```text
林东方
品牌官方号
运营负责人
```

都会有各自历史。

但系统同时检查 Business 级历史。

所以：

> 林东方昨天说过的内容，不能今天换品牌号重新发一遍，系统却认为是全新内容。

只有 Speaker 自己带来了新的真实信息，才可以突破。

---

# 九、Fact Usage Pressure

这里也是目前系统缺的一层。

每个 KNOWN Fact 增加的是**内容规划状态**，不是 Authority：

```text
historical_usage_count
recent_primary_usage_count
recent_supporting_usage_count
distinctiveness_weight
```

同一个 Fact 可以重复出现。

但要区分：

> **Primary Fact** 和 **Supporting Fact**。

比如“免费米饭”完全可以在价格视频里作为辅助信息出现。

但连续三条都以：

> 免费米饭

作为主要卖点，就应该被强降权。

换句话说：

> **允许事实复用，不允许内容中心不断复用。**

---

# 十、Exclusive Anchor V1

高质量内容必须尽量包含：

> **“这家店才有资格说的具体东西。”**

可以是价格、具体菜品、具体时间、真实人物、真实评价、特定服务规则、真实流程动作、具体数据、真实场景。

例如：

> “服务很方便”

几乎没有价值。

而：

> “素菜加工通常 8–10 元”

就是强 Anchor。

> “陶先生一家是常客，他说最大的好处就是省心”

是更强 Anchor。

> “林东方在窗口按少盐少辣要求现场加工”

也是强 Anchor。

V1 建议目标：

> **最终 Production Batch 至少 80% Content 有明显 Customer-specific Exclusive Anchor。**

80% 是初始运营目标，可调，不是架构 Frozen Fact。

---

# 十一、Editorial Quality Gate

Novelty 解决：

> **“是不是新内容。”**

Editorial Quality 解决：

> **“新归新，但值不值得发。”**

每个 Concept 建议按以下维度做 0–5 分：

| 维度                       | 判断           |
| ------------------------ | ------------ |
| Audience Relevance       | 用户真的在乎吗      |
| Specificity              | 有没有具体细节      |
| Business Distinctiveness | 是不是这家店自己的内容  |
| Speaker Authenticity     | 这个人说出来合理吗    |
| Information Gain         | 看完到底多知道了什么   |
| Hook Potential           | 是否存在天然开场动力   |
| Visualizability          | 能不能自然形成画面    |
| Single Focus             | 是否一条只讲一件核心事情 |

具体权重**不要冻结**。

评分只负责：

> Ranking + Review Flag。

**不得让 Editorial Score 自动形成 Human Approval。**

---

# 十二、“删掉品牌名测试”

我建议把这个非常简单的测试正式加入 Editorial Gate：

> **如果删掉店名、人物名和行业名，这条文案还能原封不动给 100 家同行用吗？**

机器输出：

```text
customer_specific
category_specific
generic
```

Generic 不一定禁止。

例如基础 FAQ 本身有运营价值。

但一个 10 条 Production Batch 如果 7 条都是 Generic：

> **Batch Quality Fail。**

V1 初始目标建议：

> `customer_specific >= 70%`
> `generic <= 20%`

仍然属于可调运营门槛。

---

# 十三、Storyboard Diversity

脚本不重复还不够。

否则 10 条最后都是：

> 接菜 → 炒菜 → 装盒 → 递给顾客

用户仍然觉得每天同一条视频。

因此 Selected Concept 在生成脚本前就要有：

```text
visual_anchor
hero_shot_role
supporting_shot_roles
avoid_recent_visual_anchor
```

例如：

| 内容      | Hero Visual   |
| ------- | ------------- |
| 价格      | 价目表           |
| 少盐少辣    | 顾客沟通 / 调味     |
| 等待时间    | 炒制过程 / 计时感    |
| 林东方 POV | 林东方本人窗口工作     |
| 陶先生评价   | 顾客/打包/评价文字    |
| 梭子蟹场景   | 梭子蟹 / 水产 → 加工 |

同一个 Hero Visual 高频重复应进入 Diversity Penalty。

但当前 Excel Contract **不需要改**。

最终依然只导：

> 标题 + 口播。

Storyboard Plan 是内部生产 Artifact。

---

# 十四、Content Capacity Stop Rule

这是我认为必须 Frozen 的规则：

> **宁可告诉用户“当前只有 7 条值得发”，也不能为了 quantity=10 硬凑 3 条换皮内容。**

最终：

```text
requested = 10
high_quality_novel_capacity = 7
selected = 7
status = capacity_limited
```

这是正常成功状态，不是异常。

这件事非常重要，因为否则整个 Quality Engine 最终都会被“必须交够数量”击穿。

---

# 十五、新 Production Pipeline

现在：

```text
Persona
→ Source Matching
→ Angle Plan
→ Script Generation
→ Human Review
```

V1 升级成：

```text
Approved Business / Speaker Persona
        ↓
Historical Content Ledger
        ↓
Content Opportunity Plan
        ↓
30 Concept Candidates
        ↓
Novelty Gate
        ↓
Editorial Quality Ranking
        ↓
Content Capacity
        ↓
Top N Content Plan
        ↓
Approved Pattern / Case Structural Assignment
        ↓
Script Generation
        ↓
Script Editorial Check
        ↓
Storyboard Diversity Plan
        ↓
Human Review
        ↓
Approved Batch
        ↓
Excel
```

注意这个顺序体现了一项核心原则：

> **先决定“值得讲什么”，再决定“借哪个 Case 怎么讲”。**

---

# 十六、工程 Artifact 要克制

我不建议这次突然增加十几个 JSON。

V1 正式只需要新增三个核心概念：

| Artifact             | 职责                                                           |
| -------------------- | ------------------------------------------------------------ |
| `content_ledger_v1`  | 历史内容记忆                                                       |
| `content_plan_v1`    | Opportunity + Candidates + Novelty + Ranking + Selected Plan |
| `storyboard_plan_v1` | 视觉差异规划，可后置实现                                                 |

现有：

`generation_batch_v1`

只增加：

```text
concept_ref
semantic_signature
presentation_signature
editorial_summary
```

不要新建第二套 Generation Batch。

---

# 十七、对照实验怎么做

这正是你这次保留 B0 Baseline 最大的价值。

我建议下一轮**仍然用书房市集志泉社区食堂**，并且故意不给系统新增任何 Case、Persona Fact 或 Pattern。

保持：

> 同一 Business Persona
> 同一 Speaker Persona
> 同一 3 Case
> 同一 Approved Pattern
> 同一 DeepSeek Model
> 同一 Mix Profile

唯一变化：

> **增加 Content Uniqueness & Editorial Quality V1。**

然后把当前 10 条 Approved 内容先写入 Ledger。

让新系统生成：

> `real_shufang_mix_002`

目标仍然是 10 条。

但它必须把旧 10 条视为已经说过的内容。

如果最后只找到 6 条真正高质量的新内容：

> **6 条反而比硬凑 10 条更成功。**

这才是我们真正要测试的系统能力。

---

# 十八、B0 vs V1 正式 Scorecard

以后不要只比较“模型觉得好不好”。

建议比较：

| 指标                                |          B0 |      V1目标 |
| --------------------------------- | ----------: | --------: |
| Semantic duplicate pairs          | 建立 backfill |     **0** |
| Unique Central Claims             |    backfill |   尽量 100% |
| Exclusive Anchor Coverage         |    backfill | ≥80% 初始目标 |
| Generic Content Ratio             |    backfill | ≤20% 初始目标 |
| High-overlap Primary Fact Bundles |    backfill |      显著下降 |
| Unique Audience Needs             |    backfill |        提升 |
| Unique Content Jobs               |    backfill |        提升 |
| Unique Visual Anchors             |          暂无 | ≥70% 初始目标 |
| Human First-pass Approval         |    当前经历多轮修订 | ≥80% 初始目标 |
| Revision Rate                     |        当前较高 |      显著下降 |
| Lexical Similarity                |        次要指标 |     仅继续监控 |
| Capacity Padding                  |       有潜在风险 |     **0** |

其中最重要的其实不是某个模型分数，而是三个硬结果：

> **用户是否感觉每天都在讲新东西。**
> **每条是否明显属于这个客户。**
> **Human Reviewer 第一次看到时愿不愿意直接发。**

---

# 十九、这轮明确不做什么

V1 暂时不加入真实播放量学习，不做 CTR/完播率优化，不做 Embedding/Vector DB，不做跨客户内容去重，不做自动发布策略，不扩 Case，不做 News Pattern，也不改变现有 Excel Contract。

原因很简单：

> 先证明在 **Case 完全固定** 的条件下，我们能不能从同一客户事实里持续找到“新的、值得讲的内容”。

这件事如果成立，再加更多 Case 和真实运营数据，收益才会放大。
