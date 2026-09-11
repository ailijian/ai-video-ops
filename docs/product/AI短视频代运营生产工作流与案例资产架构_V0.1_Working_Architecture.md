# AI 短视频代运营生产工作流与案例资产架构 V0.1｜Working Architecture

> **Status**：Working Architecture  
> **Maturity**：MVP Validation  
> **Planning Ready**：No  
> **Frozen**：No  
> **适用对象**：产品、运营、内容、AI 工程、未来 Codex 实施者  
> **目的**：在产品化之前，约束“人工 + 脚本 + AI”验证过程，沉淀稳定架构原则、已验证事实、候选方案与开放问题；避免边实验边漂移，也避免过早把尚未验证的实现细节冻结为长期事实。

---

## 0. 文档使用规则

本文不是 PRD，不是数据库 Schema，不是 Codex 实施计划，也不是最终冻结版。

本文只承担四件事：

1. 定义这套 AI 短视频代运营生产系统长期不应轻易改变的架构原则；
2. 记录目前已经通过真实案例、脚本和运行环境验证的结论；
3. 给接下来的人工 / 脚本 MVP 提供统一边界；
4. 为未来 Codex 产品化提供稳定的上下文入口，减少重新理解与设计漂移。

### 0.1 状态标签

- **[Stable Principle]**：当前认为具有长期稳定性的架构原则；未来即使换模型、换工具、换 UI，也应优先保持。
- **[Validated]**：已经通过当前真实案例、脚本或运行环境验证。
- **[Candidate]**：当前推荐方向，但还需要更多真实业务验证。
- **[Open Question]**：尚未决定，不得被实现者自行升级为事实。
- **[Not Frozen]**：明确禁止现在冻结的参数、模型、阈值或 UI 细节。
- **[Source-derived Business Fact]**：直接来自当前公司会议纪要或已确认输入，不由本架构文档重新设计。

### 0.2 未来升级条件

只有当“案例逆向 → Pattern → Persona → 新脚本 → 发布文案 → 3 类 Excel → 现有生成系统 → 成片 → 人工验收”至少完整跑通一次，并完成一轮真实业务复盘后，本文才进入：

```text
Working Architecture V0.x
↓
Freeze Review
↓
AI 短视频代运营生产工作流 V1.0
Status: Approved / Frozen
↓
Delivery Baseline
↓
Implementation Plan
↓
Codex 产品化
```

---

# 1. 业务基线

## 1.1 业务定位

**[Source-derived Business Fact]**

当前公司方向不是单纯“卖工具”或“卖课件”，而是面向本地线下实体门店与服务行业提供结果导向的 AI 短视频代运营能力。

当前业务交付强调“重前期、轻后期”：

```text
团队：
人设搭建
+ 文案库
+ 素材分组
+ 自动化配置
+ 投流方案

客户：
提供资料
+ 按要求拍素材
+ 完成必要的登录 / 启停 / 互动动作
```

长期商业路径是：

```text
先跑通直客 SOP
↓
形成可复制交付
↓
再向代理商输出产品 + 解决方案
```

## 1.2 当前内容生产重点

**[Source-derived Business Fact]**

当前视频内容至少包含两类主要生产方式：

1. **新闻体**
   - 超短内容；
   - 前期冷启动高频使用；
   - 重点是画面文字 / 标题结构；
   - 当前已有独立 Excel 导入结构。

2. **混剪**
   - 包括人设型、故事型、高转化型等；
   - 更依赖完整旁白、字幕、人物动作、场景、商品、经营过程；
   - 当前已有独立“视频制作标题 + 口播内容”导入结构。

发布文案属于独立的第三类输出：

```text
视频发布标题
视频发布正文
视频话题
```

## 1.3 当前人工交付目标

**[Source-derived Business Fact]**

当前李健相关工作聚焦：

- 反推文案结构与提示词；
- 形成新闻体 / 故事型 / 高转化型文案资产；
- 构建不同行业的分组镜头名称与 3–5 秒参考案例；
- 将经验沉淀为可复制资产，而不是每个客户重新手工制作。

---

# 2. 系统北极星

## 2.1 核心目标

**[Stable Principle]**

这套系统不以“自动生成更多视频”为第一目标，而以：

> **把真实有效的短视频案例转化为可追溯、可学习、可匹配、可批量复用的公司内容资产，并最终根据不同客户人设持续生成可执行的视频生产脚本。**

