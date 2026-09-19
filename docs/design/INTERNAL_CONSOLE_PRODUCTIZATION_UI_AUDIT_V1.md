# Internal Console Productization UI/UX V1

## Gate 1 — Current Surface & Information Audit

Audit date: 2026-09-20

Repository checkpoint: `14b9de1fc80a5a9b8cb5ffb359fd9794abeb7bc7`

Audit mode: current-state, read-only product surface audit

Audited application: `internal-console`

This report records the current UI truth. It does not propose a redesign, new wording, new behavior, or a new design system. Dynamic values supplied by APIs or business artifacts are described by field rather than copied from production data.

### Evidence and limits

- Route and rendering evidence: `internal-console/static/assets/*.js`.
- Visual evidence: `internal-console/static/assets/styles.css` and `internal-console/static/index.html`.
- Public-edge reachability: `https://ops.jingtang.cc` was reachable, but the user identified that deployment as older than the audited local code. It was excluded from current-UI visual evidence.
- Current visual evidence was collected from the authenticated local runtime at `http://127.0.0.1:8000`, after the user completed login directly. The runtime served the checked-out files at the checkpoint above.
- Navigation and viewport changes were read-only. No form was submitted, no task or review action was triggered, and no customer, case, task, or other business authority was created or changed.
- Viewport screenshots were captured during the audit for all eight requested surfaces at 1440×900 and 390×844. They were not persisted to the repository because they contain real local customer, case, and task data. The Screenshot Index records the capture result.
- The same eight surfaces were also measured at 430×932 and 1792×900. Responsive conclusions below distinguish observed runtime evidence from source-derived behavior for lifecycle states that were not active.

## 1. Surface Inventory

“Primary count” is audited separately in section 5. Embedded surfaces keep the parent route because they replace or extend content within that route rather than owning a separate URL.

