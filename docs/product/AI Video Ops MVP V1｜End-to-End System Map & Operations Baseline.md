# 《AI Video Ops MVP V1｜End-to-End System Map & Operations Baseline》

**Status：Approved / Frozen V0.1**
**Baseline Date：2026-09-13**
**Reference Checkpoint：`9674b3ae0f84132576a6206ac630e7257f24f0be`**
**Scope：AI Video Ops MVP 当前已经成立的 Customer Truth → Content → Pre-production 生产链，以及后续视频生产链的明确接口。**

---

# 0. 这份 Baseline 不是什么

本文件不是：

* PRD；
* 某一个功能的设计稿；
* 某个脚本的使用说明；
* 当前代码目录的简单索引；
* 一份未来愿景；
* 一个新的状态机。

它是：

> **AI Video Ops 当前系统真相、运行方式与责任边界的顶层入口。**

以后一个新的 Codex 会话、运营人员、开发人员进入仓库：

**第一份应该读的就是这份 Baseline。**

---

# 1. MVP 当前产品定义

当前系统正式定义为：

> **以客户真实信息、历史内容和生产证据为基础，持续规划和生产不重复、不越权、可追溯的短视频内容，并明确告诉运营人员下一步缺什么。**

它不是：

> AI 文案生成器。

也不是：

> 爆款视频复刻器。

也不是：

> 自动剪辑软件。

当前核心产品能力是：

```text
Customer Truth
+
Historical Content Memory
+
Content Intelligence
+
Creative Intelligence
+
Production Control
```

最终目标是：

```text
真实客户信息
↓
值得讲什么
↓
这次怎么讲
↓
需要什么素材
↓
哪些素材真的可用
↓
如何组成视频
↓
成片是否可信
↓
发布以后学到了什么
```

---

# 2. 当前 End-to-End System Map

完整长期链路冻结为：

```text
┌──────────────────────────────────┐
│ 01 Customer Intake               │
│ 客户原始事实 / 资料 / 采访          │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 02 Customer Truth                │
│ Business Persona                 │
│ Speaker Persona                  │
│ UNKNOWN / REVIEW / FORBIDDEN     │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 03 Content Intelligence          │
│ Fact Atoms                       │
│ Historical Exposure              │
│ Novelty                          │
│ Editorial Quality                │
│ Content Capacity                 │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 04 Content Planning              │
│ Content Concept                  │
│ Central Claim                    │
│ Audience Need                    │
│ Semantic Signature               │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 05 Production Profile            │
│ MIX / NEWS                       │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 06 Creative Intelligence         │
│ Approved Pattern                 │
│ Structural Case Reference        │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 07 Generation                    │
│ Script / Micro Beat              │
│ Visual Anchor                    │
│ Claim → Fact                     │
└────────────────┬─────────────────┘
                 ↓
               HUMAN
               REVIEW
                 ↓
┌──────────────────────────────────┐
│ 08 Approved Content Batch        │
└────────────────┬─────────────────┘
                 ↓
       ┌─────────┴──────────┐
       ↓                    ↓
 Excel Contract       Content Ledger
 downstream output    Historical Exposure
       │
       ↓
┌──────────────────────────────────┐
│ 09 Footage Planning              │
│ Shot Requirements                │
│ Capture Missions                 │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 10 Production Assets             │
│ Asset Intake                     │  ← NEXT REAL GATE
│ Rights / Privacy                 │
│ Visual Analysis                  │
│ Event Relationship               │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 11 Storyboard Coverage           │
│ Asset → Requirement Match        │
│ covered / partial / gap / block  │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 12 Production Package            │
│ Script + Assets + Clip Ranges    │
│ + Storyboard + Rights            │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 13 Video Production              │
│ external / automation            │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ 14 Final Video QA                │
│ Claim / Subtitle / Visual        │
│ Rights / Proof / Privacy         │
└────────────────┬─────────────────┘
                 ↓
              PUBLISH
                 ↓
┌──────────────────────────────────┐
│ 15 Performance Learning          │
│ 尚未进入 MVP 当前实现范围           │
└──────────────────────────────────┘
```

---

# 3. 当前到底完成到了哪里

截至当前稳定 Baseline：

| Stage                      | Status                                             |
| -------------------------- | -------------------------------------------------- |
| 01 Customer Intake         | **PASS**                                           |
| 02 Customer Truth          | **PASS**                                           |
| 03 Content Intelligence    | **PASS**                                           |
| 04 Content Planning        | **PASS**                                           |
| 05 Production Profile      | **PASS**                                           |
| 06 Creative Intelligence   | **MVP PASS / narrow coverage**                     |
| 07 Generation              | **PASS**                                           |
| 08 Approved Content Batch  | **PASS**                                           |
| Excel Export               | **PASS**                                           |
| Content Ledger             | **PASS**                                           |
| 09 Footage Planning        | **PASS**                                           |
| Capture Missions           | **PASS**                                           |
| 10 Production Asset Intake | **Not Real-validated**                             |
| 11 Storyboard Coverage     | **Architecture exists / no real asset validation** |
| 12 Production Package      | **Not implemented**                                |
| 13 Video Production        | **Not implemented in this pipeline**               |
| 14 Final Video QA          | **Not implemented**                                |
| 15 Performance Learning    | **Future**                                         |