为核心目标。

## 2.2 最重要的公司资产

**[Stable Principle]**

长期真正积累价值的不是 AI 每天生成的几百条文案，而是：

```text
Case Library
+
Pattern Library
+
效果反馈数据
```

其中：

- **Case Library**：真实案例事实库；
- **Pattern Library**：从多个案例中抽象出的可复用规律库；
- **效果反馈数据**：证明 Pattern 在什么行业、什么人设、什么平台、什么目标下有效。

生成内容本身属于消耗品。

案例、Pattern 与效果学习能力才是复利资产。

---

# 3. 总体生产架构

**[Stable Principle]**

完整工作流分为七层：

```text
Layer 1｜Source
真实案例与客户真实信息

Layer 2｜Evidence
声音、画面、文字、时间、Metadata

Layer 3｜Understanding
单案例内容理解

Layer 4｜Pattern
跨案例规律提炼

Layer 5｜Generation
Persona → 新文案 / 新分镜 / 发布文案

Layer 6｜Production
Excel / 配音 / BGM / 混剪 / 发布

Layer 7｜Feedback
投流 / 效果数据 / Pattern 强化与淘汰
```

关键原则：

> **越靠近 Source / Evidence，越追求“不能错”；越靠近 Generation，越允许 AI 做创造。**

---

# 4. 人、AI、开源软件与业务系统的职责边界

## 4.1 人工

**[Stable Principle]**

人工负责有责任含义的判断：

- 客户事实；
- 商业承诺；
- 内容合规；
- 案例是否值得进入正式库；
- Pattern 是否值得复用；
- 声音授权；
- 音乐版权；
- 审美；
- 广告预算；
- 最终质量 Gate；
- 异常处理。

人工不应长期承担：

- 批量下载；
- 转码；
- ASR；
- 文件映射；
- 时间对齐；
- Excel 格式转换；
- 大规模标签填写。

## 4.2 AI

**[Stable Principle]**

AI 负责：

- 视觉理解；
- 语义分类；
- 单案例结构理解；
- Pattern Mining；
- Persona 与 Case / Pattern 语义匹配；
- 文案生成；
- 生产分镜生成；
- 发布文案生成；
- 配音导演建议；
- BGM 运营语义判断；
- 数据复盘。

AI 不拥有：

- 原始证据修改权；
- 时间真值；
- Case ID；
- 文件对应关系；
- 授权事实；
- 商业结果事实；
- Approved 权限。

## 4.3 确定性软件 / Python

**[Stable Principle]**

程序负责：

- ID；
- 时间；
- 文件；
- 数据完整性；
- 去重；
- 格式转换；
- 映射；
- 状态机；
- 批处理；
- Resume；
- 验证；
- Excel 生成。

一句话：

> **事实结构由程序保证，语义理解由模型完成。**

## 4.4 业务系统

当前已有视频生成 / 发布系统继续负责：

- 视频生成；
- 自动合成；
- 任务计划；
- 发布；
- 后续设备执行。

**[Candidate]**

未来新的内容生产系统优先通过稳定的输入 Contract 与现有系统对接，而不是重新开发一套视频发布执行系统。

---

# 5. 两个核心前端入口

## 5.1 Surface A｜上传案例

**[Candidate Product Flow]**

用户登录前端后：

```text
上传案例
↓
选择分析类型
新闻体 / 混剪
↓
粘贴抖音分享链接
↓
系统采集
↓
逆向分析
↓
生成 Candidate Case
↓
自动质量检查
↓
人工 Review
↓
Approved Case
↓
进入公司案例库
```

### 关键规则

**[Stable Principle]**

用户选择的“新闻体 / 混剪”是：

> **Analysis Profile**

而不是不可质疑的事实。

如果用户选择新闻体，但系统检测到明显长口播、多场景和复杂行动，应提示重新确认分类。

## 5.2 Surface B｜获取视频脚本

**[Candidate Product Flow]**

```text
登录
↓
获取视频脚本
↓
创建 / 选择 Video Persona
↓
选择生成数量
↓
选择：
新闻体 / 混剪 / 两种都生成
↓
匹配 Approved Case + Approved Pattern
↓
生成 Production Script
↓
质量检查
↓
生成 Publishing Copy
↓
确定性格式化
↓
导出 3 类 Excel
↓
下载 / 导入现有系统
```

### 当前候选 UI 需求