| Surface ID | Surface | Route | User Goal | Primary Action | Secondary Actions | Displayed Information | Status / Empty / Error Variants | Desktop Layout | Mobile Layout | Source files |
|---|---|---|---|---|---|---|---|---|---|---|
| S01 | Login | `/login` | Enter the internal console | 登录 | None | Brand, internal-use label, phone and password fields | Submitting state; API message in form error | Centered auth card, max 440 px | Same single card with 20 px page inset | `index.html`, `app.js`, `styles.css` |
| S02 | Change Password | `/change-password` | Replace initial or current password | 保存并进入工作台 / 保存新密码 | 返回工作台 when not first login | Current password, new password, confirmation, minimum-length hint | First-login and voluntary-change copy; submitting; API form error | Centered auth card | Same single card | `app.js`, `styles.css` |
| S03 | Workbench | `/workbench` | See current operational attention and start common work | No singular button; quick-start cards are the main entry set | Four attention links; current customer summary | Attention counts, operational hold/next action, quick starts, selected customer summary and capacity | No customers; customers exist but none selected; selected status; load error | At ≥1024 px, operational card and 2×2 attention grid form a two-column dashboard; quick starts use three columns | All blocks stack; quick starts stack; fixed bottom nav remains visible | `app.js`, `styles.css` |
| S04 | Case Library | `/cases` | Browse and filter cases | + 添加案例 | Filter 全部 / 待审核 / 已入库; 查看案例 | Case title, status, source, duration, profile, industry, summary | Populated list; empty library; load error | Three-column cards at ≥1024 px, two at ≥680 px | Single-column cards; horizontal filter row | `case-views.js`, `case-components.js`, `styles.css` |
| S05 | Add Case | `/cases/new` | Submit a Douyin URL for analysis | 分析这个案例, then a lifecycle-specific CTA | 粘贴; 添加另一个案例 | URL, source detection, rights boundary, duplicate or task result | Idle; submitting; queued/running; awaiting review; approved; rejected; failed; exact-media duplicate; form/API error | At ≥1024 px, URL panel plus boundary aside | Single column; action container is sticky above bottom nav | `case-views.js`, `case-submit-state.mjs`, `case-components.js`, `styles.css` |
| S06 | Case Analysis Progress | Embedded in `/cases/new`; `/tasks/{task_id}` for case tasks | Track actual analysis stages | Contextual 去审核案例 when ready; otherwise none | 查看已有案例 on media duplicate; return through navigation | Progress %, current stage, five stages, failure detail, next action | queued/running; awaiting_review/completed; failed; media duplicate | Full progress card; static action placement on desktop | Full progress card; may sit above sticky case action and bottom nav | `case-components.js`, `case-views.js`, `task-progress.js`, `app.js`, `styles.css` |
| S07 | Case Review | `/cases/{case_id}` | Compare source media with structured analysis and decide admission | 批准入库 or 完成审批恢复 | 退回重新分析; 不收录; source link; expand full breakdown | Media/embed, title, source, duration, description, cleanup notice, rights warning, topic, expression, narrative structure, reusable observations, narration, shots | Local media vs Douyin embed; awaiting review; approved; approval recovery; rejected/reanalysis through surrounding flow; load error | Media/meta split at ≥900 px; review decision becomes sticky right aside at ≥1280 px | Single column; decision follows content; mobile review action class exists; fixed nav remains | `case-components.js`, `case-views.js`, `styles.css` |
| S08 | Customer List | `/customers` | Browse customer lifecycle state | + 新建客户 | 查看客户 | Customer name, industry, lifecycle status, customer profile status, speaker count | Populated; no customers; load error | Three columns at ≥1024 px, two at ≥680 px | Single-column cards | `customer-views.js`, `customer-components.js`, `styles.css` |
| S09 | New Customer | `/customers/new` | Submit known customer material for analysis | 分析客户信息 | None | Name, industry, source material, local/privacy note, two-stage review explanation | Submitting; duplicate customer; task starts; API/form error | Form and explanatory aside in two columns at ≥1024 px | Stacked form and notice | `customer-views.js`, `customer-components.js`, `styles.css` |
| S10 | Customer Analysis | Embedded in `/customers/new`, `/customers/{business_id}`, and task detail | Track extraction of customer facts | 继续分析 in failed state; otherwise none while running | 修改已有资料 in recovery paths | Progress %, five processing stages, retained failure detail | analysis_pending/analyzing; awaiting review; completed; failed; unknown lifecycle fallback | Progress card in page flow | Same stacked card | `customer-views.js`, `customer-components.js`, `task-progress.js`, `styles.css` |
| S11 | Customer Fact Review | `/customers/{business_id}` when `fact_review_required` | Decide which extracted facts may enter reviewed customer truth | 确认这些信息 | Per fact: 确认 / 修改 / 不采用; evidence disclosure | Known facts, review candidates, source excerpts, editable values, count awaiting review | Known-only section may be absent; per-field edit state; validation/API error | Fact cards in a vertical list; sticky action becomes static and max 360 px at desktop | Vertical list; sticky submit above bottom nav | `customer-views.js`, `customer-components.js`, `styles.css` |
| S12 | Customer Persona Review | `/customers/{business_id}` when `persona_review_required` | Perform the second human gate on the complete customer profile | 确认并建立客户档案 | Back/navigation only | Confirmed facts, second-gate explanation, production suitability warning | Ready for persona review; API error | Vertical facts plus authority banner; desktop action constrained | Stacked with sticky action | `customer-views.js`, `customer-components.js`, `styles.css` |
| S13 | Approved Customer | `/customers/{business_id}` when `approved` | Inspect approved customer context and continue to people/content work | 开始创作 when ready; otherwise + 添加出镜人 | 内容运营; + 添加出镜人; open a speaker | Customer status, speaker count, speaker cards, creation readiness, approved facts, rights boundary | No speakers; speakers present but creation not ready; creation ready; load error | Overview two columns; speaker grid up to three columns; readiness row | Sections stack; readiness actions wrap/stack | `customer-views.js`, `customer-components.js`, `speaker-components.js`, `styles.css` |
| S14 | Speaker List | Embedded in approved customer detail | See all people attached to a customer | + 添加出镜人 when empty; otherwise no singular primary | Open speaker; add another speaker | Name, public role, speaker lifecycle status, authority separation note | Empty; one or more speakers with mixed lifecycle states | Three-column grid at ≥1024 px, two at ≥680 px | Single-column list | `customer-views.js`, `speaker-components.js`, `styles.css` |
| S15 | New Speaker | `/customers/{business_id}/speakers/new` | Submit known speaker facts | 分析出镜人信息 | Return via navigation | Name, public role, type, materials, forbidden claims, persona/media-rights explanation | Customer not approved blocker; submitting/task; duplicate/error | Form and explanatory aside use customer-new two-column pattern | Stacked form and notice | `speaker-views.js`, `speaker-components.js`, `styles.css` |
| S16 | Speaker Analysis | Embedded in new/detail routes and task detail | Track speaker fact extraction | None while running; recovery action in failed state | Navigation/back | Progress %, five stages, retained failure detail | pending/analyzing; awaiting review; completed; failed; unknown lifecycle fallback | Progress card in page flow | Same stacked card | `speaker-views.js`, `speaker-components.js`, `task-progress.js`, `styles.css` |
| S17 | Speaker Review | `/customers/{business_id}/speakers/{speaker_id}` | Review speaker facts, then approve the speaker persona | 确认这些信息 or 确认并建立出镜人设, by phase | Per fact confirm/edit/reject; evidence disclosure | Business-fact boundary, speaker facts, source evidence, complete persona review, approved facts and media-rights boundary | fact_review_required; persona_review_required; approved; needs_more_info; failed; analyzing; unknown status | Vertical review cards; approved overview uses two columns | Single-column review; sticky phase action | `speaker-views.js`, `speaker-components.js`, `customer-components.js`, `styles.css` |
| S18 | Content Creation Entry | `/create` | Select customer, speaker, mode and quantity | 检查内容容量 | Mode choices; customer/speaker selects; lifecycle recovery links after submission | Customer, speaker, Mix/News mode, quantity, authority explanation | No eligible customer/speaker; selection required; loading/restoring active request; request authority error | One full-width workflow aligned to page container | Full width; controls and mode cards stack as CSS breakpoints require | `content-views.js`, `styles.css` |
| S19 | Content Capacity | Embedded in `/create` after capacity check | Understand capacity and explicitly confirm a request | 确认数量并建立创作请求 when eligible | Change form inputs before confirmation | Capacity number, requested number, remaining number, history, gaps, authority note, rights note | Ready; limited; exhausted/blocked; unavailable profile; temporary failure | Three metric cells; same workflow width | At ≤390 px, three metrics become stacked key/value rows | `content-views.js`, `styles.css` |
| S20 | Generation / Delivery | Embedded in `/create` for Mix | Move from request to content plan, scripts, human review, and Excel delivery | One lifecycle CTA at each stage: generate plan, generate scripts, submit review, export, or download | Source-plan recovery; per-script approve/revise/reject; approve-all; authority disclosure | Request metadata, source-planning state, selected topics, generated scripts, review flags, revision fields, export receipt and filename | Request established; source handoff missing; task running/failed; plan ready; scripts ready; human review; nothing exportable; exported | Four-step progress; script cards become two columns at ≥680 px | Stepper becomes 2×2 at ≤430 px; script cards stack; action rows stack | `content-views.js`, `content-delivery-views.js`, `styles.css` |
| S21 | News Flow | Embedded in `/create` for News | Reuse eligible historical content as News titles, review them, and export | One lifecycle CTA at each stage: establish request, generate title plan, submit review, export, or download | Source selection; per-title pass/revise/reject; request recovery | Historical source choices, source facts, requested count, title candidates, review decisions, export receipt, presentation history | No eligible history; preview; active request; plan task; review; no exportable item; exported; request authority error | Source cards list; review cards become two columns at ≥680 px; three-step progress | Single-column source/review cards and actions | `content-views.js`, `news-delivery-views.js`, `styles.css` |
| S22 | Task List | `/tasks` | See shared task execution state | No singular primary in populated state | 查看任务; empty-state 添加案例 | Task type, subject/stage, progress %, compact status projection | Populated; empty; load error | Vertical task list across page width | Same vertical list | `app.js`, `case-components.js`, `customer-components.js`, `speaker-components.js`, `styles.css` |
| S23 | Task Detail | `/tasks/{task_id}` | Inspect one task and recover business state | Varies by task type; generic detail has 返回任务记录 | Type-specific recovery/navigation | Full progress, task stage, task/business distinction | Case/customer/speaker/content/excel dispatch; generic running/completed/failed; load error | One detail column | One detail column | `app.js`, the three workflow view modules, `content-views.js`, `styles.css` |
| S24 | Empty States | Embedded throughout | Understand why a collection or workflow has no usable item | Contextual entry when available | Navigation | Empty reason and next entry: no customer, no case, no task, no speaker, no eligible create customer, no content work | At least eight distinct empty projections | Centered empty card or domain-specific empty strip/card | Same; full-width in parent flow | `app.js`, all workflow view modules, `styles.css` |
| S25 | Error States | Embedded globally and per operation | Understand that loading/action failed and what can be done | 重新尝试 globally; operation-specific retry/recovery | Back/navigation; API `next_action` | Raw API message, optional next action, retained task failure, form validation | Global load error; form error; result banner error; task failure; authority recovery error; toast | Card/banner/form placement in current layout | Same, sometimes adjacent to sticky action/nav | `app.js`, all workflow view modules, `api-client.js`, `styles.css` |
| S26 | Mobile Navigation | All authenticated routes below 1024 px | Move among five main areas | Center 创作 orb is visually prominent | 工作台 / 案例 / 客户 / 任务 | Current active destination | Fixed on every authenticated surface | Hidden at ≥1024 px | Fixed five-column bottom nav with safe-area inset | `app.js`, `styles.css` |
| S27 | Desktop Navigation | All authenticated routes at ≥1024 px | Move among five main areas and account actions | 视频创作 is coral-highlighted | Other four routes; change password; logout | Brand, nav labels, masked phone, product footer, current page title | Active-link variant | Fixed 252 px sidebar plus sticky 76 px topbar | Sidebar hidden; mobile brand and bottom nav replace it | `app.js`, `styles.css` |
| S28 | Customer Edit / Reanalysis | `/customers/{business_id}/edit` | Correct retained source information and start a new analysis intake | 重新分析客户信息 | Return through navigation | Existing name, industry, materials, explanation that a new Intake is created | Submitting; new task; API/form error | Single edit card in page container | Same stacked form | `customer-views.js`, `styles.css` |
| S29 | Customer Content Operations | `/customers/{business_id}/content` | Inspect customer-level content work, capacity, in-flight work, and deliveries | 开始创作 | Return to customer; download recent delivery; expand authority details | Mix/News delivery totals, capacity, current work, recent exports, speaker-selection state | No work; no deliveries; ready/quiet capacity; selection required; load error | Custom max width 1180 px; four overview cards, structured work and delivery lists | At ≤1040 px overview becomes two columns; at ≤760 px one column and full-width actions | `content-operations-views.js`, `styles.css` |
| S30 | Boot and Loading | Initial load and before async route resolution | Wait for identity or route data | None | None | Logo, product name, “正在打开工作台…”; route skeletons | Boot; two-card skeleton page | Centered boot; page skeleton after shell loads | Same; shell uses mobile navigation once authenticated | `index.html`, `app.js`, `styles.css` |
| S31 | Transient Feedback and Browser Dialogs | Overlay on current route | Receive short action feedback or confirm a consequential mutation | Confirm/OK in native dialog when invoked | Cancel; toast auto-dismiss | Toast messages; `confirm()` approval/reanalysis prompts; `prompt()` reanalysis reason | Success/error toasts; confirm accepted/cancelled; prompt filled/cancelled | Toast top-right, max 360 px; native browser dialogs | Toast nearly full viewport width; native browser dialogs | `app.js`, workflow view modules, `styles.css` |
| S32 | Excel Download | Triggered from `/create` or `/customers/{business_id}/content` | Download a completed approved export | 下载 Excel / download action | Return to surrounding workflow | Exported filename, count/profile/customer/speaker metadata, receipt-derived completion projection | Export pending; no exportable content; export task running/failed; exported | Button within delivery success card/list row | Full-width or stacked action depending parent breakpoint | `content-delivery-views.js`, `news-delivery-views.js`, `content-operations-views.js`, `api-client.js` |