因此：

> **AI Video Ops MVP 的 Content + Pre-production Foundation 已经完成。**

但不能说：

> 整个 AI 视频生产 MVP 已经完成。

---

# 4. 四种信息的 Authority 必须永久分开

这是整个系统最重要的顶层规则之一。

## A. Customer Truth

回答：

> 关于这个客户，什么是真的？

Authority：

```text
Approved Business Persona Revision
+
Approved Speaker Persona Revision
```

来源必须追溯：

```text
Raw Input
→ Fact Candidate
→ Human Review
→ Approved Persona
```

---

## B. Historical Content Truth

回答：

> 我们以前已经讲过什么？

Authority：

```text
Content Ledger
+
Communicated Information Units
```

采访：

> 不是 Historical Exposure。

Persona 新事实：

> 不是 Historical Exposure。

只有内容真正：

```text
Approved / Exported / Published
```

才进入内容历史。

---

## C. Creative Knowledge

回答：

> 什么结构可以用来表达？

Authority：

```text
Approved Pattern
+
Approved Case Structural Reference
```

Case 不提供：

> 客户事实。

Case Media 不自动获得：

> Production Rights。

---

## D. Production Evidence

回答：

> 这条视频实际用了什么素材，素材是否能够承担这个视觉语义？

Authority：

```text
Production Asset
+
Rights
+
Privacy
+
Event Relationship
+
Requirement Match
```

Visual：

> 不创建 Customer Truth。

也：

> 不自动创建 Proof。

---

# 5. 系统 Authority Hierarchy

当 Artifact 互相冲突时，不能“取最新文件”。

正式优先级如下。

### Customer Fact

```text
Approved Persona Current Revision
>
Pending Persona Revision
>
Fact Candidate
>
Raw Input
>
AI inference
```

AI inference 永远不能直接成为 Production Authority。

---

### Content Novelty

```text
Content Ledger / Historical Exposure
+
Current Approved Fact Atoms
+
Canonical Effective Gate Resolver
```

不要让 downstream 自己读取：

```text
gate_decision
v1_1_gate_decision
v1_1_1_gate_decision
```

必须通过：

```text
resolve_effective_content_gate_decision(...)
```

---

### Creative Structure

```text
Approved Pattern
>
Approved Case Structural Reference
>
Pattern Candidate
>
Research Hypothesis
```

Generation 不得消费：

> 未批准 Pattern。

---

### Production Media

```text
Production-eligible Asset
>
Partial / Review Asset
>
Unregistered Media
>
Case Media
```

Case Media 不进入 Production Pool。

---

# 6. Artifact 的五类角色

以后所有 Artifact 必须能够被归入以下之一。

## 1. Authority Artifact

决定业务事实。

例如：

* Approved Persona；
* Content Ledger；
* Approved Pattern；
* Approved Batch；
* Subject Media Authorization；
* Production Asset Eligibility。

---

## 2. Derived Artifact

计算结果，可以重新生成。

例如：

* Content Capacity；
* Content Gap；
* Persona Readiness；
* Storyboard Coverage；
* Capture Mission；
* Current Status View。

Derived Artifact：

> 不能反过来创造 Authority。

---

## 3. Human Approval / Validation Receipt

证明某次 Human Gate 已发生。

例如：

* approval receipt；
* validation artifact；
* batch human approval；
* capacity human approval。

它记录：

> 谁批准了什么。

但不是新的 Customer Truth。

---

## 4. Historical Artifact

旧 Revision、旧 Generation Attempt、旧 Diagnostics。

必须保留时：

> immutable。

但 downstream：

> 不能误认为 Current Authority。

---

## 5. Fixture / Test Artifact

仅用于：

* tests；
* smoke validation；
* architecture validation。

永远不得进入：

> Real Customer Authority。

---

# 7. 禁止“哪个文件更新时间新就用哪个”

这是 Operations Baseline 中必须明确写死的。

系统不得通过：

```text
mtime
created_at
directory sort
filename max
```

自行决定 Authority。

Current Authority 必须依赖：

* explicit revision；
* lifecycle status；
* approval receipt；
* canonical reference；
* current resolver。

---

# 8. Human Gates

不是所有步骤都需要 Human Review。

但以下 Gates 属于核心控制面。

