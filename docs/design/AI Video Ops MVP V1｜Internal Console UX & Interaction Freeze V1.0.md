# 《AI Video Ops MVP V1｜Internal Console UX & Interaction Freeze V1.0》

**Status：Approved / Frozen**
**Product Surface：Internal Production Console**
**Design Principle：Mobile-first / Desktop-adaptive**
**Primary Users：内部运营人员**
**MVP Stop Point：案例入库 → 客户/人设 → 内容生成 → Human Review → Excel 导出 → 素材准备入口**

---

# 1. 产品定位

V1 前端不是公开 SaaS，不承担客户自助使用。

它是：

> **AI Video Ops 内部生产工作台。**

核心任务只有三件：

1. 扩充和审核案例库；
2. 建立、审核和选择客户 / 出镜人设；
3. 生成、审核、预览并导出视频内容。

前端是现有 Operations Layer 的 **Surface**，不是重新实现一套业务系统。

因此正式冻结：

> **Frontend Status = Existing Authority Projection**

前端不得创建第二套 Customer Truth、Content Lifecycle、Novelty、Capacity、Case、Pattern 或 Rights Authority。

---

# 2. V1 总体闭环

用户从登录开始，可以完整完成：

```text
登录
↓
工作台

┌──────── 案例生产 ────────┐
粘贴视频网址
↓
后台异步分析
↓
案例审核
↓
批准入库
└───────────────────────┘

┌────── 客户 / 人设 ───────┐
新建客户
↓
输入已有资料
↓
AI 提取事实
↓
人工确认
↓
Business Persona Approved
↓
添加 / 选择出镜人
↓
Speaker Persona Approved
└───────────────────────┘

┌──────── 视频创作 ────────┐
选择客户
↓
选择出镜人
↓
选择视频类型
↓
输入数量
↓
Capacity Check
↓
生成
↓
Human Review
↓
批准 Batch
↓
内容预览
↓
Excel 下载
↓
查看素材准备
└───────────────────────┘
```

---

# 3. V1 冻结 UX 原则

### P1 — Internal-only

无公共注册入口。

账号由内部管理员预置。

### P2 — Mobile-first

390px 左右手机宽度是第一验收基线。

Desktop 是更高效率的适配 Surface，而不是设计源头。

### P3 — Desktop-adaptive

桌面端允许：

* 左右分栏；
* 更高信息密度；
* 更宽列表；
* 并排审核。

但不得改变核心步骤、Authority 或 CTA。

### P4 — One screen, one main decision

手机端一个 Screen 优先解决一个主要问题。

### P5 — Progressive disclosure

普通运营只看到业务语言。

内部 Fact ID、SHA、Pattern ID 等默认隐藏。

### P6 — Human Gate 不消失

AI 完成：

> ≠ 自动批准。

### P7 — Async + Recoverable

耗时任务允许退出页面。

任务状态必须可恢复。

### P8 — No Padding

Content Capacity 不足时减少数量，不补重复内容。

### P9 — Authority Projection Only

前端状态来自已有 Authority / Resolver。

### P10 — Primary Action First

每个核心页面只强化一个 Primary CTA。

### P11 — Mobile 不依赖宽表格

列表以 Card 为主要表达形式。

### P12 — Sticky Action

长流程核心 CTA 在手机端优先使用 Bottom Action Bar。

### P13 — Business language first

例如：

`Content Capacity`

前端显示：

> **剩余内容空间**

### P14 — Tasks survive navigation

切换 Tab、锁屏、刷新、退出再登录后，任务仍可恢复。

### P15 — Case ≠ Production Media

案例审核界面永久保持这一边界。

### P16 — Business Persona ≠ Speaker Persona

前端必须显式区分客户档案和出镜人设。

### P17 — Speaker Persona ≠ Media Rights

人设可用于写第一人称，不代表允许露脸。

### P18 — Excel 是生产合同，不是唯一结果界面

用户首先能直接预览和复制内容，然后才下载 Excel。

---

# 4. Global Navigation

## Mobile

固定底部导航：

```text
工作台     案例     创作     客户     任务
```

其中：

> **创作**

作为中央高频入口适度强化。

顺序正式冻结为：

```text
工作台
案例
创作
客户
任务
```

---

## Desktop

映射为左侧导航：

```text
工作台

案例库

视频创作

客户与人设

任务记录
```

