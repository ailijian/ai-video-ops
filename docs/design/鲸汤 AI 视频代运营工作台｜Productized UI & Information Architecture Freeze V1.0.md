# 鲸汤 AI 视频代运营工作台｜Productized UI & Information Architecture Freeze V1.0

这一版的设计目标不是“更酷”，而是：

> **安静、专业、可信、低学习成本。**
>
> 打开后像一个团队每天在用的成熟运营产品，而不是一套把系统内部结构展示给用户看的开发控制台。

---

## 视觉方向：从「组件 Demo」变成「专业运营桌面」

现有深绿 + 暖白的基础不用推倒。审计里的全局色彩其实是成立的，问题主要在大圆角、大标题、过多阴影和“所有东西都装进 Card”。当前页面 H1 最高可到 46px，大卡圆角 24px、中卡 18px，并且几乎所有业务块都有边框和阴影。

新的视觉基线冻结为：

**Canvas** 使用极浅暖灰 `#F6F7F4`，核心 Surface 使用 `#FFFFFF`；品牌深绿保留，但主色统一为 `#214C3D` 左右，Hover 使用更深的绿。珊瑚橙不再常驻于导航主入口，只用于“需要注意”或少量品牌强调；Amber 只表示待处理，Red 只表示失败和危险操作。

**圆角降级**。页面主要容器 14–16px，普通 Card 10–12px，输入框和按钮 9–10px；只有 Pill 保持胶囊形。现在 18–24px 的大圆角会明显收敛。

**阴影基本退出工作区**。普通 Card 默认只使用 1px 边框，只有 Toast、Modal、Dropdown 等浮层使用阴影。页面的层次主要由留白、字号和分隔线形成。

**字体变成工作台尺度**。Page title 28–32px，Section title 18–20px，Card title 15–17px，正文 14px，Meta 12–13px。首页、案例页、客户页都不再出现接近官网 Hero 的超大标题。

**Spacing 统一成 4 / 8 / 12 / 16 / 24 / 32 / 40 / 48**。现在 CSS 里大量 11、13、18、22、28 等 page-specific spacing 不再继续扩散。

---

# 全局 Shell 重做

桌面侧栏继续保留，但我建议导航正式改成：

| 当前    | V1 冻结 |
| ----- | ----- |
| 工作台   | 工作台   |
| 案例库   | 案例    |
| 视频创作  | 创作    |
| 客户与人设 | 客户    |
| 任务记录  | 任务    |

顺序冻结为：

**工作台 → 案例 → 客户 → 创作 → 任务**

“创作”不再永久使用一块橙色按钮强调。审计已经指出，桌面和移动导航持续把 Create 视觉提升为 Primary，而页面内部又有自己的 Primary Action，这实际上形成了两个竞争的操作层级。

以后导航只表达“你在哪里”；Primary Action 只由当前工作页面决定。

侧栏底部的：

> 内部生产工作台 · V1

删除。

顶部栏保留当前页面名称、账号和退出，但手机号缩小为账户菜单信息，不抢视觉焦点。

移动端也取消现在明显隆起的 Create Orb，统一为五个等权 Tab，只用 Active 状态区分当前区域。这样会从“消费 App”更接近专业移动工作台。

---

# 信息架构：默认界面彻底停止说工程语言

这一轮真正决定“正式产品感”的其实是这一项。

以后默认运营界面只存在三类信息：

**我现在在哪、发生了什么、下一步做什么。**

架构术语继续存在于代码、Artifact、日志和治理文档里，但不再要求同事学习它们。

术语映射冻结如下：

| 内部术语                    | 默认产品语言            |
| ----------------------- | ----------------- |
| Customer Truth          | 已确认信息             |
| Business Persona        | 客户档案              |
| Speaker Persona         | 出镜人档案             |
| Authority               | 依据 / 当前有效信息，按语境表达 |
| Content Ledger          | 历史内容记录            |
| Generation Request      | 本次创作              |
| Source Planning Handoff | 素材准备              |
| Profile                 | 内容类型              |
| Attempt                 | 本次分析              |
| Artifact                | 结果 / 记录           |
| Canonical               | 默认不显示             |
| Request ID              | 默认隐藏              |
| Hash / Schema           | 完全隐藏              |
| Approved Projection     | 已确认内容             |
| Historical Exposure     | 历史已使用内容           |
| Presentation History    | 历史呈现记录            |
| Central Claim           | 核心表达              |

这不是简单“中文化”。例如：

> 当前 Authority 状态正常

不会改成：

> 当前有效信息状态正常

而是整个句子删除，只在需要用户做决定时告诉他：

> 客户资料和出镜人资料都已确认，可以开始创作。

审计已经确认大量工程词和中文业务语言混在同一句话里，甚至 raw API message、technical status enum 和 JSON 都可能直接露给用户。 这一层必须彻底收掉。

Rights / Human Gate 例外。类似：