## Mandatory Customer Truth Gate

```text
Fact Candidate
→ Human Review
→ Persona Approval
```

AI 不得自动批准 Persona。

---

## Mandatory Content Gate

```text
Generated Batch
→ Human Review
→ Approved Batch
```

当前 MVP 不允许：

> Generated = Approved。

---

## Production Rights Gate

素材进入正式生产前必须确认：

```text
media rights
privacy
identifiable people
scope
```

---

## Final Video Gate

未来正式发布前：

```text
Rendered Video
→ Final QA
→ Human Acceptance
```

这个 Gate 尚未实现，但在系统图中预留。

---

# 9. Research Gate 与 Production Gate 分离

Case / Pattern Research 有自己的：

```text
Case Approval
Pattern Approval
```

但这是：

> Creative Intelligence 管理流程。

它不是每天给客户生产内容的主流程。

运营人员不应该为了做一条新视频：

> 去批准 Case 或 Pattern。

如果当前 Creative Coverage 足够：

> 直接生产。

---

# 10. 新客户 Runbook

新客户进入系统时标准流程冻结如下：

```text
客户原始资料
↓
customer_intake
↓
Fact Extraction
↓
Persona Review
↓
Business Persona Approval
↓
Speaker Persona Approval
↓
Content Capacity
↓
Generation Request
↓
Content Planning
↓
Production Profile
↓
Pattern Match
↓
Generation
↓
Human Review
↓
Approved Batch
↓
Export
↓
Ledger
↓
Footage Planning
↓
Capture / Asset
```

第一轮禁止要求：

> Persona 全字段填满。

目标：

> Minimum Viable Customer Truth。

---

# 11. Existing Customer Content Exhausted Runbook

当：

```text
high_quality_content_capacity
```

明显不足时：

不要：

> 换标题继续生成。

标准流程：

```text
Content Gap
↓
Gap-driven Interview
↓
Raw Replenishment Intake
↓
Fact Extraction
↓
Persona Revision N+1
↓
Human Approval
↓
Capacity Recalculation
↓
New Content Space
```

林东方已经完成第一轮真实验证：

```text
Capacity 2
→ Interview
→ Persona Rev2
→ Capacity 12
```

随后生产 4 条后：

```text
12
→ actual remaining capacity 7
```

这证明 Capacity 不是简单：

> 数量减法器。

---

# 12. New Content Batch Runbook

正式生成一批内容前：

先判断：

```text
requested quantity
vs
high-quality semantic capacity
```

如果：

```text
capacity < requested
```

正确结果：

```text
capacity_limited
```

不是：

> Padding。

---

# 13. Production Profile Runbook

当前支持：

```text
mix
news
```

Production Profile 决定：

> 怎么交付内容。

不决定：

> 内容是否新。

因此：

```text
Profile Switch
!=
Novelty Reset
```

News 可以重新表达 Mix 内容，但必须：

```text
cross_profile_repurpose
semantic_novelty = false
```

---

# 14. Mix 当前状态

Mix：

> 当前最成熟 Production Path。

已有真实证明：

```text
Persona
→ Capacity
→ Novel Generation
→ Human Review
→ Excel
→ Ledger
```

最新真实 Batch：

```text
real_shufang_mix_003
```

已：

```text
approved
exported
ledger recorded
```

---

# 15. News 当前状态

News 已有：

### Approved Patterns

```text
Price / Offer-led Micro-information
Scene Contrast
```

### 已真实 Production Validation

```text
Price / Offer-led
```

### 尚未真实 Production Validation

```text
Scene Contrast
```

原因不是系统失败。

而是：

> 当前客户没有 Approved A/B Truth。

因此：

```text
pending_real_customer_opportunity
```

正确。

不要为验证：

> 制造 A/B。

---

# 16. Customer Story Runbook

Customer Story 必须同时区分：

### Story Truth

这件事：

> 是否真实？

### Content Reuse Scope

这段：

> 可以怎么说？

### Media Rights

照片 / 视频：

> 可以使用吗？

三者不能合并成：

```text
authorized = true
```

---

# 17. Persona 与 Speaker 的运行规则

一个 Business：

```text
Business Persona
├── Owner
├── Frontline Expert
├── Brand
└── Generic
```

业务事实：

> 属于 Business。

第一人称资格：

> 属于 Speaker。

Speaker：

> 不能自动继承所有 Business 事实为第一人称。

---

# 18. Speaker Persona ≠ Speaker Media Rights

正式冻结：

```text
Speaker Authority
!=
肖像 / 视频授权
```

一个人允许：

> 用他的身份写第一人称内容

不意味着：

> 允许把他的脸放到公开视频里。

Media Authorization：

> 独立 Authority。

---

# 19. Content Capacity 的正确含义

正式定义：