右上角：

```text
当前账号
修改密码
退出登录
```

不单独创建复杂“设置中心”。

---

# 5. Authentication

## `/login`

页面结构：

```text
AI Video Ops

手机号
[              ]

密码
[              ]

[ 登录 ]
```

不显示：

```text
注册
短信验证码
找回密码
第三方登录
```

账号由内部创建。

初始密码：

```text
123456
```

---

# 6. 首次登录

如果：

```text
must_change_password = true
```

登录成功后不能进入工作台。

直接进入：

## `/change-password`

```text
首次登录，请设置新密码

当前密码
新密码
确认新密码

[ 保存并进入工作台 ]
```

保存后：

```text
must_change_password = false
```

然后进入工作台。

密码必须使用安全哈希。

禁止数据库保存：

```text
123456
```

明文。

---

# 7. Workbench

## `/workbench`

移动端首屏首先不是 Dashboard，而是：

> **今天需要做什么。**

示例：

```text
你好，李健

今天有 2 件事需要处理

┌──────────────────────┐
│ 2 个案例等待审核       │
│                去审核 ›│
└──────────────────────┘

┌──────────────────────┐
│ 林东方 · Mix003        │
│ 已导出 · 等待素材       │
│                 查看 › │
└──────────────────────┘
```

然后三个快捷入口：

```text
+ 添加案例

+ 新建客户

+ 开始视频创作
```

---

# 8. Workbench 数据原则

展示：

* 待审核案例；
* 待审核客户信息；
* 待审核生成任务；
* 运行中任务；
* 最近完成任务。

不做：

* GMV；
* 用户 DAU；
* 大量 Analytics；
* 漂亮但无行动意义的指标。

核心原则：

> **Action Dashboard，不是 Data Dashboard。**

---

# 9. Case Library

## `/cases`

Mobile Card：

```text
视频标题 / 简短内容

抖音 · 32 秒

待审核

刚刚分析完成

[ 去审核 ]
```

支持状态：

```text
分析中
待审核
已入库
失败
已归档
```

这只是 UI Projection。

后台 lifecycle 不改变。

---

# 10. Add Case

## `/cases/new`

页面只突出一件事：

> **添加一个视频案例**

输入：

```text
粘贴视频链接
[ https://...             ]

[ 从剪贴板粘贴 ]

[ 开始分析 ]
```

自动识别来源时显示：

```text
已识别：抖音视频
```

---

# 11. Duplicate Case

如果 URL / Source 已经存在：

不重新处理。

显示：

```text
这个案例已经分析过了。

[ 查看已有案例 ]
```

---

# 12. Case Analysis Progress

提交以后进入：

```text
案例分析中

✓ 获取视频
✓ 提取语音
→ 分析画面
○ 理解内容结构
○ 生成审核结果

你可以离开这个页面。
完成后会出现在“任务”中。
```

阶段可以来自真实后台任务状态。

不要为了 UI 创建假的业务 lifecycle。

---

# 13. Case Review

## `/cases/:id`

### Mobile layout

顺序固定：

```text
视频播放器

↓

这个视频在讲什么

↓

它是怎么讲的

↓

值得学习的结构

↓

查看完整拆解

↓

Human Review
```

---

# 14. Case Review — Section 1

播放器下显示：

```text
来源
时长
标题 / 原始描述
```

永久提示：

> **该案例仅用于内部结构研究。批准入库不代表原视频素材可以用于客户生产。**

---

# 15. Case Review — Section 2

标题：

> **这个视频在讲什么**

显示自然语言：

```text
内容主题

核心表达

主要受众
```

---

# 16. Case Review — Section 3

标题：

> **它是怎么讲的**

示例：

```text
开头
从一个具体问题进入

中段
口播推进信息
真实过程画面辅助理解

结尾
形成明确结果或状态
```

---

# 17. Case Review — Section 4

标题：

> **值得学习的结构**

只能表达：

```text
结构观察
信息组织方式
画面角色
叙事节奏
```

不能前端直接宣称：

> 爆款规律
> 已验证高转化结构。

---

# 18. Case Full Breakdown

默认折叠：

> **查看完整拆解**

展开可看到：

* Narration；
* Shot；
* Narration ↔ Shot；
* Visual State；
* Privacy-safe details。

这是高级信息，不是默认首屏。

---

# 19. Case Human Review