## 2. Information Inventory

### 2.1 Classification

| Code | Category | Current examples |
|---|---|---|
| B | User-facing business language | 客户、出镜人、案例、视频创作、审核、导出、内容容量 |
| O | Necessary operational language | 排队中、分析中、等待审核、重新分析、任务进度、下载 Excel |
| P | Product explanation | “系统会先检查是否已经分析过”、流程 and next-step explanations |
| G | Governance / risk explanation | Rights boundaries, human gates, privacy projection, facts not automatically entering production |
| E | Engineering / architecture language | Authority, canonical, artifact, Request ID, Profile, Intake, ledger/handoff names |
| D | Debug / implementation language | Raw status fallback, raw API error strings, JSON rendering, task IDs, unexpected enum values |

### 2.2 Visible text coverage by surface family

This table records all current static text families. Repeated button labels such as “查看任务” are listed once in their owning family. Dynamic customer names, facts, titles, source excerpts, counts, errors, stages, IDs, and filenames are identified as fields.

| Surface family | Current visible text and dynamic fields | Categories |
|---|---|---|
| Global shell | 鲸汤AI视频 / 代运营工作台; 工作台; 案例库/案例; 视频创作/创作; 客户与人设/客户; 任务记录/任务; 修改密码; 退出登录; 内部生产工作台 · V1; masked phone; current page title | B, O, P |
| Boot | 鲸汤AI视频代运营工作台; 正在打开工作台… | B, O |
| Login | 内部运营专用; 欢迎回来; 登录后继续处理案例、客户与视频创作任务。; 手机号; 密码; placeholders; 登录; 正在登录…; API error | B, O, P, D |
| Change Password | 账号安全; 首次登录 / 修改密码; current/new/confirm password; 至少 8 个字符，不能继续使用初始密码。; 保存并进入工作台 / 保存新密码; 返回工作台; API error | O, P, D |
| Workbench | 今日; 今天需要做什么; attention summary; 已暂停/可以继续; 客户联系已暂停/客户运营可以继续; 当前下一步; 当前客户; 当前可用; 客户档案; 出镜人设; 剩余内容空间; 最近批次; 快捷开始; 添加案例; 新建客户; 开始视频创作; 还没有客户; 尚未选择当前客户; dynamic customer/count/status/next action | B, O, P |
| Case Library | 案例; 案例库; rights description; + 添加案例; 全部/待审核/已入库 counts; title/source/duration/profile/industry/summary; 查看案例; 案例库还是空的 | B, O, G, E |
| Add Case | 添加一个视频案例; video URL instruction; 视频链接; 粘贴视频链接; 粘贴; source detection states; 分析这个案例; 案例使用边界; duplicate/reanalysis messages; 去审核案例; 查看已有案例; 重新分析; 添加另一个案例 | B, O, P, G |
| Case Progress | 获取视频; 提取语音; 分析画面; 理解内容结构; 生成审核结果; 案例分析中; 分析完成，等待审核; 案例分析未完成; progress %; dynamic stage/error; leave-page persistence; duplicate-media explanation | O, P, D |
| Case Review | 返回案例库; source metadata; 在抖音打开原视频; cleanup notice; rights banner; 这个视频在讲什么; 内容主题; 核心表达; 它是怎么讲的; 开头/中段/结尾; 值得学习的结构; 查看完整拆解; 完整口播; 画面拆解; 口播/画面/画面文字/作用; 人工审核; approve/reanalyze/reject/recovery labels | B, O, P, G, E |
| Customer List | 客户; 客户与人设; AI/human-review explanation; + 新建客户; name/industry/status; 客户档案; 出镜人; 查看客户; 还没有客户 | B, O, P, G |
| New/Edit Customer | 新建客户; 先把你已经知道的放进来; 客户名称; 行业; 已有资料; 分析客户信息; local Authority/privacy projection hint; 这一步不会建立正式客户档案; fact review then Business Persona explanation; 修改已有资料; new Intake explanation | B, O, P, G, E |
| Customer Analysis | 保存客户原始资料; 隐私检查; 提取事实候选; 评估信息完整度; 生成审核结果; analysis titles; progress %; stage/error; leave-page persistence; 继续分析 | O, P, G, D |
| Customer Fact Review | 客户信息审核; AI fact-candidate explanation; 已经明确的信息; 已确认; 需要你确认; Customer Truth sentence; 查看依据; 修改后的事实; list-entry hint; per-fact choices; 确认这些信息; dynamic facts/source excerpts | B, O, P, G, E, D |
| Customer Persona Review | 客户档案审核; Business Persona sentence; second human gate; 将进入正式档案的信息; fact count; 确认并建立客户档案 | B, O, P, G, E |
| Approved Customer / Speaker List | 客户档案已批准; speaker count; Approved Business Persona; Approved Speaker Persona; Persona 条件已完成; 可以进入创作流程; 内容运营; 开始创作; 出镜人; + 添加出镜人; approved facts; rights boundary | B, O, P, G, E |
| New/Review Speaker | 添加一个出镜人; Speaker Persona explanation; name/role/type/materials/forbidden claims; 两件事保持独立; media-rights note; Business Fact boundary; Speaker Facts/Truth; evidence, edit and decision labels; second gate; approved/needs-info/failure messages | B, O, P, G, E, D |
| Create Entry / Capacity | 创作; customer/speaker/mode/count fields; Mix 素材混剪 / 数字人口播混剪; News 新闻体内容; 检查内容容量; Product explanations; capacity state, metrics and gaps; 当前 Authority 状态; Content Ledger; Customer Truth; rights boundary; establish-request CTA | B, O, P, G, E |
| Mix Generation / Delivery | Generation Request 已建立; Request ID; Profile; Source Planning Handoff; immutable/canonical request explanations; Content Plan; 本轮最终选题; 用户问题; 核心表达; 审核生成稿; 模型原始标题/口播; Central Claim; Authority 信息; Review flags; Approved Projection; Historical Exposure; export metadata; download | B, O, P, G, E |
| News Flow | News title plan; historical core; Cross-profile Repurpose; source facts; Known Fact; Authority Field; pass/revise/reject; Excel exported; semantic addition = 0; Presentation History; current not Novel Content Generation; remote model wording in task action; request/export fields | B, O, P, G, E |
| Task List/Detail | 任务; 任务记录; task/business distinction; task type; stage; progress; 查看任务; 返回任务记录; task complete then canonical artifact reread; empty state; raw task/API failure detail | O, P, E, D |
| Content Operations | 内容运营; customer/speaker summary; delivered counts; capacity; current work; recent deliveries; download; empty strips; speaker selection required; authority details; canonical Authority | B, O, P, E |
| Errors/feedback | Error; operation-specific failure title; raw `error.message`; 下一步; API `next_action`; 重新尝试; validation messages; toasts; raw unexpected status | O, P, D |