**[Candidate / Not Frozen]**

- 一个账号可创建最多 10,000 个 Video Persona；
- 生成数量以 100 条为单位；
- 通过 `+ / -` 调整；
- 两种都生成时必须明确“新闻体 100 + 混剪 100”，而不是模糊的“总计 100”。

这些属于产品参数，不在 V0.1 冻结。

---

# 6. Case Library

## 6.1 Case 是什么

**[Stable Principle]**

Case 不是“视频标题 + 一段脚本”。

Case 是：

> **一个真实视频经过证据保真、结构化理解后形成的可追溯案例资产。**

如果只能在“脚本”和“分镜”二选一：

> **Canonical Truth 采用结构化分镜；Markdown / 表格脚本只是展示层。**

## 6.2 Case 概念结构

**[Candidate Schema Concept]**

```text
CASE
│
├── Identity
│   ├── case_id
│   ├── source_url
│   ├── source_platform
│   ├── content_profile
│   ├── industry
│   ├── duration
│   └── status
│
├── Source Evidence
│   ├── video
│   ├── original_audio/music
│   ├── cover
│   └── source_metadata
│
├── Audio Evidence
│   ├── transcript_raw
│   ├── transcript_segments
│   ├── word_timestamps
│   └── srt
│
├── Visual Evidence
│   ├── candidate_frames
│   ├── frame_timestamps
│   ├── OCR
│   ├── observable_scene
│   └── visual_timeline
│
├── Unified Evidence
│   ├── deterministic_timeline
│   └── semantic_relations
│
├── Understanding
│   ├── content_goal
│   ├── hook
│   ├── claim
│   ├── explanation
│   ├── proof
│   ├── CTA
│   └── audio_visual_strategy
│
├── Shots[]
│   ├── start/end
│   ├── voiceover
│   ├── onscreen_text
│   ├── observable_visual
│   ├── shot_role
│   └── source_evidence_refs
│
└── Pattern Candidates
```

**[Not Frozen]**

字段命名、数据库实现、JSON Schema 暂不冻结。

## 6.3 Case 生命周期

**[Stable Principle]**

```text
candidate
↓
analyzed
↓
review_required
↓
approved
↓
retired
```

规则：

- 只有 `approved` Case 可以参与正式生成；
- AI 不得自行把 Case 标记为 `approved`；
- 原案例失效不自动抹掉内部分析资产；
- 分析逻辑重大升级时可重新分析同一 Source，但必须保留分析版本。

---

# 7. Pattern Library

## 7.1 Case ≠ Pattern

**[Stable Principle]**

禁止：

```text
发现一个案例
↓
直接把它定义为爆款模板
```

正确关系：

```text
Case A ─┐
Case B ─┤
Case C ─┼→ Pattern Candidate
Case D ─┤
Case E ─┘
           ↓
效果 / 人工验证
           ↓
Approved Pattern
```

## 7.2 Pattern 分类

**[Candidate]**

未来至少考虑：

- Copy Pattern：文案结构；
- Shot Pattern：镜头结构；
- Hook Pattern：开场结构；
- Proof Pattern：证明结构；
- CTA Pattern：转化结构；
- Audio-Visual Pattern：音画分工；
- Industry Pattern：行业特有规律。

## 7.3 Pattern 数据建议

```text
Pattern
├── pattern_id
├── pattern_type
├── source_case_ids[]
├── applicable_content_types[]
├── applicable_industries[]
├── applicable_goals[]
├── required_persona_attributes[]
├── required_materials[]
├── forbidden_conditions[]
├── pattern_structure
├── diversity_group
├── validation_status
└── performance_summary
```

**[Not Frozen]**

需要多少 Case 才能形成 Pattern、效果达到什么水平才能 Approved，目前不冻结。

---

# 8. Evidence Core

## 8.1 总原则

**[Stable Principle]**

所有分析类型共享一套 Evidence Core：

```text
Source
↓
Download
↓
Metadata
↓
Audio Evidence
↓
Visual Evidence
↓
Deterministic Timeline
↓
Canonical Case
```

新闻体与混剪不维护两套基础系统。

## 8.2 当前已经真实验证的工具链

**[Validated / Implementation Detail / Not Frozen]**

当前 Windows MVP：

