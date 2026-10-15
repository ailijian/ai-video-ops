# NAV-1 + CUSTOMER-LIST-1 联合 UX 实施报告

日期：2026-10-14。状态：**OFFLINE_VERIFIED / READY_FOR_PRODUCT_REVIEW**；Founder 独立 UX 验收及生产验收尚未完成。

本报告记录 Founder 本轮明确批准的导航与客户运营列表变更。它只替代旧 UI 文档中适用的一级导航、客户目录卡片与全局新建创作入口呈现，不修改既有 Authority、Human Gates 或生产资格。CS-0～CS-3、E2-A～D、E2-UX、Case V1.1 的既有成果保留。

## A. 工程基线与保护

| 项目 | 本次实际状态 |
|---|---|
| hostname | LIJIAN |
| HEAD | `1effb623eb89413686f87ce953931897912b82eb` |
| 主工作区 | `E:\projects\ai-video-ops`，`main`，开始及结束均 clean |
| 原建议工作区 | `E:\cs-intake-v1` 已在此前授权的 checkpoint/合并/工作树收口中移除；本次没有重做合并或恢复旧目录 |
| 当前隔离 worktree | `E:\projects\ai-video-ops\.worktrees\nav1` |
| 分支 | `codex/nav1-customer-list1`，从上述 HEAD 创建，当前修改未提交 |
| Case V1.1 冻结参考 | `f10f3992433ab81df38ae90f9379ce1061a7afac`；本次没有重写案例录入与审批实现 |
| 旧服务 | 127.0.0.1:18013，监听 PID 30888，原 DB 与 Canonical Root 未重启、未借用 |
| 新隔离服务 | 127.0.0.1:18015，launcher PID 6484，监听 PID 10452；当前 worktree 完整 ASGI + Static |
| 新 DB / Canonical Root | `.local/nav1node02/console.sqlite3` / `.local/nav1node02/ops-pipeline`，均在主项目目录内 |
| 保护检查 | 1389 个既有 JSON SHA 不变，5 个既有 DB 的非 sessions 表内容摘要不变，main HEAD 不变且 clean |

新运行根只包含虚构 fixture 与本轮隔离 UAT 产生的记录。没有操作 4090、生产数据、FRP、云配置、凭证或旧 UAT 数据。没有 commit、push、merge、deploy。虚拟环境复用主工作区现有 venv 的 junction；`.verify` junction 保持项目内短路径，避免 Windows 深层测试路径超过限制。

证据根：`E:\projects\ai-video-ops\.local\evidence\nav1-customer-list1-20261014`。保护基线、最终差异、截图、测试 XML、浏览器轨迹摘要与运行信息均保存在此处。完整测试收据位于主项目 `.verify/65d245c0/`。这些本机证据没有作为业务 Authority 使用。

## B. 旧「创作」Tab 职责与新入口

审计入口包括 `app.js` 导航/工作台/任务详情、`content-views.js` 创作表单与恢复、Mix/News/Novel Gateway、Delivery 视图，以及客户内容管理页面。

| 原有职责 | 现在推荐入口 | 保留能力 |
|---|---|---|
| 新建内容、选择客户 | 客户列表「开始创作」或客户详情 | 原 `/create`、Creation Entry、Preview、Confirm；只省去重复选客户 |
| 继续未完成 Request | 客户主操作或该客户作品记录 | 精确 Request ID，恢复原 profile/mode，无自动新建 |
| 查看进行中内容 | 客户卡片「查看处理进度」/任务页 | 原 Task 及轮询，原任务身份 |
| 待审核、修改、导出 | 作品记录「查看原创作」或 Task「查看原创作与审核」 | 原 Delivery/Human Review/Export 视图和 API |
| 失败恢复 | 客户/人物详情的已有恢复按钮，或精确内容 Request | 原 checkpoint、重试与幂等，不另建恢复流程 |
| 跨客户最近工作 | 工作台最近任务 → 原 Task | 跨客户入口保留 |
| 跨客户执行状态 | 一级「任务」 | 原分页、详情、恢复能力保留 |
| 历史作品与导出 | `/customers/{business_id}/content` | 新增请求记录的只读列表，原交付记录/下载区保留 |
| 旧无客户 `/create` 书签 | 明确「先选择一个客户」 → 客户列表 / 已有任务 | 旧路由有效，不生成缺少客户归属的 Request |