### 2.3 Required concept audit

“Can hide from default UI?” is an information-layer classification only; it is not a wording or implementation proposal.

| Current Text | Surface | Category | Why it is shown | Can hide from default UI? |
|---|---|---|---|---|
| `Authority`, `当前 Authority 状态`, `News Request Authority 异常`, `Active Request Authority 异常` | Customer intake/detail, Speaker review/detail, Create, News, Content Operations | G + E | Communicates which approved source governs a mutation or why recovery is blocked | Partly. Rights/human-gate meaning is governance-facing; the English architecture noun and recovery labels are implementation-facing. |
| `canonical Request`, `canonical artifact`, `canonical Authority` | Create, generic Task Detail, Content Operations | E | Explains immutable recovery source and the separation between task completion and business completion | Yes for default UI; it is architecture vocabulary. |
| `Customer Truth` | Customer Fact Review, Customer needs-more-info, Create capacity/delivery | G + E | Marks facts that have passed human confirmation and the source for content claims | Partly. The user consequence is governance; the formal authority name is internal architecture vocabulary. |
| `Business Persona`, `Approved Business Persona` | Customer onboarding/review/detail, Speaker onboarding, Create | G + E | Distinguishes the customer-wide approved profile from speaker-specific permissions | Partly; the distinction is operationally relevant, while repeated formal English naming is not required to perform every action. |
| `Speaker Persona`, `Approved Speaker Persona` | Customer detail, Speaker onboarding/review/detail, Create | G + E | Defines first-person speaking scope and keeps it separate from media rights | Partly; the permission boundary is necessary, the formal English label can be non-default. |
| `Content Ledger` | Create capacity and request explanations | G + E | Explains that exported content history persists and constrains novelty/capacity | Partly; remaining-capacity consequences are user-facing, the ledger implementation name is architecture-facing. |
| `Generation Request` | Create, capacity confirmation, delivery recovery | O + E | Names the durable unit established after a capacity check | Partly; operators need to recognize the active request, but repeated formal lifecycle explanations are not required on every default state. |
| `Source Planning Handoff` | Create request result and recovery | E | Exposes the boundary between an established request and source planning | Yes; this is an internal workflow/architecture handoff name. |
| `Profile`, `Production Profile`, `Cross-profile Repurpose` | Case metadata, Create, News | E + P | Labels Mix/News modes and explains that mode changes do not create new semantics | Partly; mode is necessary, formal “Profile” terminology is implementation/product-model language. |
| `Attempt` | Case approval recovery prompt and review warning | E | Identifies an idempotent case-analysis/approval execution lineage | Yes; it appears only in recovery explanation and is implementation language. |
| `artifact` | Case approval recovery, Create, Task Detail | E | Explains durable result publication and recovery | Yes; it is implementation language. |
| `Provider` | No static user-visible occurrence found | — | Not currently shown | Not applicable. |
| `Consumer` | No static user-visible occurrence found | — | Not currently shown | Not applicable. |
| `Schema` | No static user-visible occurrence found | — | Not currently shown | Not applicable. |
| `Hash` | No static user-visible occurrence found | — | Not currently shown | Not applicable. |
| `模型`, `模型原始标题`, `模型原始口播` | Customer intake hint, Mix Human Review | P + E | Explains privacy projection and distinguishes generated source text from reviewed text | Partly; original-vs-reviewed provenance is relevant, model implementation detail is not needed everywhere. |
| `Remote Model` | No exact static user-visible English occurrence found; Chinese copy refers to “远程模型” in generation task states | E | Indicates an external generation stage | Yes for default UI; operator-facing stage can remain without architecture naming. |
| `Local Model` | No exact static user-visible occurrence found | — | Not currently shown | Not applicable. |
| `Request ID` plus dynamic request ID | Generation Request result | E + D | Supports request identity and recovery tracing | Yes from the default summary; useful diagnostic/detail information. |
| `Batch ID` | No exact static user-visible occurrence found | — | Not currently shown | Not applicable. |
| Technical status enums | Fallback status pills, customer/speaker unknown-state page, API errors and task payload-derived state | D | Used when no humanized mapping exists or an unknown lifecycle state reaches the UI | Yes from default UI; current code can expose them because fallbacks render raw values. |
| Raw JSON for object-valued fact | Customer/Speaker fact review | D | Generic renderer displays object-shaped extracted facts | Yes from default UI; currently visible by design of the generic field renderer. |
| `Intake` | Customer edit/reanalysis | E | Explains that reanalysis creates a new retained input lineage | Yes; it is lifecycle implementation vocabulary. |
| `companion` | Case approval recovery | E | Names the secondary publication repaired during recovery | Yes; it is implementation vocabulary. |
| `Central Claim（Revision 不可修改）` | Mix Human Review | G + E | Freezes the semantic claim while allowing copy edits | Partly; the restriction is governance-relevant, the mixed English/revision label is product-model vocabulary. |
| `Approved Projection`, `Historical Exposure`, `Presentation History`, `Semantic Ledger` | Mix/News review and export | G + E | Explains what approved or rejected content will enter and how historical reuse is recorded | Partly; consequences matter, formal storage/projection terms are architecture-facing. |