```text
Douyin source
↓
jiji262/douyin-downloader

Audio
↓
faster-whisper large-v3
RTX 4060 / CUDA

Visual candidate frames
↓
PySceneDetect + OpenCV

Visual understanding
↓
Qwen3-VL 4B via Ollama

Time alignment
↓
Deterministic Python

Semantic fusion
↓
DeepSeek V4 Flash

Reverse storyboard
↓
DeepSeek V4 Flash
```

这些工具当前有效，但模型名、版本和供应商不属于长期 Frozen Fact。

---

# 9. 当前逆向分析 MVP 的验证结论

## 9.1 下载层

**[Validated]**

已经真实跑通：

```text
抖音分享链接
↓
MP4
MP3 / music
Cover
Metadata JSON
```

## 9.2 Audio Evidence

**[Validated]**

`faster-whisper small` 曾将“执行力超强的自己”误识别为“执行力超强了自己”。升级到 `large-v3 + CUDA + float16` 后正确识别。

当前 MVP 生产 ASR 默认使用 large-v3。

**[Not Frozen]**：模型本身未来允许替换。

## 9.3 Visual Evidence

**[Validated]**

Qwen3-VL 4B 已经验证可完成：

- 中文画面文字 OCR；
- 人物 / 动作 / 环境识别；
- 多帧按时间顺序理解；
- 区分轻微视觉变化与信息变化。

同时发现：

- 模型可能推断人物性别 / 身份；
- 可能把衣物误认定为“商品”；
- 可能把经营动作升级为“成功证据”；
- 纯视觉模型在没收到 Audio 时，不能声称“视频没有旁白”。

因此：

> **Observation 与 Interpretation 必须分层。**

## 9.4 自由 LLM 时间融合失败

**[Validated Failure]**

实验曾直接将 Audio + Visual 交给模型自由融合，结果出现：

- 3.6 秒 source frame 被放入 0–2 秒；
- Whisper 存在的句子被漏掉；
- Visual Sampling 漏信息但模型仍声明 coverage high；
- Evidence 来源被误当成视频内容 Evidence。

结论：

**[Stable Principle]**

> **LLM 不拥有时间对齐权。**

## 9.5 Deterministic Timeline

**[Validated]**

当前已改为：

```text
Audio timestamps
+
Visual frame timestamps
↓
Python
↓
Raw Unified Timeline
↓
LLM Semantic Fusion
```

并验证 `All audio evidence preserved: YES`。

## 9.6 Reverse Storyboard

**[Validated MVP]**

当前已经真实得到“时间、旁白、画面文字、可观察画面、镜头作用”构成的逆向分镜。

当前结果属于：

> **Representative Storyboard**

而不是：

> **Frame-complete Storyboard**

因为当前 Visual Timeline 只分析 34 个候选帧中的 8 个代表帧。

---

# 10. 新闻体与混剪：一套 Core，两套 Profile

## 10.1 统一原则

**[Stable Principle]**

```text
Evidence Core
        ↓
┌───────────────┐
│               │
News Profile    Mix Profile
│               │
↓               ↓
News Script     Shot Script
```

## 10.2 News Profile

**[Candidate]**

新闻体重点：

- 6–8 秒等超短时长；
- 高密度画面文字；
- 标题出现顺序；
- OCR 变化；
- 地域 / 行业 / 商家 / 冲突；
- Hook；
- 新闻化 framing；
- 最终映射到 6 个标题 Slot。

新闻体采样可更密，例如 0.25–0.5 秒；如果确认无有效语音，可跳过高成本 ASR。

最终 Canonical Output 倾向：

```text
news_script
├── title_1
├── title_2
├── title_3
├── title_4
├── title_5
└── title_6
```

具体规则需要专项实验。

## 10.3 Mix Profile

**[Candidate]**

重点：

- 完整旁白；
- 字幕；
- 镜头；
- 人物；
- 动作；
- 环境；
- 产品；
- 音画关系；
- 情绪 / 人设；
- 真实 Proof；
- CTA。

输出核心为 `shots[]`。

---

# 11. 镜头角色词典

**[Candidate → High Priority Validation]**

当前需要统一镜头角色，否则模型会把“干活画面”滥标为 Evidence。

推荐基础枚举：

```text
hook
context
action
persona
product
claim
explanation
emotion
proof
transition
payoff
CTA
other
```

### Proof 严格定义

**[Stable Principle]**

只有能直接支持某项 Claim 的可验证事实才属于 Proof，例如：