桌面与手机一级导航实际改为 **工作台 / 案例 / 客户 / 任务**。创作页仍存在，导航 active 归属「客户」。移除 Tab 没有删除 Creation 组件、Gateway、审核、导出或生命周期。

## C. 卡片字段、计数与查询口径

唯一新增层为 Console **只读列表 Projection**：`customer_operations_projection.py`。Canonical writers/resolvers 继续决定业务状态；SQLite 仅供已有执行 Task 投影。没有新增业务写入字段、迁移或第二套状态机。

| 字段 | 正式来源与规则 |
|---|---|
| 名称 | 现有 `_customer_projection` / 客户 Intake 与正式 Persona 展示规则 |
| 行业 | 先用现有人工 classification 的 `approve/edit`；没有该记录时才读当前 Approved Business 中已确认 industry；AI hint、defer/reject/uncertain 不升级为确定行业 |
| 地区 | 仅当前 Approved Business 已确认的 `location_public_area` 字符串；不存在即省略 |
| 当前状态/下一步 | 客户状态、精确 Business/Speaker lineage、Canonical Constraint policy、有效 Request stage、最新执行 Task 与正式 Creation Entry 的派生结果 |
| 已批准出镜人数 | 以 Speaker ID 去重；必须通过 Approved Persona resolver 且精确绑定当前 Business revision/SHA；Draft、待本人审核、待新 revision 复核不计入 |
| 人物摘要 | 一位有效 Approved Speaker 的公开姓名、公开身份；按姓名 + ID 稳定排序，只作为代表展示，不称「主出镜人」；不输出经历、生日、联系信息 |
| 创作记录 | Canonical `generation_requests` 与 `news_deliveries` 的 Request 数；按 namespace + Request ID 标识，一份请求计一次，含未完成/结束/导出；不等于脚本数、成片数、生成次数或导出次数 |
| 待处理 | 一个客户资料工作项 + 每个可人工处理的 Speaker 工作项 + 每个可处理 Request；同一内容失败 Task 与对应 Request 去重，重试由最新同操作 Task 代表 |
| 不计待处理 | 纯 queued/running 执行、等待客户批准而不能继续的 Speaker、人物分析中、被后续恢复/Canonical 完成阶段取代的历史失败 |
| 最近更新 | 持久化 Intake 提交、人工行业审核、当前 Persona 批准、Task 更新时间与 Request 创建时间的最大值；统一 UTC；非法/缺失时间不伪造为 now；Request 没有可靠新更新时间时使用创建时间 |
| 未知与 0 | 读取失败返回 `null`，卡片显示 `—`；合法空集合显示 0；不会因读取失败写成无记录 |

待处理是「工作项」计数，不是逐条候选事实数。queued Task 只有与该 Request 当前 Canonical 下一步骤精确匹配时，才从人工待办中扣除；另有待审核作品时仍显示待处理。

权限保持现有已认证同事共享客户的范围。没有新增按账号隔离，也没有把 actor A 的身份用于 B 的提交。列表响应不返回 Task 原始 payload 或完整 Persona。

查询：一次客户/人物目录索引、一次 Request 全局索引、**一次 Task SQL**；Delivery 汇总跳过不需要的 export actor SQL，避免逐卡片任务/人物全局 SQL 查询与前端 N+1 请求。每页默认 20、最大 50。规范化状态仍委托既有 Canonical Owner 逐对象校验，没有引入失效缓存或读取捷径。25 客户专项验证一条 Task SQL、搜索分页及稳定排序；大量已批准客户和大量 Novel News 历史的耗时仍需实际容量基准测试，不宣称完成大规模性能验收。

搜索仅名称、已确认行业与合法地区。筛选「全部 / 待处理 / 可创作」与卡片采用同一投影；计数范围是 **全部搜索匹配**，不是当前页，UI 明示。排序默认可操作事项优先，再可信更新时间，ID 稳定打破并列；支持最近更新。URL 保留搜索/筛选/排序/页码，浏览器返回恢复上下文。不存敏感资料到 localStorage。