> **当前 Approved Customer Truth 与 Historical Exposure 条件下，仍存在多少高质量、独立的语义内容机会。**

不是：

* 发布配额；
* 月度产量；
* Generator quota；
* 必须一次生产数量。

例如：

```text
capacity = 12
```

不代表：

> 立即生成 12 条。

---

# 20. Content Gap 的正确含义

Content Gap 回答：

> **为了扩大未来 Content Space，下一步最值得补什么真实信息？**

它：

> 不能创建事实。

也：

> 不能自动触发采访。

运营人员决定：

> 现在值不值得去补。

---

# 21. Content Ledger 是业务级长期记忆

Ledger 按：

```text
Business
```

而不是：

```text
Speaker
Production Profile
Platform
```

隔离。

因此：

> 换 Speaker 不重置 Novelty。

> Mix → News 不重置 Novelty。

> 以后 TikTok → 小红书也不应自动重置 Novelty。

除非未来显式支持：

```text
repurpose
```

---

# 22. Excel 的定位

Excel 是：

> **Downstream Production Contract。**

不是：

* Customer Truth；
* Content Authority；
* Pattern；
* Ledger。

Excel 中不应加入：

* internal IDs；
* Pattern；
* Fact Atom；
* Persona SHA；
* Authority metadata。

---

# 23. Footage Planning 的运行原则

Approved Script 之后：

```text
Script
↓
Shot Requirement
↓
Capture Mission
```

Shot Requirement：

> 内部语义验收标准。

Capture Mission：

> 客户能执行的拍摄任务。

正式冻结：

```text
Shot Requirement
!=
Capture Mission
!=
Media File
```

一个 Mission：

> 可以覆盖多个 Requirements。

一个 Mission：

> 可以回来多个 Media Files。

---

# 24. Production Asset 的核心规则

素材存在：

> 不等于素材可用。

Production Eligibility 至少取决于：

```text
Source
Media Rights
Privacy
Subject Rights
Scope
Profile Compatibility
Event Relationship
```

Ownership：

> 单独不足以通过 Production Gate。

---

# 25. Visual Event Relationship

当前最小四类继续冻结：

```text
exact_event_footage

actual_current_operation

illustrative_same_process

generic_context
```

关键边界：

```text
illustrative_same_process
!=
exact_event_footage
```

后补相似流程不能证明：

> 当时那次真实事件。

---

# 26. Visual Truth ≠ Content Truth

一个画面看到：

> 花蛤泡在水里。

不能证明：

> 它之前没有吐沙。

一段现在补拍的蟹加工：

不能证明：

> 原来那一次正好用了 15 分钟。

Visual：

> 只能承担其实际可观察的信息。

---

# 27. Proof Authority 继续独立

Process：

> 不等于 Proof。

Busy shop：

> 不等于生意好。

白板：

> 不等于焦虑下降。

Cooking：

> 不等于客户满意。

只有经过 Proof Authority 支持的内容：

> 才能作为 Result Proof。

---

# 28. Privacy 全局规则

任何 Remote Model：

必须：

```text
Canonical Source
↓
Privacy Projection
↓
Safe Input
↓
assert_safe_for_external_model
↓
Network
```

不能因为进入新 Pipeline：

> 自己建立另一套 Privacy Logic。

---

# 29. Case Library 永远不是 Production Footage Library

这条必须写在 Baseline 顶层。

```text
Approved Case
```

只意味着：

> 可以用于内部 Creative / Structural Research。

不意味着：

> 可以把它的视频拿来给客户生产。

当前 public Case：

```text
media_reuse_rights = not_established
production_footage_pool_eligible = false
```

继续成立。

---

# 30. 当前 Current Status Snapshot

当前真实客户：

```text
Business:
shufang_zhiyuan_community_canteen

Primary Speaker:
lin_dongfang_frontline_chef
```

Customer Truth：

```text
Business Persona Rev2 — APPROVED
Speaker Persona Rev2 — APPROVED
```

Content：

```text
Latest exported Mix Batch:
real_shufang_mix_003

Remaining High-quality Novel Capacity:
7
```

Production：

```text
Footage Planning — APPROVED
Capture Missions — 4
Capture Pack — ready_to_send
Sent — false

Production Assets — 0
Eligible Assets — 0

Storyboard Coverage:
4 / 4 capture_required
```

Speaker Media:

```text
Lin Dongfang:
review_required
```

---

# 31. 当前真正的 Next Action

如果没有人工暂停：

```text
SEND_CUSTOMER_CAPTURE_PACK
```

然后：

```text
COLLECT_RAW_ASSETS
```

但当前用户已经明确：

> 暂时不打扰客户补拍。

因此现在真实运营状态应表达为：

```text
Operational Hold:
true

Reason:
customer outreach intentionally deferred
```