Mobile Sticky Bottom：

```text
[ 不收录 ]       [ 批准入库 ]
```

更多：

```text
⋯
退回重新分析
```

退回必须填写原因。

批准后：

```text
已进入案例库
```

不能显示：

> 已获得素材使用权。

---

# 20. Customers

## `/customers`

每个客户使用 Card：

```text
书房市集志泉社区食堂

社区餐饮

客户信息      已批准
出镜人         1
剩余内容空间    7

[ 查看客户 ]

开始创作 ›
```

---

# 21. Customer Detail

## `/customers/:id`

顶部：

```text
客户名称

客户档案：已批准
```

下面两个 Section：

```text
客户信息

出镜人设
```

最后：

```text
内容空间
最近创作
素材状态
```

---

# 22. New Customer

## `/customers/new`

第一版只要求：

### 客户名称

### 行业

### 已有资料

大输入框提示：

> **把你现在已经知道的客户情况粘贴进来。采访记录、门店介绍、服务流程、价格、顾客问题都可以。**

Primary CTA：

> **分析客户信息**

不做巨大字段表。

---

# 23. Customer Information Analysis

后台：

```text
Raw Customer Input
↓
Fact Candidate
```

完成后进入：

# **客户信息审核**

---

# 24. Customer Truth Review

移动端按 Fact Card 审核。

## 已确认

```text
顾客可以买食材后
交给窗口加工。

已确认
```

## 需要确认

```text
未处理干净的鱼
是否一定会产生额外费用？

需要确认

[ 暂不确认 ] [ 确认 ]
```

## 暂时不知道

```text
是否支持提前预约

暂时不知道
```

## 禁止使用

```text
某未经确认的经营数据

禁止用于内容生成
```

---

# 25. Persona Approval

全部关键 Fact Review 完成后：

Primary CTA：

> **确认并建立客户档案**

后台仍走现有：

```text
build persona
↓
Human Approval
```

前端不能绕过正式 Persona lifecycle。

---

# 26. Speakers

Customer Detail：

```text
出镜人设

林东方
主厨 · 一线专业人员
可用于创作

[ 查看 ]

+ 添加出镜人
```

---

# 27. Add Speaker

仅要求：

```text
姓名 / 对外称呼

角色
```

角色：

```text
老板 / 创始人
一线专业人员
品牌官方
其他
```

映射后台：

```text
owner_founder
frontline_expert
brand
generic
```

然后：

> **关于这个人的真实经验和做法**

自然语言输入。

---

# 28. Speaker Truth Review

流程和 Business Fact Review 类似。

特别增加：

> **这个人可以第一人称讲什么？**

以及：

> **哪些事情不能由他本人确认？**

Speaker Approved 后显示：

> **可用于创作**

---

# 29. Speaker Media Rights

单独一块：

```text
出镜授权

当前：待确认
```

不能因为：

```text
人设：可用于创作
```

就显示：

```text
可以露脸
```

---

# 30. Video Creation

主入口：

## `/create`

采用 Mobile 4-step Wizard。

顶部：

```text
1 人设
2 类型
3 数量
4 确认
```

不要让所有配置同时出现。

---

# 31. Step 1 — Customer & Speaker

页面：

> **这批视频为谁创作？**

选择客户。

然后：

> **谁来讲？**

选择 Speaker。

如果只有一个：

默认选中。

显示：

```text
林东方 · 主厨

人设
可用于创作

当前剩余内容空间
7 条
```

---

# 32. Step 2 — Video Type

页面：

> **想做哪种视频？**

第一版只公开两个 Profile。

### 素材混剪 / 口播型

描述：

> 用真实客户信息生成标题和完整口播，适合真人、数字人口播和真实素材混剪。

状态：

```text
可使用
```

---

### 新闻体 / 信息型

描述：

> 把价格、优惠、对比或重要信息组织成短而明确的信息节奏。

展开能力：

```text
已验证
✓ 价格 / 优惠信息型

等待真实业务机会
○ 场景对比型
```

---

# 33. Profile 不可用

如果当前 Customer Truth 没有合适机会：

显示：

```text
当前客户暂时没有适合这种视频类型的新内容。
```

CTA：

> 返回选择其他类型

辅助入口：

> 查看还缺什么客户信息

不能硬生成。

---

# 34. Step 3 — Quantity

页面：