## D. 状态、次级说明和主操作矩阵

优先级从上至下，命中第一项作为唯一主状态/主操作；卡片只有一个次级说明及作品记录入口。

| 条件 | 主状态 | 主操作 | 保持的边界 |
|---|---|---|---|
| 当前重大限制；或新材料含未解决身份/Business 范围冲突 | 待核实 | 查看阻断原因 | 包括尚无首次 Persona，以及旧 Approved R1 + 新 R2 核心冲突；R1 不改写，也不能据 R1 错误放行 |
| 最新有效失败任务需恢复 | 异常 | 处理异常 | 客户/人物分析回原详情；内容回精确 Request；独立可用路径另行验证，失败不是永久剥夺资格 |
| 客户存在待审核事实 | 待核对 | 去核对资料 | AI Candidate 不等于 Human Review |
| 事实已核对、档案尚待独立批准 | 待批准 | 查看待批准事项 | 不自动 Persona Approval |
| Readiness 仍需处理 | 待处理 | 继续处理资料 | 进入既有缺口/遗漏/冲突说明，不概括成虚假的主营缺失 |
| 既有 Request 需要人工操作 | 待处理 | 继续创作 / 待审核 / 待导出 / 查看记录阻断原因 | 原请求优先；与运行 Task 并存时待审核工作优先 |
| 仅有 queued/running Task | 处理中 | 查看处理进度 | 单纯运行不计人工待办 |
| 至少一条正式路径可继续 | 可创作 | 开始创作 | Formal Creation Entry/News preview 支持且无核心阻断；进入与提交再次验证 |
| Business 已批准，人物需独立审核/精确复核，且没有其他可用路径 | 待处理 | 查看出镜人资料 | 待复核者不计 Approved Speaker，不自动继承 Business revision |
| Business 已批准，但现有路径没有兼容覆盖/可用内容 | 查看创作条件 | 查看创作条件 | 正常 coverage 不足不是系统异常，也不是待批准 |
| 只有名称或尚未建档 | 待建档 | 继续完善资料 | 可以先保存，不能据名称生产 |
| 记录无法可靠读取 | 需核对 | 查看阻断原因 | 统计未知、fail closed，不伪造正常状态 |

「可创作」筛选表示**存在至少一条支持路径**，并非卡片当下主操作一定是新建创作。例如 A 已有运行任务且另一入口仍具备 formal Mix 条件时，筛选可包含 A，但卡片仍为「处理中」，优先原工作、不创建重复请求。

目前正式受支持的适用路径均通过既有 Owner 要求 Business/Speaker。列表只检查这些真实路径，没有新加一个覆盖未来所有 profile 的「无 Speaker 一律禁止」规则。Novel News 仍受原 actor rollout；新 Constraint 下尚未适配的 News 路径保持阻断。Content Opportunity、可创作脚本与 Production Feasibility/媒体生产权利仍分别判定。

## E. 路由与恢复兼容性

新增 GET 均需既有正式登录：

- `/api/customers/operations`：搜索/筛选/排序/分页只读聚合。
- `/api/customers/{business_id}/creation-records`：服务端先验证真实客户，准确限定其记录。
- `/api/create/request-context`：按原 Request namespace/profile/header/lineage 解析 Business 身份；可从不含 profile 的旧任务 URL 推导真实模式；歧义、错配 Business 或 profile 拒绝。
- `/api/create/options?business_id=...`：只读该准确客户，非法/不存在 ID 明确失败，不退回其他客户。

现有 POST、auth、CSRF、Operation Lock、服务端 actor、Request 幂等没有改写。定向表单展示客户名称和返回客户入口；保留原 form plumbing 的单项隐藏客户字段，不让同事再次选择该客户。打开表单不生成内容；真正 Preview/Confirm 仍走正式 Gateway。

旧 `/create?request_id=...` 会恢复原 Delivery/News/Novel 视图。终止请求只展示历史；导出请求保留原结果入口。有效任务页增加「查看原创作与审核」，关联原 Request，不以查看动作创建新 Task。