这种 Hold：

> 属于 Operations Metadata。

不是：

> Customer Truth / Content Authority。

---

# 32. Current Status Read Model

建议建立唯一只读能力：

```text
show_customer_status_v1
```

它不能：

* 修改状态；
* 自动推进；
* 创建 Artifact；
* 触发模型。

只读取 Current Authority 并生成：

```text
Customer Truth
Content
Latest Batch
Content Capacity
Footage
Rights
Blockers
Current Next Action
```

示例：

```text
AI VIDEO OPS — CUSTOMER STATUS

Business
  书房市集志泉社区食堂

Customer Truth
  Business Persona Rev2      APPROVED
  Speaker Persona Rev2       APPROVED

Content
  Remaining Novel Capacity   7
  Latest Mix Batch           EXPORTED
  Latest News Path           PRICE VALIDATED

Footage
  Capture Pack               READY_TO_SEND
  Registered Assets          0
  Eligible Assets            0
  Covered Contents           0 / 4

Rights
  Lin Dongfang Media         REVIEW_REQUIRED

Current Blocker
  RAW PRODUCTION ASSETS NOT AVAILABLE

Operational Hold
  ACTIVE

Next Action
  WAIT_FOR_OPERATOR_RELEASE
```

---

# 33. Read Model 不得创建第二套状态

Current Status：

> 全部 Derived。

例如：

```text
Persona Approved
```

从 Persona Authority 读取。

```text
Latest Batch Exported
```

从 Batch + Export Receipt 读取。

```text
Capacity 7
```

从当前 Capacity Derived Artifact 读取。

不能创建：

```text
customer.status = READY
```

然后让它变成第二个真源。

---

# 34. Current Next Action 规则

整个客户在任一时刻：

> **只推荐一个 Primary Next Action。**

可以有 Secondary Notes。

但不能告诉运营：

> “你可以采访，也可以生成，也可以补 Case，也可以拍素材，也可以扩 Pattern……”

这会失去编排价值。

---

# 35. Next Action Resolution Priority

建议 Derived Resolver 按优先级：

```text
1. HARD AUTHORITY BLOCKER

2. REQUIRED HUMAN REVIEW

3. REQUIRED CUSTOMER / OPERATOR INPUT

4. SYSTEM EXECUTION

5. OPTIONAL IMPROVEMENT
```

例如：

Persona 未批准：

```text
REVIEW_PERSONA
```

不是：

> Generate Content。

没有 Content Capacity：

```text
RUN_REPLENISHMENT
```

不是：

> Force Generation。

没有素材：

```text
COLLECT_PRODUCTION_ASSETS
```

不是：

> Start Rendering。

---

# 36. Operational Hold 优先于 Next Action

如果：

```text
operational_hold = true
```

则 Current Next Action：

```text
WAIT_FOR_OPERATOR_RELEASE
```

同时显示：

```text
would_be_next_action:
SEND_CUSTOMER_CAPTURE_PACK
```

这样系统：

> 知道该做什么。

但尊重：

> 人明确选择暂时不做。

---

# 37. RUNBOOK 的正式入口

仓库应最终拥有：

```text
docs/operations/RUNBOOK.md
```

它只解决一个问题：

> **“我现在要做某件事，标准流程是什么？”**

---

# 38. RUNBOOK 应覆盖的核心场景

V1 至少覆盖：

### New Customer

```text
NEW_CUSTOMER
```

### Existing Customer / Generate New Batch

```text
NEW_CONTENT_BATCH
```

### Content Capacity Low

```text
CONTENT_REPLENISHMENT
```

### Create News Content

```text
NEWS_PRODUCTION
```

### Human Review Batch

```text
CONTENT_HUMAN_REVIEW
```

### Export

```text
APPROVED_BATCH_EXPORT
```

### Footage Planning

```text
FOOTAGE_PLANNING
```

### Assets Returned

```text
PRODUCTION_ASSET_INTAKE
```

未来加入：

```text
VIDEO_QA
PUBLISH
PERFORMANCE_REVIEW
```

---

# 39. 每个 Runbook Entry 的格式

统一写：

```text
Goal

Required Inputs

Authority Preconditions

Execution

Human Gate

Outputs

Stop Conditions

Next Action
```

不要写成：

> 一大段教程。

---

# 40. RUNBOOK 不能硬编码已过时命令

Codex Consolidation 时：

> 从当前真实实现发现现有 CLI / Script。

Baseline 冻结：

> Operation。

不冻结：

> 某一行 CLI 永远不变。

例如：

```text
Operation:
BUILD_PERSONA
```

可以以后换实现。

---

# 41. System Map 与 RUNBOOK 的关系

System Map：

> 解释整个系统。

RUNBOOK：

> 告诉运营怎么跑。