> **这次想生成多少条？**

Stepper / number input：

```text
[-]   4   [+]
```

下面：

> 当前最多支持 **7 条高质量、不重复内容**

---

# 35. Capacity Limited

用户输入 10，Capacity = 7：

```text
你希望生成
10 条

当前内容空间
7 条

为了避免重复，
本轮最多生成 7 条。
```

Primary CTA：

> **生成 7 条**

Secondary：

> 补充客户信息

不允许：

> 仍然生成 10 条。

---

# 36. Step 4 — Confirmation

移动端显示极简摘要：

```text
客户
书房市集志泉社区食堂

出镜人
林东方 · 主厨

视频类型
素材混剪 / 口播

本轮数量
4

当前内容空间
7
```

Sticky CTA：

> **开始生成**

---

# 37. Generation Progress

进入：

```text
正在创作 4 条内容

✓ 检查历史内容
✓ 选择新的内容方向
→ 匹配表达结构
○ 生成文案
○ 安全检查
```

允许：

> 返回工作台

并显示：

> 任务会继续执行。

---

# 38. Tasks

## `/tasks`

手机端统一任务卡。

类型：

```text
案例分析
客户信息分析
视频创作
```

状态：

```text
处理中
等待审核
已完成
失败
```

示例：

```text
林东方 · Mix

4 条内容

等待审核

刚刚完成

[ 去审核 ]
```

---

# 39. Content Review

## `/create/:requestId`

或：

## `/batches/:id`

移动端一条内容一个完整 Card。

顶部：

```text
01 / 04
```

显示：

### 标题

### 完整口播

### 为什么生成这条

示例：

> 这是此前没有表达过的真实服务实例。

---

# 40. Content Evidence

默认折叠：

> **查看内容依据**

展开使用业务语言：

```text
✓ 来自已确认的客户信息

✓ 来自林东方本人的真实做法

✓ 此前未被正式使用
```

不要展示：

```text
Fact Atom
SHA
central_claim_key
pattern_ref
```

---

# 41. Content Review Actions

Mobile Sticky Bottom：

```text
[ 不通过 ]       [ 通过 ]
```

菜单：

```text
编辑文案
```

---

# 42. Editing Content

全屏编辑：

```text
编辑标题

编辑口播
```

允许编辑：

```text
title
narration
```

不允许编辑：

```text
Concept
Central Claim
Fact Authority
Pattern
Persona Reference
```

保存后必须重新跑现有 Guard。

---

# 43. Edited Content Guard Failure

如果编辑产生风险：

```text
这次修改暂时不能通过。

原因：
“15分钟”变成了普遍承诺。

建议：
保留“这一次”的限定。
```

用户可以继续编辑。

不能批准。

---

# 44. Partial Approval Principle

产品设计冻结：

> **长期允许只批准通过的内容。**

例如：

```text
4 条生成

3 条通过
1 条不通过
```

可以批准：

> 3 条。

不允许为了凑齐 4 条：

> 自动再补一条。

如果当前 backend batch contract 一期不能安全支持 partial approval：

V1 implementation 可以暂时整批 Gate。

但：

> **不要在 UI / Schema 冻结“必须全批批准”作为长期产品规则。**

---

# 45. Approved Result

批准后进入：

## `/batches/:id`

显示：

```text
本批内容已批准

4 条内容
```

Primary：

> **下载 Excel**

Secondary：

> 查看内容

Next：

> 准备视频素材

---

# 46. Result Preview

每条：

```text
01

三只梭子蟹加年糕，
那一单前后大约15分钟

[ 展开口播 ]

复制标题
复制口播
```

手机端不需要打开 Excel 才能查看内容。

---

# 47. Excel

Mix：

保持现有：

```text
标题
口播内容
```

News：

保持已有 News Contract。

前端：

> 不自定义 Excel schema。

---

# 48. Footage Planning Entry

Approved Result 页显示：

> **下一步：准备视频素材**

进入后显示：

```text
4 条视频

都还需要补拍素材

[ 查看补拍清单 ]
```

或者：

```text
视频 1

三只梭子蟹加年糕

需要：
三只梭子蟹
年糕
加工过程
完成 / 打包

状态：
等待素材
```

---

# 49. 当前 Footage MVP Boundary

V1 Frontend Stop Point：

允许：