- 数据；
- 订单；
- 后台截图；
- 客户评价；
- 前后对比；
- 实物效果；
- 明确结果；
- 证书；
- 可核验案例事实。

以下不是 Proof：

- 老板在工作；
- 顾客坐在店里；
- 员工正在施工；
- 人物正在做饭。

这些最多属于 `action / context / persona / product`。

---

# 12. Persona 资产

## 12.1 Persona 的角色

**[Stable Principle]**

Video Persona 不是一段自由文本 Prompt，而应该成为生成阶段的结构化输入事实。

至少需要表达：

```text
客户 / 品牌是谁
做什么
服务哪里
目标客户是谁
客户痛点
核心产品
差异化
可信事实
真实案例
品牌故事
经营者经历
表达风格
禁忌
可拍素材
CTA 约束
```

## 12.2 Persona 与 Case 的关系

**[Stable Principle]**

Persona 不直接决定“模仿哪一个视频”。

正确关系：

```text
Persona
↓
Retrieve Case Portfolio
+
Retrieve Pattern Portfolio
↓
生成
```

---

# 13. Persona → Case / Pattern 匹配

## 13.1 总体算法

**[Stable Principle]**

不是 `Persona → Embedding → Top 1 Case → 仿写`，而是：

```text
Hard Filter
↓
Semantic Recall
↓
Structural Rerank
↓
Diversity Control
↓
Case + Pattern Portfolio
```

## 13.2 Hard Filter

至少包括：

- Case 必须 Approved；
- Pattern 必须可用于当前生成任务；
- 视频类型兼容；
- 合规；
- 客户禁忌不冲突；
- 素材可执行；
- 平台约束；
- 不能要求客户不存在的 Proof。

## 13.3 Semantic Recall

**[Candidate Weighting]**

| 维度 | 候选权重 |
|---|---:|
| 内容目标 | 25% |
| 目标客户 / 痛点 | 20% |
| 产品 / 价值主张 | 15% |
| 可拍素材 / 执行性 | 15% |
| Persona 表达风格 | 10% |
| 行业接近度 | 10% |
| CTA / Proof 条件 | 5% |

**[Not Frozen]**：具体权重必须通过真实生成与效果数据迭代。

## 13.4 Portfolio 而非单案例

**[Stable Principle]**

生成 100 条视频，不允许只围绕一个案例改写。

候选方式：

```text
Persona
↓
召回 30–50 Case / Pattern Candidates
↓
重排
↓
挑选多样化 Portfolio
↓
生成 100 条
```

## 13.5 多样性控制

**[Candidate]**

后续考虑：

- 单 Case 最大复用比例；
- 单 Pattern 最大复用比例；
- Hook 重复度；
- CTA 重复度；
- 内容主题覆盖；
- 场景覆盖；
- 句式相似度；
- 连续批次 Novelty。

具体阈值暂不冻结。

---

# 14. 生产脚本生成

## 14.1 Production Script

**[Stable Principle]**

生产脚本不是简单改写案例，而应该消费：

```text
Persona Truth
+
Approved Cases
+
Approved Patterns
+
用户生成要求
+
素材约束
```

输出至少包含：

```text
Content ID
内容类型
来源 Case IDs
来源 Pattern IDs
Production Script
Shots
Voiceover
Onscreen Text
Required Materials
Proof Requirements
CTA
Quality Metadata
```

## 14.2 Publishing Copy

**[Stable Principle]**

发布文案必须在 Production Script 稳定之后生成。

正确链路：

```text
Production Script
↓
Quality Check
↓
Publishing Copy
↓
Formatter
```

不建议和视频制作脚本混在一次自由生成结果里，但可以在 API 层批量处理。

---

# 15. 三类 Excel 输出 Contract

**[Stable Principle]**

语言模型输出结构化 JSON。

Python / Formatter 负责最终 Excel。

LLM 不拥有 Excel Schema。

## 15.1 新闻体视频制作 Excel

当前真实系统字段：

```text
标题1
标题2
标题3
标题4
标题5
标题6
```

## 15.2 素材混剪 / 数字人口播混剪 Excel

当前真实系统字段：

```text
视频制作标题
视频制作口播内容
```

## 15.3 发布文案 Excel

当前真实系统字段：

```text
视频发布标题
视频发布正文内容
视频话题
```

## 15.4 Content ID 与追溯

**[Stable Principle]**

每条生成内容必须拥有 `content_id`。

内部至少可以追溯：