浏览器验收发现并修复两个实际导航问题：离开内容 Task 后旧轮询会覆盖新 Request DOM；从较慢作品 API 返回列表后旧响应会覆盖新页面。已增加轮询 dispose、路径判断及异步渲染 route guard；对应 JS 回归证明迟到更新不能重画其他页面。

一次纯导航保护窗口（A 创建完成后、B 新录入前）比对 **95 个隔离 JSON / 6 个 Task / 2 个 Request**，刷新、返回、前进、查看历史及另一账号共享读取均不新增/重写这些记录。该收据只代表此明确窗口，不伪称整个 UAT 没有合法新建数据。

## F. 本轮文件增量与调用关系

已修改：

- `internal-console/app/customer_gateway.py`：列表可传已知 Approved Speaker count，避免重复全局扫描。
- `internal-console/app/content_gateway.py`：准确客户范围的 creation options。
- `internal-console/app/content_delivery_gateway.py`、`news_delivery_gateway.py`：列表可跳过 export actor SQL；其他调用默认行为保持。
- `internal-console/app/main.py`：新增认证只读 Projection/context/history GET。
- `internal-console/static/assets/app.js`：四项真实导航、工作台客户入口、原 Request Task 入口、轮询释放。
- `customer-components.js`：信息卡片；`customer-views.js`：搜索/筛选/分页与返回状态。
- `content-views.js`：客户定向表单、旧 Request 上下文及无客户兼容入口。
- `content-operations-views.js`：原客户内容管理中加入原请求记录与分页，保留既有内容概览/交付区。
- `styles.css`：沿用现有风格的紧凑卡片、搜索控件、四列手机导航和安全底部留白。
- `internal-console/tests/browser_customer_speaker_intake_v1.py`：复用已有 harness，项目内隔离存储、新根专用虚构导航参考 fixture、实际 HEAD manifest；不增加第二套运行入口。
- `test_productization_ui_stage1.py`、`stage2.py`、`stage3.py`：对齐 Founder 本轮批准的四项导航/运营卡片/客户定向入口，原详情、Human Gate 与 Capacity 断言保留。
- `docs/operations/README.md`：为本实施证据添加适用的导航关系。

新增：

- `internal-console/app/customer_operations_projection.py`：上述唯一只读聚合 adapter，调用现有 Canonical Owners。
- `internal-console/tests/test_customer_operations_navigation.py`：22 个参数化 HTTP/投影/正式 Gate/分页专项用例。
- `internal-console/tests/js/customer-operations-navigation.test.mjs`：实际前端渲染、未知计数、定向导航及迟到请求/轮询保护。
- `internal-console/tests/fixtures/customer_navigation_v1/README.md` + 9 JSON：完全虚构的预先审核参考库，供全新隔离根与 formal HTTP Gate 验证。
- 本报告。机器业务 Schema、Approval Owner、生产消费者与旧报告没有变更。

fixture 含精确虚构 Case SHA、Fingerprint 与 Mix Compatibility sidecar、Pattern/receipt/profile/coverage。Aggregate Owner 固定要求的历史 ID/reviewer 仅作为显式 `fixture_only` 且 SHA 不匹配的占位引用，不能为虚构 Case 授权；虚构 Case 使用自己的精确 sidecar，删 sidecar 即失去 formal 可创作资格。没有生产媒体使用权。不是新增真实 Founder Approval，更不是运行 fallback；原 fixture 与历史证据没有删除。仅替换旧页面呈现，不留下平行 V2 入口。

## G. 真实浏览器验收轨迹与截图

环境：Codex In-app Browser，当前 ASGI/Static、全新独立 DB/Canonical Root、正式认证/CSRF/Operation Lock/Fact Review/Persona Approval。只在 Customer/Speaker 模型边界注入已有虚构 Golden。桌面与 **390×844、320×740** 实际视口滚动/点击，不使用 full-page 图作为底部按钮可用性证明。

### A：新客户、核对、批准、原请求