* 查看 Capture Missions；
* 查看 Capture Pack；
* 下载 / 复制补拍说明。

暂不要求：

* Production Asset Upload；
* Visual Analysis UI；
* Asset Matching；
* Storyboard Coverage Update；
* Editing。

这些留给 Production Asset Intake 真正开发时再进入前端。

---

# 50. Empty States

## No Cases

```text
案例库还是空的

先添加几个真实视频，
让系统学习内容结构。

[ 添加案例 ]
```

---

## No Customers

```text
还没有客户

先把一个真实客户的信息整理进来。

[ 新建客户 ]
```

---

## No Speaker

```text
还没有可用于创作的出镜人

[ 添加出镜人 ]
```

---

## No Tasks

```text
暂时没有任务

新的案例分析和视频创作
都会出现在这里。
```

---

# 51. Loading States

禁止大面积永久 Spinner。

使用：

```text
Skeleton
+
当前执行阶段
```

超过数秒的任务：

> 转成 Async Task。

---

# 52. Errors

错误必须告诉用户：

> 发生了什么 + 下一步怎么办。

例如：

### Case source error

```text
暂时无法读取这个视频。

你可以：
重新尝试
检查链接
```

---

### Generation failure

```text
这批内容没有全部生成完成。

成功 3 条
失败 1 条

已完成的内容不会丢失。
```

不得为了修复：

> 自动换 Concept 补齐。

---

### Export failure

```text
Excel 导出失败。

已批准内容仍然安全保存。

[ 重新导出 ]
```

不能重新生成内容。

---

# 53. Mobile Interaction Rules

手机端：

* 44px+ 触控目标；
* 输入区避免键盘遮挡 CTA；
* Sticky Bottom Bar 避让 safe area；
* 页面标题保持简短；
* Card 内不堆多列；
* 长正文可自然滚动；
* 审核操作始终容易到达；
* 状态不能只靠颜色表示。

---

# 54. Desktop Adaptation

> = 1024px 后：

底部导航 → 左侧导航。

案例审核：

```text
视频
│
分析内容
```

可以双栏。

Content Review：

可以：

```text
左侧内容列表
右侧当前审核内容
```

Customer Detail：

Business / Speaker 可以并排。

但：

> Flow 顺序和按钮语义不变。

---

# 55. Recommended Breakpoints

不冻结具体 CSS 实现，但建议验收：

```text
390px
430px
768px
1280px+
```

390px：

> 必须完整可操作。

---

# 56. Frontend Route Freeze

建议 V1：

```text
/login

/change-password

/workbench

/cases
/cases/new
/cases/:caseId

/customers
/customers/new
/customers/:customerId

/customers/:customerId/speakers/new
/customers/:customerId/speakers/:speakerId

/create
/create/:requestId

/tasks

/batches/:batchId
```

不继续扩 Route。

---

# 57. Frontend Authority Mapping

| UI 信息     | Authority                                |
| --------- | ---------------------------------------- |
| 客户档案可用    | Approved Business Persona                |
| 出镜人设可用    | Approved Speaker Persona                 |
| 剩余内容空间    | Content Capacity Derived Artifact        |
| 是否新内容     | Content Ledger + Gate Resolver           |
| 可选视频类型    | Production Profile + current coverage    |
| 案例已入库     | Approved Case lifecycle                  |
| Batch 已批准 | Batch Human Approval                     |
| Excel 已导出 | Export Receipt                           |
| 等待素材      | Footage Coverage                         |
| 出镜权限      | Subject Media Authorization              |
| 当前下一动作    | Status Read Model / Next Action Resolver |

前端不能拥有这些事实。

---

# 58. Web App Application Layer

因为现有核心能力主要是 CLI / Artifact Pipeline，所以前端不能直接调用脚本路径。

需要增加一个非常薄的 Application Layer：

```text
Web UI
↓
Internal API / Application Service
↓
Canonical Operations
↓
Existing Authority / Pipeline
```

Application Layer 负责：

* Auth；
* 用户 Session；
* Task orchestration；
* 调用现有 canonical operations；
* 返回 read model；
* Async job status。

它不负责：

* 重新实现 Persona；
* 重新实现 Novelty；
* 重新实现 Case；
* 重新实现 Content Ledger；
* 重新实现 Pattern；
* 重新实现 Footage Authority。

---

# 59. Internal Database Scope

V1 数据库只允许承载：