Current Status：

> 告诉运营现在跑到哪。

Next Action：

> 告诉运营现在只该做什么。

四个东西不要混成一份巨大文档。

---

# 42. 推荐最终文档组织

```text
/docs/operations/

AI_VIDEO_OPS_SYSTEM_MAP_V1.md

AUTHORITY_MAP_V1.md

RUNBOOK.md

ARTIFACT_LIFECYCLE_V1.md

CURRENT_STATUS_READ_MODEL_V1.md
```

另外根目录：

```text
README / OPERATIONS entry
```

指向：

> RUNBOOK。

---

# 43. Artifact Lifecycle 文档必须解决“哪些能删”

这是本轮 Consolidation 很关键的一部分。

每个目录 / Artifact 类型必须分类：

```text
CURRENT_AUTHORITY

ACTIVE_DERIVED

HISTORICAL_IMMUTABLE

VALIDATION_RECEIPT

FIXTURE_TEST

DEPRECATED
```

---

# 44. CURRENT_AUTHORITY

永远保留。

例如：

* Approved Current Persona；
* Content Ledger；
* Approved Patterns；
* Current Approved Batch；
* Media Authorization。

---

# 45. ACTIVE_DERIVED

可重新生成，但当前运营会用。

例如：

* current capacity；
* current gap；
* current coverage；
* capture pack。

可以替换：

> 同一语义的新版本。

不需要无限堆叠。

---

# 46. HISTORICAL_IMMUTABLE

为了 lineage / audit 必须保存。

例如：

* Approved Persona Rev1；
* older approved batch；
* old generation attempts；
* prior ledger state if intentionally persisted。

不能被当前 Consumer：

> 当 Current Authority 使用。

---

# 47. VALIDATION_RECEIPT

保留关键 Gate 的证据。

但：

> 不作为业务事实消费。

---

# 48. FIXTURE / TEST

必须与真实客户数据隔离。

目录和 ID 要能明显识别：

```text
fixture_
test_
sample_
```

Fixture 不得被：

> Production Matcher

扫描到。

---

# 49. DEPRECATED

满足以下条件应该删除或归档：

* 同职责已有 canonical replacement；
* 当前代码 / docs / tests 无消费；
* 不承担 Historical Lineage；
* 不属于 Approval Receipt；
* 不包含唯一调查证据。

---

# 50. 脚本治理原则

用户之前已经明确要求：

> 新版本能覆盖旧脚本时，优先直接替换。

因此正式写入 Baseline：

> **One Responsibility → One Canonical Script / Entry Point**

避免：

```text
generate_x_v1.py
generate_x_v2.py
generate_x_new.py
generate_x_final.py
```

长期共存。

---

# 51. 什么时候可以保留旧脚本

只有：

### A. Compatibility

外部接口仍依赖。

### B. Migration

旧数据仍需要迁移。

### C. Historical Reproduction

必须重现旧 Approved Artifact。

否则：

> 删除。

---

# 52. 旧脚本如果保留必须明确标识

例如：

```text
deprecated
do_not_use_for_new_production
replacement = ...
```

并且：

> RUNBOOK 不能指向它。

---

# 53. Output 治理

同一个正式 Batch：

不要在根目录残留：

```text
final.xlsx
final2.xlsx
final_latest.xlsx
test_final.xlsx
```

正式输出必须由：

```text
request_id
revision
approval state
```

能够定位。

---

# 54. Generated Data 与 Git

维持当前仓库真实策略即可，不强行统一所有 data 入 Git。

但必须明确：

### Code / Contract / Tests

应进入 Git。

### 必须形成产品证据的 Approved Output

按现有 repo policy。

### Cache / Downloads / Temp

不入 Git。

### Secret

永不入 Git。

---

# 55. Consolidation Audit 的目标

Codex 下一轮不是：

> 重构整个仓库。

而是输出：

```text
CURRENT
KEEP

HISTORICAL
KEEP BUT DO NOT CONSUME

FIXTURE
ISOLATE

DEPRECATED
REMOVE / ARCHIVE

UNKNOWN
HUMAN REVIEW
```

---

# 56. Consolidation 不允许做的事

禁止借机：

* 重写 Persona Schema；
* 重写 Content Ledger；
* 合并 Case / Production Asset；
* 重做 Pattern；
* 改 Novelty；
* 改 Customer Truth；
* 重新跑真实模型；
* 删除 Historical Approved Artifacts；
* 大规模代码重构。

---

# 57. Research System 当前进入 Maintenance Mode

Case / Pattern 现在不再是开发主线。

进入：

```text
MAINTENANCE / DEMAND-DRIVEN
```

只有发生：

### Coverage Gap

当前 Pattern 无法表达一个真实 Production Need。

### New Profile

例如未来出现新 Profile。