### 2.4 Status and error visibility

- Humanized case/task statuses: 已入库, 待审核, 分析中, 排队中, 进行中, 已完成, 失败, 已归档.
- Humanized customer statuses: 已批准, 信息待确认, 档案待确认, 分析中, 待分析, 需补充, 分析失败, 未完成.
- Humanized speaker statuses: 人设已批准, 事实待确认, 人设待确认, 分析中, 待分析, 需补充, 分析失败, 未完成.
- Any unmapped status is rendered as the raw status string by the pill functions or “当前状态” fallback views.
- Global load errors render the API `error.message` as the page description and an API-provided `next_action` in the card.
- Form and result errors also render API messages directly. This makes backend wording part of the current user-visible information surface.

## 3. Visual Primitive Inventory

### 3.1 Global primitives

| Primitive | Current implementation |
|---|---|
| Color | `--paper #f6f3ed`, `--paper-strong #fffdf9`, `--ink #1d2522`, soft/faint ink, two line colors, forest/forest-strong, mint, coral/coral-soft, amber/amber-soft, red/red-soft. Body adds a pale coral radial gradient. |
| Typography | Inter, SF Pro Display, PingFang SC, Microsoft YaHei, then system sans. Page H1 uses `clamp(29px, 8vw, 46px)` and tight negative tracking. Body/help text is generally 11–14 px with 1.5–1.75 line height. IDs/JSON use monospace in selected components. |
| Spacing | No named spacing tokens. Repeated values cluster around 8–18 px within controls/cards, 22–30 px between sections, and 32–56 px page edges, with additional one-off values. |
| Radii | Tokens: 24 px large, 18 px medium, 12 px small. Controls commonly use 11–14 px; pills are fully rounded. |
| Shadows | Global shadow token `0 18px 45px rgba(35,44,40,.08)`; cards use a lighter `0 10px 28px rgba(35,44,40,.035)`; sticky actions/nav and create orb have separate shadows. |
| Buttons | Global `.btn` base, primary forest, secondary bordered paper, quiet text, full-width and compact variants; 46 px minimum height (38 px compact). |
| Cards | Global `.card` border/background/radius/shadow. Domain cards add padding, background, side accent, status color, grid or list behavior. |
| Status pills | Global `.pill` with approved/review/failed/archived color variants. Domain-specific badge families also exist in delivery and content operations. |
| Inputs | `.field input`, `textarea`, and `select` share border/radius/focus-ring conventions, but their definitions are separate. News title and revision controls define additional local input styles. |
| Page width | Global `.page`: `min(100%, 1120px)`. Content Operations overrides to `min(100%, 1180px)`. |
| Sidebar | Hidden below 1024 px; fixed 252 px at desktop; dark forest background; five nav links; persistent footer. |
| Topbar | Sticky, 68 px mobile and 76 px desktop, blurred paper background, current page title, account actions. |
| Mobile nav | Fixed five-column bottom navigation, safe-area aware, center create orb raised 17 px. Main content reserves 82 px plus safe area. |
| Tables/lists | No data-table primitive is used. Collections use responsive card grids, vertical bordered lists, filter chips, disclosure blocks, or progress lists. |
| Empty states | Global centered `.empty-state`; additional `speaker-empty-card`, content-operation empty strips, and delivery-specific empty success/blocker cards. |
| Alerts | `.form-error`, `.result-banner.error`, `.notice-card`, `.authority-banner`, `.speaker-boundary-banner`, `.rights-banner`, `.transient-media-notice`, capacity notes and toast. |
| Motion/accessibility | Focus-visible ring on buttons/nav/icons; reduced-motion media query; 44–54 px common touch targets; ARIA live regions for app and toast. |

### 3.2 Page-specific one-off styles

- Workbench: `hold-card`, attention cards, quick cards, customer snapshot.
- Case: URL/paste combo, progress timeline, media review shell, review rows, full breakdown, sticky review/action containers.
- Customer/Speaker: fact cards, three-choice rows, edit panels, authority/boundary banners, overview cards, creation readiness card.
- Create/Delivery: profile choices, capacity state cards, request metadata, source handoff, four/three-step delivery progress, script/source/review cards.
- Content Operations: overview accent cards, state/count/record pills, bordered delivery list, collapsible authority detail.

### 3.3 Repetition and drift present in current CSS