### User Account

```text
phone
password_hash
must_change_password
status
created_at
updated_at
```

### Session / Auth

按技术栈选择。

### Async Task Projection

例如：

```text
task_id
task_type
subject_ref
status
progress
error
created_at
updated_at
```

### UI / orchestration references

必要时保存：

```text
business_id
request_id
case_id
```

但只是 reference。

---

# 60. Database 禁止成为第二套业务真源

禁止复制：

```text
Persona Truth
Content Capacity
Ledger
Pattern
Case lifecycle
Batch Authority
Rights Authority
```

然后让数据库成为新 Authority。

数据库中的 Task：

> 只表示“这个异步动作跑到哪里”。

不是：

> “业务已经批准到哪里”。

---

# 61. Authentication Security Freeze

即使是内部 MVP：

* 密码必须哈希；
* 默认密码不得明文持久化；
* 首次登录强制修改；
* 无公开 registration API；
* 登录失败不要泄露手机号是否存在；
* Session 优先 HttpOnly Cookie；
* Production 环境要求 HTTPS；
* 密码不得写进日志。

---

# 62. Account Provisioning

V1 不做账号管理 UI。

提供一个内部管理员操作，例如：

```text
create_internal_user
```

或使用当前后端框架的安全 provisioning method。

输入：

```text
phone
initial_password = 123456
```

创建：

```text
must_change_password = true
```

不要要求运营人员直接手写 SQL 作为长期流程。

---

# 63. Backend APIs 不冻结 URL，冻结行为

不要现在锁死大量 endpoint。

只冻结 Capability Boundary。

至少需要能力：

```text
auth.login
auth.changePassword
auth.logout

status.getCustomerStatus

cases.list
cases.createAnalysis
cases.get
cases.review

customers.list
customers.createIntake
customers.get
customers.reviewFacts

speakers.create
speakers.get
speakers.review

content.getCapacity
content.createGeneration
content.getGeneration
content.review
content.approve

exports.create
exports.download

footage.getPlanning

tasks.list
tasks.get
```

Codex 可根据实际技术栈设计 REST route。

---

# 64. Async Task Principle

以下默认 Async：

* Case acquisition / analysis；
* Customer intake extraction；
* Generation；
* Excel export，如果耗时明显；
* 后续 Asset Analysis。

Async Job：

```text
queued
running
review_required / completed
failed
```

这里只是 Task 状态。

不能覆盖业务 lifecycle。

---

# 65. MVP 非目标

这一版明确不做：

* Public Registration；
* SMS；
* Forgot Password；
* RBAC；
* Multi-tenant SaaS；
* Customer portal；
* Pattern 管理后台；
* Case research 管理全功能；
* Asset Upload；
* Video Editing；
* Publishing；
* Analytics Dashboard；
* Performance Learning；
* Social account connection；
* AI Chat。

---

# 66. Frontend MVP Stop Point

一期只有满足下面真实流程，才算完成：

> **内部账号登录**
>
> → 手机端粘贴一个真实 URL
>
> → 案例分析
>
> → 手机端 Human Review
>
> → Approved Case
>
> → 新建 / 选择客户
>
> → 新建 / 选择出镜人
>
> → Fact / Persona Human Review
>
> → 选择 Mix / 当前可用 News
>
> → Quantity + Capacity Gate
>
> → Generate
>
> → Human Review
>
> → Approve
>
> → Content Preview
>
> → Excel Download
>
> → 查看 Footage Preparation

达到这里：

# STOP。

不要顺手继续 Asset Intake 或自动剪辑。

---

# 67. 产品验收核心

V1 不以：

> “页面全部做完”

作为 PASS。

而以：

> **一个真实运营人员能否只拿手机，从 URL → Case → Persona → Content → Excel 跑完一次真实工作。**

作为 PASS。

---

# 68. Frozen Product Decision

这份设计从现在开始作为：

# **AI Video Ops MVP V1｜Internal Console UX & Interaction Freeze V1.0**

后续 Codex 可以根据真实代码做技术适配。

但未经重新审批，不得改变：

* Mobile-first；
* 无公众注册；
* Human Gates；
* Business/Speaker 分离；
* 4-step Creation Wizard；
* Capacity / No Padding；
* Case Governance；
* Status Projection；
* Excel 前 Human Approval；
* Frontend MVP Stop Point。