> 批准案例不会获得原视频素材使用权。

这是用户做正确决定必须知道的信息，继续保留。但不再在五个地方重复说同一件事。

---

# Workbench：从「系统状态展示」变成「今天需要做什么」

当前 Workbench 是整个系统“工程味”最浓的页面之一：4 张 Attention Card + 3 张 Quick Card + Operational Card + Customer Card，一打开就是 9 张卡。

新版第一屏冻结成：

**顶部**：`工作台` + 一句动态摘要，例如：

> 今天有 3 件事需要处理。

下面是一个 **需要你处理** 区域，不再做四张 KPI 卡，而做一张紧凑 Action List：

```text
需要你处理

2  个案例待审核                     去审核
1  个客户信息待确认                 去确认
2  个任务正在运行                   查看进度
```

如果完全没有待办：

> 当前没有需要处理的事项。

然后才是 **快捷开始**：

`添加案例 / 新建客户 / 开始创作`

用三个轻量按钮/入口，不再三张大 Card。

再下面是 **最近工作**，只展示最近客户和最近任务，每类最多几条。不要首页承载完整业务状态。

“客户运营可以继续”这种系统判断默认不再占首页大卡；只有真正有 Operational Hold 时，才出现一条明显但紧凑的 Warning Banner。

---

# 案例：变成媒体运营库，而不是卡片墙

现在案例库是 N 张 Case Card，数据一多就会越来越长。审计里的真实状态已经有 11 张案例卡，移动页面高度达到 2781px。

桌面端改成 **List / Row View**：

```text
案例                                         + 添加案例

全部 12      待审核 2      已入库 10

烧烤创业故事
抖音 · 13 秒 · 人物表达              已入库      >

海鲜处理技巧
抖音 · 21 秒 · 知识说明              待审核      >
```

不要每条再一个大白 Card。

Mobile 才使用紧凑 Card。

Profile / Industry 只有确实帮助运营判断时才显示；开发内部枚举不显示。

---

# 添加案例：从「表单 + 说明卡 + 进度卡嵌套」变成一个连续任务

当前 Add Case 会出现 Card inside Card：URL panel 中又塞 progress card。

新版页面只保留一个工作面。

初始态：

```text
添加案例

粘贴抖音视频链接
[ https://...                         粘贴 ]

                       [分析案例]

批准后的案例只用于内部参考，
不会获得原视频素材使用权。
```

提交后，表单本身直接转换为 Progress State，而不是在下面再长一张进度卡。

完成：

```text
分析完成
视频已经准备好审核。

[审核案例]

添加另一个案例
```

---

# 案例审核：Evidence-first，而不是 Video-first

刚才我们已经处理了播放器尺寸问题，这次把整个页面一起正式化。

桌面首屏冻结：

```text
← 案例                                  待审核

┌──────────────┐   烧烤 / 野 / 美食 / 创业
│              │   抖音 · 13 秒
│  视频预览    │   视频简介……
│  compact     │
│              │   在抖音打开原视频 ↗
└──────────────┘


分析结果                         ┌─────────────┐
                                │ 审核         │
讲了什么                        │             │
……                              │ [批准入库]   │
                                │ 重新分析     │
怎么讲                          │ 不收录       │
……                              └─────────────┘

值得参考
……

完整拆解  >
```

去掉多个大卡片，只留下分区标题 + Divider。

右侧 Review Panel 是唯一强调 Card，并在桌面 Sticky。

“原始媒体已清理”“Media Rights”等技术描述不再单独做两个 Notice。只在媒体区域显示一句轻量说明：

> 当前通过抖音原视频进行审核。

审核按钮下再保留：

> 批准不会改变原视频素材使用权。

---

# 客户：这是本轮最需要降噪的页面

审计记录的真实 Customer Detail 达到 **28 张卡、桌面 5307px、移动 5637px**。

这个页面如果不重新组织，即使颜色再漂亮也不像成熟产品。

客户详情冻结为：

```text
上海 XX 餐厅                         已确认

餐饮 · 上海
1 位出镜人

[开始创作]     ···


概览   客户资料   出镜人   内容
```

**概览**只显示业务需要的摘要：

客户状态、出镜人、内容空间、最近创作。

**客户资料**集中展示确认过的事实。不要 20 条事实 = 20 张 Card，改为 Section + Key/Value Rows：

```text
基础信息
客户名称                 XX餐厅
行业                     餐饮
经营年限                 12年
服务区域                 上海浦东
```

长文本单独作为 Content Blocks。

**出镜人**才显示 Speaker。

**内容**承接现在的 Content Operations。

这样原来一个 5000px 超长页面就被拆成四个清晰信息域，而不需要增加新的 Backend Authority。

---

# 客户审核 / 出镜人审核：保留 Human Gate，删除架构教学

现有 Fact Review 的信息密度问题非常典型：

Card → Evidence → 3 Choices → Edit Panel → Authority Notice。