```text
content_id
→ persona_id
→ case_ids[]
→ pattern_ids[]
→ production_script_version
→ publish_copy_version
→ prompt/model version
→ batch_id
→ 后续真实效果
```

即使现有 Excel 不允许新增列，也应另存 `batch_manifest.json`，否则后续无法从真实效果反向学习。

---

# 16. Voice Production Layer

**[Candidate Architecture]**

```text
Production Script
↓
Voice Decision
↓
Voice Plan
↓
授权声音
↓
TTS
↓
Duration Fit
↓
Audio Post
↓
Human Gate
```

候选 Voice Mode：

```text
NO_VOICE
STANDARD_AI_VOICE
CUSTOMER_AUTHORIZED_VOICE
```

### 核心原则

**[Stable Principle]**

- 不允许未经授权克隆案例视频中的真人声音；
- 案例声音可以研究“语速、情绪、节奏、声线类型”；
- Persona 内容优先考虑客户本人授权音色；
- 公司可建立少量长期授权标准音色。

**[Candidate / Not Frozen]**：CosyVoice 作为当前优先 TTS 候选；具体模型、部署方式和 Voice Schema 尚未验证。

---

# 17. BGM Production Layer

**[Candidate Architecture]**

```text
Production Script
+
Voice Plan
↓
Music Decision
↓
Approved Music Library
↓
BGM Plan
↓
Beat / Segment
↓
Voice Ducking
↓
Final Audio Mix
```

### 两套音乐资产

**[Stable Principle]**

1. **案例音乐研究库**：学习真实案例怎么使用音乐；不意味着可以复制用于商业生产。
2. **公司生产音乐库**：必须具备明确商业使用权；AI 只能从 approved rights asset 中选择。

### 自动音乐分析方向

**[Candidate]**

未来可以自动获得：

```text
identity
BPM
beat
downbeat
segment
chorus / intro
mood
energy
vocal / instrumental
video suitability
```

工具候选包括 Metadata、音频指纹、all-in-one-infer、librosa、CLAP、audio-separator；均未作为 V0.1 Frozen Dependency。

---

# 18. 完整 AI 短视频代运营业务闭环

**[Working Architecture]**

```text
01 客户筛选
人工

02 客户资料 / Persona
人工事实 + AI 整理

03 案例发现
人工 / AI

04 案例采集
开源工具

05 Audio / Visual Evidence
开源模型 + 程序

06 Case Reverse Engineering
程序 + AI

07 Case Review
人工 Gate

08 Pattern Mining
AI + 人工 Gate

09 Persona Matching
检索 + AI

10 Production Script
AI

11 Script Quality Review
规则 + AI + 人工抽检

12 Publishing Copy
AI

13 Excel Formatting
Python

14 客户素材拍摄
客户 + 拍摄说明书

15 Voice
AI 导演 + TTS + 人工 Gate

16 BGM
Music Library + 算法 + AI + 人工 Gate

17 视频合成
现有业务系统

18 发布
现有业务系统 / 人工异常处理

19 投流
人工主导 + 平台

20 数据回流
API / 导出

21 Pattern Evaluation
程序 + AI

22 Pattern 强化 / 淘汰
AI 建议 + 人工 Gate
```

---

# 19. “人工 + 脚本”模式必须长期可运行

**[Stable Principle]**

产品化不是业务开始运行的前置条件。

在产品开发完成前，公司必须能够通过：

```text
PowerShell
Python
Excel
飞书
AI API
现有生成系统
```

完成真实交付。

理由：

1. 业务先于 UI；
2. 脚本可以更快验证真实 Workflow；
3. 产品化只自动化已经成立的流程；
4. 避免 Codex 把未经验证的假设大规模写进产品；
5. 即使产品故障，公司也保留人工运行能力。

---

# 20. 当前 MVP 状态

## 20.1 已跑通

**[Validated]**

```text
✅ 抖音链接解析
✅ 视频 / Music / Cover / Metadata 下载

✅ Whisper GPU ASR
✅ transcript_raw
✅ segment / word timestamp
✅ SRT

✅ Visual Candidate Frames
✅ Qwen OCR
✅ Qwen Visual Observation
✅ Multi-frame Visual Timeline

✅ Deterministic Audio / Visual Timeline
✅ Semantic Fusion
✅ Reverse Storyboard JSON
✅ Reverse Storyboard Markdown
```

## 20.2 已知缺陷