- `.create-authority-card` is declared in two locations; one establishes shared width and one adds margin.
- `.operations-profile-badge` has two complete definitions; the later V1.1 definition changes minimum size and alignment.
- Content Operations retains an earlier V1 style block and a later “V1.1 — Visual Polish” block for the same component family.
- `.content-operations-page` first sets padding, then later overrides width and padding.
- `.profile-choice` and `.delivery-step` use `var(--surface)`, but `--surface` is not declared in `:root`; the declaration therefore has no resolved background value unless supplied elsewhere at runtime.
- Warning/explanation containers repeat similar amber or mint border/background structures under separate classes: `authority-banner`, `rights-banner`, `transient-media-notice`, `speaker-boundary-banner`, `capacity-authority-note`, `boundary-note`.
- Status semantics are represented by several parallel families: `.pill`, delivery flags, capacity state classes, operations state/count/record pills, and status kickers.
- Inputs share visual intent but are defined in global field rules and again for News/revision-specific controls.
- Content Operations uses a 1180 px page maximum while the global page maximum is 1120 px.

## 4. Card Density Map

Counts describe one rendered base state; `N` means the count grows with business data. A “border container” is a visually boxed element that is not the global `.card` primitive.

| Surface | Base cards | Nested cards / card-like children | Other border containers | Banners / notices | Current density fact |
|---|---:|---:|---:|---:|---|
| Login / Change Password | 1 | 0 | 2–3 input fields | 0–1 form error | One centered card. |
| Workbench, selected customer | 1 operational + 4 attention + 3 quick + 1 customer = 9 | 0 | Metrics inside customer card | Operational card carries banner-like styling | Highest base card count before any data list. |
| Workbench, empty | 1 empty + 4 attention + 3 quick = 8 | 0 | 0 | Empty card | Empty state remains surrounded by seven action/attention cards. |
| Case Library | N case cards | 0 | Filter chip row | 0 | Card count scales directly with library size; no pagination surface is visible. |
| Add Case | 2 | Task/result card can appear inside the URL panel form | Input combo; result banner; sticky action box | Rights notice card; optional error banner | Card inside card occurs when task progress is rendered in `#case-result` inside `.url-panel`. |
| Case Review | 4 fixed cards (media, 3 review sections) + full-breakdown card + decision card = 6 | N shot blocks inside breakdown; approved message inside decision | Media player frame | Rights banner + optional transient-media notice | Multiple boxed layers appear before and inside expanded breakdown. |
| Customer List | N customer cards | 0 | Metric band inside each card | 0 | Each card contains a bordered top/bottom metric band and an action row. |
| New Customer / New Speaker | 2 | Progress card can appear inside form result host | 3–5 fields | Explanatory notice card | Form card plus notice; dynamic progress adds a card inside form flow. |
| Customer Fact Review | N known/review fact cards + optional summary card | Edit panel and source disclosure inside each review card | Three-choice control per review fact | Optional authority/needs notice | Repeated card → evidence → decision → optional edit nesting. |
| Customer Persona Review | N fact cards | 0 | Sticky action container | 1 authority banner | Long vertical confirmed-fact list plus second-gate banner. |
| Approved Customer | 2 overview + N speaker + N fact + optional readiness = 2+N | Speaker mini-authority box inside each speaker card | Readiness action group | 1 rights banner | Several card families appear in one continuous detail page. |
| Speaker Review | N fact cards + 2 overview when approved | Source disclosure and edit panel inside facts | Sticky action container | Boundary or authority banner; rights banner when approved | Mirrors customer review density with an extra permission boundary. |
| Create before capacity | 1 form + 1 authority notice card | Two profile-choice bordered blocks in form | 4 controls | 1 notice card | Form card contains mode cards; separate notice follows. |
| Capacity result | 1 result card in addition to entry/notice | 3 metric boxes + gap + authority note inside result | Multiple inset containers | Authority and rights notes | Container-inside-container is explicit in the result composition. |
| Generation Request | 1 request card + delivery cards | Metadata rows, handoff box, stop-boundary box inside request | 3+ inset containers | Handoff/boundary notes | Request state is represented by several bordered layers within one card. |
| Mix Human Review | 1 outer delivery state + N script cards | Authority disclosure, flags, decision controls, revision editor inside each script card | Stepper + action row | Per-script flags/notices | Most densely nested repeated surface: outer state → script card → metadata/flags/decision/editor. |
| News Review | 1 outer delivery state + N title/source cards | Fact/authority boxes and decision/editor inside each card | Three-step progress | Capacity/semantic notes | Similar repeated nesting to Mix, with source and title layers. |
| Task List | N task progress cards plus N attached link rows | 0 | Progress track and step list | Failure next-action box when applicable | Each task visually combines two bordered blocks into one list item. |
| Content Operations | 4 overview + N work cards + delivery list | Delivery rows inside one bordered list rather than cards | Empty strips, badges, authority disclosure | Collapsible authority details | Mixes card grid, strips, individual cards, and a table-like list. |
| Global load error | 1 notice card | 0 | 0 | Page heading also carries raw error summary | Compact but duplicates failure explanation between heading and notice. |

Observed hierarchy patterns:

- Container inside container: capacity result metrics/gap/authority note; request metadata/handoff/boundary; delivery state/script cards; fact card/edit panel/source disclosure.
- Card inside card: Add Case result progress within the URL panel; delivery cards within the create workflow host.
- Notice inside card: transient-media notice within media metadata; capacity authority note inside capacity result; authority disclosure inside review cards.

## 5. Primary Action Audit