### Evidence Need

需要验证新的结构假设。

才重新 Research。

---

# 58. Content Intelligence 同样进入 Stability Mode

当前不要主动：

* 增评分维度；
* 换算法；
* 引入 Embedding DB；
* 做更多 Novelty 版本。

只有真实 Production Failure：

> 才打开对应模块。

---

# 59. Customer Truth 进入 Operational Mode

Initial Intake + Replenishment：

后台能力已通过。

下一次真正需要验证的是：

> **第二个不同类型的真实客户。**

不是继续优化林东方。

---

# 60. Production Footage 成为下一主线

接下来主线：

```text
Production Asset Intake
↓
Asset Eligibility
↓
Visual Analysis
↓
Requirement Match
↓
Storyboard Coverage
↓
Production Package
```

这是当前最大未完成链路。

---

# 61. Asset Intake 真正启动的条件

不是：

> 开发人员想继续写。

而是：

```text
真实客户素材到达
```

第一轮必须使用：

> 未经过人工挑选的 Raw Customer Assets。

这样才能真实验证：

> 系统是否能处理混乱输入。

---

# 62. Production Package 将成为下一重要 Canonical Contract

未来应把：

```text
Approved Script

Matched Assets

Clip / Shot References

Storyboard Order

Narration Mapping

Rights State

Privacy State

Missing/Fallback
```

组合成：

```text
production_package_v1
```

但：

> 本轮 Baseline 只预留，不立即实现。

---

# 63. Final Video QA 的未来职责

至少检查：

* Narration；
* Subtitle；
* Visual Claim；
* Event Relationship；
* Rights；
* Privacy；
* Proof；
* Storyboard Coverage；
* 是否把 illustrative footage 当原事件。

它会成为：

> Publish 前最后 Human Gate。

---

# 64. Performance Learning 暂不进入当前主线

原因很简单：

目前连：

> Production Asset → Final Video

尚未跑通。

此时设计复杂：

* CTR；
* Completion；
* Conversion；
* Winner Pattern；
* Performance Model；

都过早。

---

# 65. 第二真实客户 Gate

在大规模产品化 UI 之前：

必须至少验证一个：

> **明显不同于当前餐饮窗口业务的客户。**

建议优先：

* 宠物；
* 美容；
* 家政；
* 汽修；
* 健身；
* 零售；
* 教培。

关注：

> 核心架构是否无需修改即可运行。

而不是：

> 内容是否漂亮。

---

# 66. 泛化验证重点

第二客户重点检查：

```text
Business/Speaker separation
Customer Truth
Capacity
Gap Interview
Novelty
Mix Production
Footage Requirements
```

如果需要添加：

> 行业特定 Fact Fields

没问题。

如果需要重写：

> Customer Truth / Novelty / Authority

则说明顶层架构还没有泛化。

---

# 67. 当前 MVP 不追求全自动

当前正确架构是：

```text
AI does:
extract
plan
compare
match
generate
check

Human owns:
truth approval
content approval
rights confirmation
final acceptance
```

不要为了宣传：

> 强行把 Human Gate 去掉。

---

# 68. 当前 MVP 的成功指标

现在不应该用：

> “一天生成多少条文案”

衡量系统。

更有价值的是：

### Truth Safety

有没有瞎编。

### Semantic Novelty

有没有真的避免重复。

### Capacity Honesty

没内容时敢不敢返回 0。

### Production Traceability

每条内容为什么能说。

### Footage Actionability

系统能不能明确告诉客户拍什么。

### Delivery Continuity

一个环节结果能不能成为下一环节明确输入。

---

# 69. 当前最重要的已验证案例

林东方客户已经证明：

```text
Content Capacity 2
↓
Gap-driven Interview
↓
Persona Rev2
↓
Capacity 12
↓
Production 4
↓
Historical Exposure update
↓
Actual remaining capacity 7
```

这是当前系统最有价值的一条真实验证链。

它应该进入：

> System Validation Evidence。

但不应被宣传成：

> 效果 Proof。

---

# 70. Operations Baseline 的 Freeze 强度

我建议真正 Frozen 的只有这些。

### F1

一项事实只有一个 Authority Owner。

### F2

Raw Input 不直接等于 Production Truth。

### F3

Business Persona / Speaker Persona 分离。

### F4

Content Ledger 是 Business-wide Historical Content Authority。

### F5

Production Profile 不重置 Novelty。

### F6

Case / Pattern 与 Customer Truth 分离。

### F7

Case Media 与 Production Asset 分离。

### F8

Visual Truth 不升级 Customer Truth / Proof。

### F9

Speaker Authority 不等于 Media Rights。

### F10

Capacity 是语义库存，不是生产配额。

### F11

No Padding。

### F12

Approved Revision 不静默覆盖。