客户 `customer_1102bbf0e8f745018eab630e813006d5`，虚构名称「澄禾小馆 · NAV验收A（虚构）」；人物 `speaker_7e2ad51baef0db`。

真实点击录入 → 自动整理 → 普通事实与限制审核（未核实宣传显式 exclude）→ 独立 Business Approval → 人物本人 3 项逐条审核 → 独立 Speaker Approval。回列表显示餐饮、Approved Speaker 1、请求 0、待办 0，进入准确客户 Mix 表单，无重复客户选择。

Formal Capacity Preview 请求 4 条、实际支持 2 条；明确确认得到 `gen_3682f6a4fb391b01865f`。刷新恢复同一请求/数量；本地确定性 sources 已完成。点击生成选题产生既有正式 `content_plan-gen_3682f6a4fb391b01865f-ab67cdf3c89b`，**真实生成 worker 禁用，任务保持 queued，不调用模型**。列表显示创作记录 1、待办 0、处理中；Task 返回原 Request，无重复请求。

### B：搜索、正式可创作、手机入口与空记录

另一已认证账号在相同共享范围合法读取 A，再录入虚构客户 `customer_1a6279273b974e09b115c1f19e9fc847`；人物 `speaker_d871bfcef4518f`。完成相同正式人审与两次独立 Persona Approval。

Business 已批准、Speaker 尚待审时截图显示 Approved Speaker 0、待办 1，不能标可创作。人物批准后搜索「NAV验收B」并筛选可创作，显示 1 / 0 / 0；桌面与手机点击开始创作均为准确 Business/Speaker，返回与历史链接有效。只打开表单，**没有为 B 新建 Request**；作品记录显示真实 0、无已交付内容。

### C：未完成、核心冲突、分析失败恢复

- 名称-only `customer_aa03fbf8636f4f64b817bcfc039b6a10`：行业待确认、Approved Speaker 0、请求 0，继续完善资料。
- 核心冲突 `customer_26d216347fa8474886eaf946431b4eed`：依法保存可审核普通事实；奖项 exclude，主体冲突 defer；Speaker Draft 保留。行业人工确认餐饮，但无 Approved Business/Speaker、卡片「待核实/查看阻断原因」，等待客户的 Draft 不重复计待办，不能开始生产。
- fail-once `customer_603870c2d6b64aee9719d6c48180e94b`：合成边界的受控失败 → 卡片异常 → 原详情「继续分析」复用已存资料 → 新恢复 Task awaiting_review。旧失败 Task `...-41273d75cb36` 保留，新 Task `...-ced4dd4218e7`，列表回待核对/待办 1，未批准、未重复统计。

### D：历史创作与任务恢复

从任务页进入 A 的有效旧 Request 链接，模式和客户由服务器解析，恢复原来源/请求与审核工作上下文；刷新、返回、前进、作品记录与手机恢复仍为同一 ID。工作台最近任务/跨客户任务、原内容管理审核与导出组件保留。此浏览器轨迹选择了**历史恢复**分支，没有声称实际完成新模型生成、成片审核或生产导出；这些原有接口由正式回归覆盖。

截图均在证据根 `screenshots/`，以下是最终可用证据：

| 文件 | 实际证明 |
|---|---|
| `24-desktop-final-list.jpg` | 四项桌面导航、真实混合状态、计数与信息密度 |
| `20-desktop-ready-customer.jpg` | 已批准人物、正式可创作的搜索/筛选卡片 |
| `21-mobile-ready-customer-safe-area.jpg` | 390×844 实际滚动后主按钮位于底部导航上方 |
| `22-mobile-scoped-creation.jpg`、`02-customer-scoped-creation.jpg` | 客户定向创作，不重复选客户 |
| `23-empty-creation-records.jpg` | 准确客户的真实空记录/无交付 |
| `03-task-request-entry.jpg`、`04-original-request-restored-fixed.jpg` | Task → 原 Request，修复旧轮询覆盖后稳定恢复 |
| `05-customer-creation-records.jpg`、`14-mobile-creation-history.jpg`、`15-mobile-original-request.jpg` | 桌面/手机历史与恢复 |
| `07-core-conflict-detail.jpg`、`09-analysis-failure-recovery.jpg` | 核心 Gate 与原分析恢复入口 |
| `19-business-approved-speaker-pending.jpg` | Business 批准不冒充 Speaker 批准/可创作 |
| `10-mobile-list-390-top.jpg`、`11-mobile-last-card-safe-area.jpg`、`12-mobile-more-menu.jpg`、`13-mobile-narrow-320.jpg` | 真实滚动、菜单、窄手机不横溢、最后卡片可操作 |
| `16-desktop-filter-restored.jpg` | 迟到响应修复后返回恢复搜索/筛选 |
| `17-workbench-current.jpg`、`18-shared-account-customer.jpg` | 工作台入口、另一账号合法共享读取 |
| `25-legacy-global-creation.jpg` | 旧无客户 /create 路由保留并引导选择 |
| `26-mobile-tasks.jpg`、`27-mobile-workbench.jpg`、`28-mobile-cases.jpg` | 手机四项导航实际打开 |