| Surface ID | Primary count in main state | Current primary action(s) | Audit flag |
|---|---:|---|---|
| S01 | 1 | 登录 | One primary. |
| S02 | 1 | Save password | One primary. |
| S03 | 0 | None; three equal quick-start cards | `PRIMARY ACTION NOT SINGULAR`: dashboard is entry-oriented rather than next-action-oriented. |
| S04 | 1 populated; 2 empty | + 添加案例 appears in heading and again inside empty state | `>1 PRIMARY` in empty state, both lead to the same route. |
| S05 | 1 contextual | Analyze/review/existing/reanalyze | One lifecycle-specific primary at a time. |
| S06 | 0 running; 1 terminal/duplicate | Go to review or existing case | Running state intentionally has no action. |
| S07 | 1 | Approve or recover approval | One primary; reanalyze and reject are secondary/quiet. |
| S08 | 1 populated; 2 empty | + 新建客户 appears in heading and empty state | `>1 PRIMARY` in empty state, same destination. |
| S09 | 1 | Analyze customer | One primary. |
| S10 | 0 running; 1 failed | Continue analysis | Running state has no action. |
| S11 | 1 page-level | Confirm information | Each fact also has three local decision buttons; these are repeated local actions, not page primaries. |
| S12 | 1 | Confirm and establish customer profile | One primary. |
| S13 | 1 when ready; 1 when no speaker; 0 in intermediate state | Start create or add speaker | Contextual one primary; content operations/add-another-speaker are secondary. |
| S14 | 1 empty; 0 populated | Add speaker | Populated list has only secondary row links/add control. |
| S15 | 1 | Analyze speaker | One primary. |
| S16 | 0 running; recovery-specific when failed | Recovery action | Running state has no action. |
| S17 | 1 per review phase; 0 approved | Confirm facts or approve persona | One primary in active review phases. |
| S18 | 1 | Check capacity | One primary. |
| S19 | 1 eligible; 0 blocked | Confirm request | One primary only after eligibility. |
| S20 | 1 per lifecycle stage, except Human Review | Generate plan/scripts, submit review, export, download | Human Review has per-item decisions plus approve-all and submit; the submit is the page primary. |
| S21 | 1 per lifecycle stage | Establish/generate/review/export/download | One page primary; repeated per-item decisions remain local. |
| S22 | 0 populated; 1 empty | Empty-state add case | `PRIMARY ACTION ABSENT` in populated state; surface acts as monitoring/history. |
| S23 | 0–1 | Type-specific recovery/next step or return | Primary depends on task projection; generic completed task only has secondary return. |
| S24 | 0–1 | Contextual entry | Empty-state behavior is not uniform across domains. |
| S25 | 1 global; variable inline | Retry | One global primary-like retry; inline operation errors vary. |
| S26 | 1 visually emphasized nav item | Create orb | It is navigation, not an in-surface action. |
| S27 | 1 visually emphasized nav item | Video Creation nav link | It is persistent navigation, not an in-surface action. |
| S28 | 1 | Reanalyze customer | One primary. |
| S29 | 1 | Start create | Downloads are row-level secondary actions. |
| S30 | 0 | None | Loading-only surface. |
| S31 | 1 in confirm/prompt | Browser confirmation | Native dialog temporarily owns the primary decision. |
| S32 | 1 when export complete | Download Excel | One primary within completed delivery. |

## 6. Responsive Audit

### 6.1 Breakpoint facts

- `<680 px`: base mobile layout, one-column collections, 18 px page inset, 68 px sticky topbar, fixed bottom navigation.
- `680–899 px`: two-column case/customer/speaker/script collections where defined; desktop sidebar is still absent.
- `900–1023 px`: case-review media and metadata can split into columns; sidebar is still absent.
- `≥1024 px`: fixed 252 px sidebar, no bottom navigation, 76 px topbar, larger page padding, three-column case/customer/speaker grids, desktop Add Case/customer-new splits.
- `≥1280 px`: case review gains sticky right decision aside; global page horizontal padding becomes 46 px.
- Additional component breakpoints: Content Operations at 1040/760 px, delivery at 430 px, capacity/request at 390 px.

### 6.2 Viewport matrix

| Viewport | Current layout behavior | Overflow | Oversized / empty space | Stacking / sticky | Density / readability |
|---|---|---|---|---|---|
| 390×844 | Observed: 18 px page inset; single-column main content; bottom nav fixed. Workbench had 9 cards and 1,844 px document height; Cases had 11 cards and 2,781 px height; Customer Detail had 28 cards and 5,637 px height; Tasks had 19 items and 4,754 px height. Capacity metrics would stack at the 390 px source breakpoint. | Observed: `/create` overflowed horizontally to 436 px; the other seven measured surfaces did not overflow. The two hidden profile radio inputs each measured 375 px wide and ended at x=436. | Case portrait iframe measured 345×613 px and occupied most of the initial viewport; long customer/task surfaces require extensive vertical scrolling. | Observed sticky topbar + fixed bottom nav. Add Case also showed a sticky action container above the nav. | 11–13 px metadata and multi-layer cards remain dense. The current Case Review iframe was a black rectangle in the capture even though its box scaled to the available width. |
| 430×932 | Observed: all eight surfaces were single-column where expected. Workbench/Cases/Case Review/Customer List/Customer Detail/Tasks measured 1,848/2,692/3,056/1,142/5,599/4,719 px document heights. Capacity metrics remain three columns by source rule because this viewport is above 390 px. | Observed: `/create` overflowed to 476 px; the other seven surfaces did not overflow. | Customer Detail retained 28 cards; Tasks retained 19 items. | Sticky topbar/action/bottom-nav behavior remained active. | This viewport sits above the capacity stacking breakpoint while still using the mobile shell. |
| 1440×900 | Observed: 252 px sidebar; global `.page` measured 1120 px and Create inner workflow/entry measured 1028 px. Three-column lists and the Case Review decision aside were active. | Observed: `/create` overflowed to 2,291 px. The two hidden profile radio inputs each measured 1,425 px wide and were positioned beyond their choice-card bounds. The other seven target surfaces did not overflow. | Workbench document height was 1,015 px; Cases 1,536 px; Case Review 2,043 px; Customer Detail 5,307 px; Tasks 4,682 px. | Topbar and Case Review aside were sticky; mutation actions were static. | Workbench showed 9 cards; Case Library 11; Case Review 6; Customer Detail 28; Tasks 19. |
| 1792×900 | Observed: sidebar remained 252 px and global `.page` remained centered at 1120 px, from x=454.5 to x=1574.5 on scrollable pages. | Observed: `/create` overflowed to 2,819 px; the other seven target surfaces did not overflow. | Global page width did not expand after the max-width cap; sparse list/form screens retained side whitespace. Customer Detail and Tasks remained 5,307 and 4,682 px tall. | Same desktop sticky behaviors as 1440 px. | Card grids did not add columns beyond their defined maxima. |

### 6.3 Responsive observations by component