**[Validated / Pending Fix]**

### Visual Coverage

当前一条案例：

```text
34 Candidate Frames
↓
只选择 8 个进行深度视觉分析
```

因此当前结果是 Representative Storyboard。

待优化：

```text
Candidate Frames
↓
分块
↓
Qwen 多段分析
↓
完整 Visual Timeline
```

### Audio Boundary

当前展示主要使用 Whisper Segment，因此横跨 Shot Cut 的 Segment 会重复。

待优化：`Word-level Timeline`。

### Semantic Role

当前模型曾把处理食材、做饭、与顾客互动错误标为 Evidence，待通过 Role Dictionary 与 Schema 修正。

---

# 21. Quality Gates

## 21.1 Evidence Gate

**[Stable Principle]**

必须保证：

- 原始视频不可被 AI 改写；
- transcript_raw 不被覆盖；
- OCR Raw 与 AI Interpretation 分离；
- 每个 Frame 保存真实 timestamp；
- 每个 Audio Token / Segment 可追溯；
- 模型不能生成不存在的 source reference。

## 21.2 Timeline Gate

必须自动验证：

```text
所有 Audio Evidence 被保留
所有 source_frame 时间合法
Timeline 不允许 LLM 重写
不存在 interval 越界映射
```

## 21.3 Case Approval Gate

Case 进入公司正式案例库前至少检查：

- Source 可追溯；
- Audio Coverage；
- Visual Coverage；
- OCR 质量；
- Timeline Alignment；
- Hallucination；
- 分类是否正确；
- 逆向分镜是否基本还原原视频。

## 21.4 Pattern Gate

Pattern 不应只凭模型判断成立。

至少需要：

```text
多个 Case 支持
+
人工 Review
+
后续真实效果反馈
```

才允许升级为高可信 Pattern。

---

# 22. 权限与资产归属候选

**[Candidate / Open Question]**

当前产品描述暗示：

### Company Scope

```text
Case Library
Pattern Library
Approved Music Assets
Standard Voice Assets
```

属于公司级资产。

### Account Scope

```text
Video Persona
Generation Batch
Generated Content
Customer-specific Voice
```

属于用户 / 账号空间。

需要在未来多租户设计前正式确认：

- 用户能否看到 Case 原视频；
- 用户能否看到 Pattern；
- 用户能否上传自己的私有 Case；
- 私有 Case 是否允许进入 Company Library；
- Persona 是否可跨组织；
- 代理商与直客的数据隔离。

当前不得由开发自行决定。

---

# 23. 安全、版权与合规

## 23.1 Secret

**[Stable Principle]**

API Key：

- 不写入代码；
- 不提交 Git；
- 通过 Secret / Environment 注入；
- 日志不得打印。

## 23.2 Source Case

案例下载用于内部研究与结构学习。未来产品对外提供原视频、音乐、完整转录内容之前，需单独确认版权与平台规则。

## 23.3 Voice

未经授权不得克隆真实案例人物声音用于商业生产。

## 23.4 BGM

案例视频中的 BGM：

> **可研究 ≠ 可生产使用。**

正式客户生产只允许 `rights_status = approved` 的音乐资产。

---

# 24. 当前不应冻结的内容

**[Not Frozen]**

以下都还属于实验参数：

- Qwen3-VL 是否长期使用 4B；
- DeepSeek 是否长期作为融合 / 生成模型；
- faster-whisper 是否长期使用 large-v3；
- 每秒采样多少帧；
- 每块 6 / 8 / 10 张图；
- Context 大小；
- CLAP / Music 模型；
- TTS 模型；
- CosyVoice 版本；
- Case Matching 具体权重；
- 100 条内容如何分配 Case / Pattern；
- 10,000 Persona 上限；
- 生成数量 UI；
- Pattern Approved 阈值；
- 数据库；
- Vector DB；
- REST 路由；
- Schema 字段名称；
- 页面视觉；
- Prompt 具体措辞；
- 自动化程度。

---

# 25. 下一阶段实验计划

## Stage A｜Reverse Storyboard V1

目标：

```text
Word-level Audio
+
完整 Visual Chunking
+
严格 Role Dictionary
↓
高质量 Reverse Storyboard
```

## Stage B｜Case Schema / Pattern Schema

目标：

- 形成 Canonical Case；
- 形成 Pattern Candidate；
- Observation / Understanding / Pattern 分层；
- 支持后续批量入库。