### F13

Human Gates 控制 Customer Truth、Content Approval、Rights 与最终发布。

### F14

Derived Status / Current Status 不建立第二套 Authority。

### F15

Current Next Action 只允许一个 Primary Action。

---

# 71. 不冻结的内容

以下都应保持可迭代：

* CLI；
* 文件目录细节；
* Prompt；
* 模型；
* scoring weight；
* 一批生成几条；
* Capture Mission 格式；
* 视频时长；
* Pattern 数量；
* Case 数量；
* UI；
* 数据库；
* embedding；
* 自动剪辑方式；
* 发布平台。

---

# 72. 明确拒绝的未来漂移

后续开发如果出现以下行为，应视为 Architecture Drift：

1. 为新模块建第二套 Customer Truth。
2. 新 Profile 重置历史内容。
3. AI 自动批准 Persona。
4. Case Fact 被写入客户 Persona。
5. Case Media 被 Production 使用。
6. 视觉匹配自动升级 Proof。
7. Speaker Persona 自动获得肖像权。
8. Capacity 为满足订单被 Padding。
9. Derived Status 成为第二套状态机。
10. 通过文件更新时间决定 Authority。
11. 同职责长期保留多个“新版”脚本。
12. 生成成功直接等于发布批准。

---

# 73. Current Development Mode

从本 Baseline 批准开始，项目开发模式应改变。

之前：

> Foundation Building。

现在：

> **Evidence-driven Production Closure。**

意思是：

> 不再因为“这个功能以后可能有用”而开发。

只有：

### Real Production Blocker

真实流程跑不下去。

### Operational Friction

每天重复手工处理。

### Authority Risk

可能造成错误事实 / 权限 / Proof。

### Scale Bottleneck

第二客户出现重复人工。

才进入开发。

---

# 74. 一条非常重要的停止原则

如果一个问题：

> 还没有在真实客户流程里发生，

且：

> 不阻塞下一次真实运营，

默认：

# 不做。

这会是接下来防止系统过度工程化最重要的一条规则。

---

# 75. 当前 Recommended Backlog

当前真正推荐优先级：

### P0 — Consolidation

System Map
Authority Map
RUNBOOK
Current Status Read Model
Artifact / Script Audit

### P1 — 等真实素材

Production Asset Intake
Storyboard Coverage

### P2 — Production Package

建立内容与视频制作系统的正式 handoff。

### P3 — Final Video QA

完成第一批真实成片闭环。

### P4 — Second Customer

跨行业泛化。

### P5 — Operations UI

在流程稳定后产品化。

### Later

Performance Learning
Publishing Automation
Research Expansion。

---

# 76. 当前 Operations Dashboard 应该只显示什么

未来哪怕做 UI，我也建议先只有：

```text
Customer

Customer Truth

Remaining Content Capacity

Latest Batch

Footage Coverage

Blockers

Current Next Action
```

不要一开始做：

> 复杂 analytics dashboard。

---

# 77. 当前客户的 Current Status

截至本 Baseline：

```text
书房市集志泉社区食堂

Customer Truth
  Business Persona      Rev2 / Approved
  Speaker Persona       Rev2 / Approved

Content
  Remaining Capacity    7
  Latest Batch          real_shufang_mix_003
  Batch                 Approved / Exported

Creative
  Mix Pattern           Available
  News Price Path       Validated
  News Scene Path       Pending real opportunity

Footage
  Planning              Approved
  Capture Missions      4
  Capture Pack          Ready to Send
  Production Assets     0
  Eligible Assets       0
  Storyboard Coverage   0 / 4
                        capture_required

Rights
  Lin Dongfang Media    Review Required

Operations
  Customer Outreach     Deferred by Operator

Current Next Action
  WAIT_FOR_OPERATOR_RELEASE

Would-be Next Action
  SEND_CAPTURE_PACK
```

---

# 78. 什么时候当前客户重新启动

用户取消 Operational Hold：

```text
WAIT_FOR_OPERATOR_RELEASE
↓
SEND_CAPTURE_PACK
↓
COLLECT_RAW_ASSETS
```

素材收到后：

```text
REGISTER_PRODUCTION_ASSETS
```

然后项目开发主线重新启动。

---

# 79. 这份 Baseline 的最终价值

如果冻结成功，以后不应该再发生：

> “我们之前这个脚本是不是还能用？”

> “这个 JSON 哪个是最新的？”

> “这个新闻体换 Profile 后是不是又算新内容？”

> “这个 Case 视频能不能直接拿来剪？”

> “Persona 里有这个事实是不是就能让林东方露脸？”

> “现在这个客户下一步到底干什么？”

所有这些都应该能从：

```text
System Map
+
Authority Map
+
RUNBOOK
+
Current Status
```

得到明确答案。