新版每个 Fact 使用一条 **Review Row**：

```text
主要产品 / 服务

社区食堂、快餐、自选菜

来源：客户提供资料                            查看依据

[确认]   [修改]   [不采用]
```

不再每条 Fact 都是一张大 Card。

“Customer Truth”“Speaker Facts”“Business Fact Boundary”等说明全部换成用户结果：

> 确认后的信息将用于后续视频内容。

出镜人的关键边界只保留一句：

> 这里确认的是这个人可以以第一人称表达的信息，不代表拥有相关照片或视频的使用权。

---

# 创作：从内部 Workflow Viewer 变成真正的创作入口

审计已经发现 `/create` 在 **390、430、1440、1792 四个目标宽度全部横向溢出**，根因是隐藏 radio input 仍吃了全局 `width:100%`。 这是实施阶段 P0，必须第一批修。

但视觉层面也要一起改变。

入口冻结为：

```text
开始创作

客户
[ XX社区食堂             ▼ ]

出镜人
[ 林师傅                 ▼ ]

内容类型

(●) 混剪
    用真实素材重新组织表达

( ) 新闻体
    从已有内容中重新呈现


计划生成
[ 4 ] 条


系统预计还有 7 条值得做的新内容。

                         [继续]
```

不再显示：

> Content Ledger
> Current Authority
> Production Profile
> Capacity Authority

进入下一步后：

```text
本次创作

4 条
XX社区食堂 · 林师傅 · 混剪

素材准备完成
选题已生成
文案待审核
```

用户理解 Workflow，但不需要知道 `Generation Request / Source Planning Handoff / canonical request`。

---

# Mix / News 审核：把技术元数据折叠出去

这是审计里信息和 Card 嵌套最严重的两个 Surface。

默认每条内容只显示：

```text
01

下班后不知道吃什么？
这里是附近居民每天都会来的社区食堂……

核心表达
离家近、选择多、价格清楚

[通过]   [修改]   [不用]
```

`Model Original / Historical Exposure / Approved Projection / Semantic Ledger / Central Claim immutable` 不再默认出现。

如果确实需要内部排障，统一放进：

> 查看生成依据

Disclosure 里。

正式产品默认不展示开发 provenance。

---

# 任务：从 19 张进度卡变成 Activity List

现在真实数据下 19 个 Task 被渲染成 19 张 progress card，桌面页面达到 4682px。

改成一张表格式 Activity List：

```text
任务                   状态         更新时间      操作

烧烤案例分析           已完成       05:22         查看
XX餐厅客户分析         待确认       04:31         继续
4条视频生成            进行中 62%   03:48         查看
```

Mobile 转成 compact rows。

只有进入 Task Detail 才显示完整 stage progress。

---

# 空状态、错误状态和确认操作也必须产品化

Native `confirm()` / `prompt()` 不再出现在正式产品里。

所有重要操作统一使用产品 Modal：

```text
批准这个案例？

请确认你已经对照原视频检查内容与结构。

批准后会进入案例库，
但不会获得原视频素材使用权。

[取消]            [批准入库]
```

Error 不再直接把 Backend wording 顶到页面。

默认：

> 暂时无法完成操作

然后显示真正对用户有帮助的 `next_action`。

Technical code 留在 Console Log，不进入普通界面。

---

# 响应式冻结

这轮把当前大量 680 / 760 / 900 / 1024 / 1040 / 1280 的碎片化断点收敛成三个核心层级：

**Mobile `<768`**
单列，底部导航，表单操作使用唯一 Sticky Action Bar。

**Tablet `768–1023`**
单侧内容宽度提升，列表可双列，但仍不出现 Desktop Sidebar。

**Desktop `≥1024`**
Sidebar + 1200–1280px 工作区。

`≥1280` 只允许增强型布局，例如 Review Sticky Aside，不重新定义一套组件系统。

移动端同一页面不能同时出现：

`sticky topbar + sticky action + bottom nav`

三层抢空间。需要 Mutation CTA 的页面，统一留出 Bottom Nav offset，只存在一条 Action Bar。

---

# 这一轮的正式停止标准

做完后，我不以“CSS 全绿”作为通过标准，而以这几个产品结果验收：

**第一眼**：看不到明显工程术语，不像开发 Dashboard。

**5 秒理解**：进入任何主要页面，用户都知道“我在哪、现在什么状态、下一步是什么”。

**操作层级**：任何工作状态最多一个明确 Primary Action。

**页面密度**：Customer Detail、Tasks、Workbench 不再依赖几十张卡表达结构。

**视觉一致性**：同类状态、同类提醒、同类按钮、同类信息行只存在一套视觉语法。

**Responsive**：`/create` 四个目标宽度 0 horizontal overflow，390px 手机端没有三列硬塞或 Sticky 冲突。

**信息边界**：系统内部 Authority 仍严格存在，但默认 UI 不再把治理架构当产品文案。