## Stage C｜Pattern Mining

选择一组真实高质量案例：

```text
10+
↓
跨案例分析
↓
Copy Pattern
+
Shot Pattern
```

数量为候选，不是冻结阈值。

## Stage D｜Persona Matching + Generation

选一个真实客户 Persona：

```text
Persona
↓
Case + Pattern Portfolio
↓
先生成约 10 条
↓
人工 Review
```

不需要第一轮直接生成 100 条。

## Stage E｜Publishing Copy + 3 Excel

输出：

```text
新闻体制作 Excel
混剪制作 Excel
发布文案 Excel
+
batch_manifest.json
```

并真实导入现有系统。

## Stage F｜Voice + BGM

先跑通：

```text
Production Script
↓
Voice Plan
↓
TTS
↓
BGM Plan
↓
Audio Mix
```

## Stage G｜真实成片

```text
脚本
↓
素材
↓
声音
↓
音乐
↓
现有系统
↓
真实视频
↓
人工 Review
```

## Stage H｜第一次完整业务闭环

必须至少证明：

```text
真实 Case
↓
Approved Case

多个 Case
↓
Pattern

真实 Persona
↓
新 Production Scripts
↓
Publishing Copy
↓
3 类 Excel
↓
现有系统
↓
成片
↓
Review
```

完成后，才进入 Freeze Review。

---

# 26. Codex 进入条件

**[Stable Principle]**

Codex 可以辅助实验脚本，但不应在以下条件之前大规模产品化：

1. Working Architecture 已形成；
2. 核心业务闭环至少跑通一次；
3. Case 与 Pattern 边界明确；
4. Evidence 与 Interpretation 边界明确；
5. 真实系统 Excel Contract 已确认；
6. 主要失败路径已经通过实验发现；
7. Open Question 不被误写为 Frozen Requirement。

届时 Codex 的任务是：

> **把已验证工作流工程化，而不是替公司重新发明工作流。**

---

# 27. Freeze Candidate 判断标准

未来 V1.0 Freeze Review 只检查：即使模型、Agent、平台、UI、TTS、音乐算法都变化，以下原则是否仍成立：

```text
Case ≠ Pattern

Evidence ≠ Interpretation

程序拥有时间 / ID / 完整性
AI 拥有语义 / 生成

Company Library 只消费 Approved Case

Persona 匹配 Case + Pattern Portfolio
而不是抄一条视频

Production Script 与 Publishing Copy 分层

Excel 由 Formatter 生成

真实效果必须回流
```

如果这些仍成立，才适合进入 Frozen V1.0。

---

# 28. 当前架构摘要

```text
                    ┌──────────────────────┐
                    │   Company Case Loop  │
                    └──────────────────────┘

真实视频
↓
Evidence Core
↓
Reverse Case
↓
Human Review
↓
Approved Case
↓
Pattern Mining
↓
Approved Pattern
        │
        │
        ▼
┌──────────────────────┐
│ Customer Production  │
└──────────────────────┘

Video Persona
↓
Hard Filter
↓
Case + Pattern Recall
↓
Rerank
↓
Diversity Portfolio
↓
Production Script
↓
Quality Gate
↓
Publishing Copy
↓
Excel Formatter
↓
Voice / BGM / Materials
↓
现有视频系统
↓
发布 / 投流
↓
Performance Feedback
↓
Pattern Evaluation
↓
Case / Pattern Learning Loop
```

---

# 29. 一句话定义

> **这不是一个“AI 批量写文案”的系统，而是一套把真实短视频经验持续转化为公司 Case 与 Pattern 资产，再根据不同客户人设生产可执行视频内容，并通过真实结果持续学习的 AI 短视频代运营生产系统。**

---

# 30. V0.1 当前结论

```text
Architecture Direction：成立
MVP Reverse Pipeline：已跑通
Production Loop：未完全跑通
Case Schema：待定义
Pattern Schema：待定义
Pattern Mining：未验证
Persona Generation：未验证
Excel End-to-End：待验证
Voice：方案候选
BGM：方案候选
Performance Feedback：未实现

Planning Ready：No
Frozen：No
```

下一步继续使用本文作为实验边界，优先完成：

```text
Case Schema V1
↓
Reverse Storyboard V1
↓
Pattern Schema V1
↓
Pattern Mining
```

在完整业务闭环验证前，不进入最终产品冻结。