历史调试图 `01-*`、未带 `fixed` 的 `04-original-request-restored.jpg`、`08-desktop-operational-list.jpg` 与 `16-mobile-filter-restored.jpg` 保留用于追溯，**不作为最终 PASS 证据**。截图/轨迹 Hash 索引在 `browser-acceptance.json`。

390×844 列表 DOM 宽度 375，320 窄视口宽度 305，未横向溢出。主要按钮/作品记录、更多菜单、分页、搜索筛选、手机创作上下文均经过真实点击；临时 viewport override 已 reset。

## H. 权限、Authority 与生产 Gate

- 页面访问和搜索都是只读；默认动作没有创建 Human Review、Persona、Request 或 Task。
- 新建与继续 Request 仍使用原 Gateway；服务器验证真实客户、原 Request/Business/profile、Persona/Speaker binding、正式 Entry 与 Constraints，不信前端 ID。
- 新专项 formal Golden HTTP 测试只注入模型输出，实际执行 Fact Review、Business Approval、Speaker 独立 Review/Approval、Creation Preview/Confirm；删除精确 Compatibility sidecar 后 Entry 必须拒绝可创作。
- R2 核心冲突优先于旧 Approved R1 与运行任务；新旧 Approval/Receipt/SHA 不改写；Speaker 精确 Business revision 复核不自动继承。
- Customer Truth、Speaker 本人经历、Case/Pattern、Rights、Compatibility 与生产 Truth Owner 未改；没有把业务事实预选规则套用 Speaker 本人审核。
- News 原 fail-closed 保持；没有通过新导航或卡片打开未适配消费路径。
- 现有 auth、CSRF、操作锁、服务端 actor、共享权限、幂等、人工审核与导出回归均经过正式全仓验证。
- 虚构 fixture 的 Case 媒体权利为 false；脚本入口可用不授予视频生产/发布权利。

## I. 测试与完整回归

| 检查 | 本次结果 / 收据 |
|---|---|
| 最终专项/HTTP/JS bridge/受影响页面 | 31 PASS，`focused-final.xml`；其中本轮新导航专项 22 参数化用例 |
| 受影响 UI/Creation/内容管理断言 | 21 PASS，`presentation-amendment.xml`，与上一行有重叠，不累加报总数 |
| Customer/Speaker revision 受影响 Integration | 短路径 18 PASS，`revision-short-path.xml`，正式 Full 再次 18 PASS |
| Full Pipeline | 467 PASS |
| Full Console，5 个 shard | 395 PASS（106 + 62 + 92 + 117 + 18） |
| Full Authority release | 12 PASS，离线测试，无部署 |
| Full FRP Guard | 30 PASS，仅 root route 的离线检查，无 FRP 配置/外部操作 |
| Full verifier | 25 PASS |
| 合计 Python | **929 PASS / 0 failures / 0 errors / 0 skipped**，69.151s |
| Console JS | Node v24.18.0，17 文件 / 20 native Node tests PASS；Python 总数已包括一个 JS bridge，不再把 native 数重复加总 |
| Python compile | 本轮 Python 改动与新增模块 compileall PASS |
| migrations/schema/历史兼容 | root Full 中既有 Console migration/hardening、Persona/revision、frozen Authority 等测试 PASS；本轮无 Schema/migration 变更 |
| diff | `git diff --check` PASS |
| live Authority | 默认 opt-in 排除，**未执行、不计入通过** |
| 真实模型/生产 | DeepSeek/Qwen/Whisper/Qiyun 0 次；4090/生产验收未执行 |