- Add Case changes from two columns to one at 1024 px, so 900–1023 px still presents a single-column URL panel despite having no desktop sidebar.
- Case Review uses three layout regimes: one column below 900 px, media/meta split at 900 px, and page-level content/decision split only at 1280 px.
- The portrait player is capped at 360 px and `aspect-ratio: 9/16`; the landscape player is capped at 640 px and `52dvh`. Both use `object-fit: contain`.
- Customer/Speaker fact choice rows always use three columns; no mobile-specific rule changes that control row.
- Create capacity metrics stack only at `max-width: 390px`; at 430 px they remain three columns.
- Mix delivery progress changes to two columns at 430 px; News progress sets three columns and has no later max-430 override specific to `.news-delivery-progress`, so it remains three columns.
- Content Operations uses its own 1040/760 px response points, which do not align with the shell’s 1024/680 px points.
- Mobile pages reserve bottom-nav space globally. Additional sticky action containers independently position themselves above 70 px plus the safe area.
- The current `/create` route has page-level horizontal overflow at all four audited widths. Runtime inspection traced the overflowing boxes to the two hidden `.profile-choice input` radio controls: the global `.field input { width: 100% }` applies to them, while `.profile-choice input` makes them absolute and transparent without resetting width.
- The current Case Review remote iframe scaled with its portrait container (360×640 px at 1440 and 345×613 px at 390), with no page-level horizontal overflow. The captured iframe content itself appeared as a black surface at both widths; this audit did not establish whether the cause was remote player behavior, network policy, or embedding policy.

## 7. Screenshot Index

All captures used the local latest runtime, not the older public-edge deployment. Captures were viewport screenshots rather than full-page composites. No screenshot file was persisted because the pages contain real customer, case and task information; the images were used transiently for this audit only.

| Surface | Desktop 1440×900 | Mobile 390×844 | Observed state |
|---|---|---|---|
| Workbench | CAPTURED | CAPTURED | Selected customer; operational hold; four attention cards; three quick starts; 9 cards total. |
| Case Library | CAPTURED | CAPTURED | 11 approved case cards and three filter chips. |
| Add Case | CAPTURED | CAPTURED | Idle URL form; no URL entered and no task submitted. |
| Case Review | CAPTURED | CAPTURED | Existing approved case; remote portrait iframe; media-cleanup and rights notices; approved decision state. |
| Customer List | CAPTURED | CAPTURED | Three existing customers in mixed lifecycle states. |
| Customer Detail | CAPTURED | CAPTURED | Existing approved customer with one speaker, creation readiness and 28 total cards. |
| Create | CAPTURED | CAPTURED | Entry form before capacity check; no request or task created. Horizontal overflow visible at both sizes. |
| Tasks | CAPTURED | CAPTURED | 19 shared task items in mixed terminal states. |

Additional runtime measurements were collected for the same routes at 430×932 and 1792×900; those were metric checks rather than screenshot-set deliverables.

## 8. Current Known UX Debt

The items below are observations of the present implementation, not proposed solutions.

### Information and terminology

- Formal architecture terms are visible in routine operator flows: Authority, canonical, artifact, Attempt, companion, Intake, Profile, Generation Request, Source Planning Handoff, Content Ledger, Approved Projection, Historical Exposure, Presentation History, Central Claim and Request ID.
- Chinese business language and English architecture nouns are mixed within the same sentence in customer, speaker, create, review, recovery and task surfaces.
- Backend/API error wording is directly user-visible in page headings, form errors, result banners and toasts.
- Unmapped lifecycle statuses can be rendered as raw technical enums.
- Object-valued facts are rendered as JSON in review cards.
- Rights and human-gate boundaries are repeated in multiple surfaces and multiple visual container types.

### Navigation and action hierarchy

- Workbench has no singular page primary; three quick-start cards and four attention links compete as entry paths.
- Empty Case Library and empty Customer List render the same primary destination twice: once in the page heading and once in the empty-state card.
- Populated Task List has no page primary and behaves as a monitoring/history surface.
- Persistent navigation visually promotes Create on both desktop and mobile, independently of the current surface’s own primary action.
- Approved Customer can simultaneously show Start Create, Content Operations and Add Speaker actions, with one primary and multiple nearby secondary routes.

### Density and hierarchy

- Workbench selected-customer state has nine base cards before dynamic additions.
- Fact review, capacity, request, Mix review and News review contain multiple bordered layers inside cards.
- Case Review combines media card, rights banner, three summary cards, an expandable breakdown card and a decision card.
- Mix and News human review repeat dense per-item cards containing provenance, governance, decisions and optional editors.
- Add Case and onboarding forms can render a task progress card inside an already bordered form card.

### Visual system consistency

- Spacing values are not tokenized and are distributed across page-specific rules.
- Content Operations has a different page maximum width and parallel V1/V1.1 style definitions.
- Status badges, notices and warning containers have several domain-specific implementations with overlapping semantics.
- Two selectors reference an undefined `--surface` custom property.
- Input styling is repeated between global and delivery-specific controls.
- Customer and speaker review share visual patterns but retain separate component/rule families.

### Responsive behavior

- Mobile combines a sticky topbar, fixed bottom navigation and, on mutation screens, a second sticky action container.
- Customer/Speaker three-choice fact controls do not have a smaller-screen layout override.
- Capacity metrics change from three columns to one exactly at 390 px; 430 px retains three columns.
- News keeps a three-column progress strip on narrow screens while Mix changes to two columns at 430 px.
- Case Review has distinct 900 px and 1280 px transitions, creating an intermediate tablet/desktop state without the right decision aside.
- Very wide desktop viewports retain fixed maximum content widths, so sparse pages show substantial side whitespace.
- `/create` has observed horizontal scrolling at every audited width: 436 px document width at 390, 476 px at 430, 2,291 px at 1440, and 2,819 px at 1792. Other requested surfaces did not show page-level horizontal overflow in the same runs.
- Case Review’s portrait player container responds to the viewport, but the current remote iframe content rendered black in the local screenshots at 1440 and 390.
- Current real-data page lengths are high on Customer Detail (5,307 px desktop; 5,637 px mobile) and Tasks (4,682 px desktop; 4,754 px mobile).

### State coverage and auditability

- Several route URLs represent multiple materially different lifecycle surfaces; the visible page is determined by API state rather than route alone.
- Task Detail dispatches into domain-specific renderers, so the same route family has different layouts and action rules by task type.
- Empty, loading, failure, recovery and approved projections are implemented independently across case, customer, speaker, Mix and News flows.
- The audit visually captured the currently available real states. Lifecycle variants not active in local data—such as an awaiting-review case decision, empty collections, active Mix/News delivery, fact-review editing, and error/recovery variants—remain source-derived.

## Audit boundary confirmation

- HTML modified: no.
- CSS modified: no.
- JavaScript modified: no.
- API/backend modified: no.
- User-facing product copy modified: no.
- Business artifacts modified: no.
- Screenshot captures performed: 16 requested viewport captures (8 surfaces × 2 sizes), transient only.
- Screenshot assets persisted in repository: no; captures contain real local business data.
- Deliverable created: this audit document only.