正式命令：在 worktree 根运行 `internal-console\.venv\Scripts\python.exe tools\verify.py`。最终收据 `.verify/65d245c0/summary.json` 状态 passed、`state_unchanged=true`、全目标实际执行、无缓存结果复用；Console JS 原始收据 `.verify/65d245c0/3/javascript.json` 与 `javascript.log`。

先前失败均保留：局部 revision Integration 的深层 Windows 路径 4 项失败，移到项目短 `.verify` 路径后通过；第一次 Full `.verify/0d2df9c5/` 的 2 项旧 UI 目标断言仍要求目录卡片/全局选客户，本轮按批准目标更新展示断言，既有安全断言不削弱，Focused 后重跑完整 Full 成功。Verifier 自身会故意构造失败的 JS 子运行检查错误传播；该负向 fixture 的 exit=1 不代表 Console JS 失败。

完整回归后仅补充本报告、导航索引和本机证据，运行代码与测试未再修改。

## J. 历史数据与运行环境保护

`protection-before.json` → `protection-after.json` 的最终检查：

- 主 Canonical 946、历史 cs3node 207、cse2node02 98、csuxnode01 138：**共 1389 个 JSON 原 SHA 全部不变**。
- 5 个原数据库所有非 sessions 表的行数与内容摘要不变；包括现有 18013 DB。sessions 是合法运行心跳，未以恢复旧 DB 的方式追求文件相同 SHA。
- main HEAD 保持本次基线，main status clean；只在新 worktree 修改代码。
- 旧 Raw、Candidate、Review、Persona、Receipt、Request、Ledger，以及旧 runtime 没有删除、覆盖或重算 SHA。
- 纯导航窗口内新 UAT 原请求/任务不变，具体范围见 E 节；之后 B 的合法虚构新建与独立人工审核单独记录，不能与只读保护混淆。
- 18015 `/api/health` 实测 `{status: ok}`。18013 PID 30888 保持；没有第二个 Console 操作同一运行数据库。

模型费用保护：隔离 launcher 初始化前真实 worker 全部禁用，清除 provider 凭证，模型边界固定虚构输出；外连 socket guard 阻断联网（仅允许 Windows asyncio 标准库内部 loopback socketpair）；extractor 子进程也禁止网络。原 Canonical 只读 adapter 子进程没有执行模型操作。queued content_plan 没有 worker 消费。合成能力验收与真实模型能力明确分离。

## K. 剩余风险与 Founder 验收建议

1. **真实模型质量、真实媒体、真实导出交付及 4090 未验收**。本轮 browser D 验证历史恢复；没有伪造真实内容生成/生产 PASS。
2. 新限制合同下未适配 News 路径继续阻断；Novel 仍受原 rollout 与正式条件。不得因 UI ready/filter 放行。
3. 25 客户专项证明聚合 SQL/分页口径，不代表大规模 Canonical/Novel 历史性能基准；文件 Owners 仍需逐对象校验。一个无法读取的 Request 全局索引会使记录/待办计数整体未知，属于显式保守降级。
4. 旧历史 fixture 缺展示姓名时展示稳定 ID，不编造人物/客户；新正式 Golden 能证明完整公开摘要。
5. Founder 可在 `http://127.0.0.1:18015/customers` 验收隔离虚构客户：优先看 B 的「开始创作」、A 的「处理中/原请求」、C 的资料/冲突/失败恢复，再试手机搜索、返回和作品空状态。页面明确标注规则模拟；不要把它作为真实客户模型识别环境。
6. 本轮工程结论是离线 Product Review Candidate，等待独立产品与架构验收；不自动提交、部署或进入 E3。

**`NAV1_CUSTOMER_LIST1_READY_FOR_PRODUCT_REVIEW`**
