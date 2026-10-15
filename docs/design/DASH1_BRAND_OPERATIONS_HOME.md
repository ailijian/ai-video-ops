# DASH-1 Brand Operations Home — read contract

Scope: Founder instruction DASH-1, 2026-10-15. This documents a Console
read-only composition, not new Authority or independent product approval.
Navigation stays 工作台 / 案例 / 客户 / 任务. Existing Gate owners are unchanged.

## DASH-0 data audit

| Home information | Machine source | Counting rule | Permission scope | Implementable |
|---|---|---|---|---|
| 客户总数 | `_identity_index`; existing Business/Persona/intake contract | Unique Business ID, excluding revisions and Speaker Personas | Existing authenticated internal Business collaboration | YES |
| 待处理事项 | `_customer_projection`, `_speaker_projection`, `creation_record_index`/effective lifecycle, Task DB and Case classification | Stable object/action ID; current stage, no duplicate failed execution or matching running operation | Existing Customer collaboration; exact submission ownership or explicit current Case reviewer | YES; null when incomplete |
| 进行中任务 | Formal Task DB | All accessible queued/running Task IDs; no last-10/50 limit; failed/completed/cancelled excluded | Case scope in SQL before row conversion, then trusted submission validation | YES |
| 本月完成作品 | Mix/News/Novel export/closure and Ledger audited | No common work/video completion definition across semantic content, repurpose presentations and script export; final video delivery unimplemented | No expansion | NO; hidden, never replaced with zero/request/download count |
| 待核对资料 (fourth KPI) | Same action collection | Subset of 待处理事项: Business Fact Review + Speaker Fact Review + accessible Case classification | Same scope; excludes Case Approval | YES; null when its sources incomplete |
| 最近工作 | Request and Intake `created_at`, Task `updated_at` | Real UTC times normalized, descending stable ties; execution updates merge into their Business/Speaker/Request/Case context | Authorized collaboration, explicitly not personal activity | YES |

No migrations, statistics table, activity database, tenant system, grant, model or
Authority writer. CASE-CL0 capability is read again each request. Revocation
removes reviewer actions on the next read. Ordinary submitters waiting for
platform review have no Case-review action. Orphan Task ownership is not guessed.

## Action matrix

| Kind / identity | Source state and entry | Priority |
|---|---|---|
| Task recovery / latest object operation | Current failed operation with a legal recovery route → exact Task; superseded failures/finished stages excluded | 10 |
| Content review / namespace + Request ID | Existing Request Human Review stage → original Business/Request/profile/mode URL | 20 |
| Case review / Case ID | Current candidate awaiting Human review with confirmed classification; designated reviewer only → original Case detail | 20 |
| Business Fact Review / Business + Intake | `fact_review_required` → exact Customer detail | 30 |
| Case classification / Case ID | Unconfirmed accessible private submission or explicit reviewer → original classification route | 30 |
| Business information / Business + Intake | `needs_more_info` → exact Customer detail, constraints remain enforced | 35 |
| Business/Speaker Approval or revalidation | Formal pending Persona/revalidation state → exact Business/Speaker; waiting-for-Business Speaker excluded | 40 |
| Draft / Request continuation | Real draft or nonterminal Request → original route; corresponding queued/running operation suppresses action | 50 |

One Request stage and its failed Task count once. Independent Business/Speaker
actions may count separately. Rejected Case is not parsing failure. Case Approval
is not sharing, compatibility or media production permission. Clicks only
navigate; target Gate owners revalidate current state and rights. No automatic
retry, Request creation, approval or model call occurs on homepage read.

The overview recent list omits contexts already in the five visible priority
actions, then fills from the remaining recent contexts. The full recent section
retains all contexts in time order; execution history stays in the original Task
records. This is presentation deduplication, not deletion or a lifecycle change.
Case submission names use the original source caption through the existing
metadata owner only after checking the exact private Case/Attempt permission.
Missing/invalid titles show 未命名的视频投稿; exact Case/Task IDs remain in the
projection and row trace attributes/tooltips, not as the primary business name.

Times retain provenance in tooltips: submission, Request creation or Task update. Missing
times stay null; no filesystem mtime or fabricated now. Display uses Asia/Shanghai
(UTC+08 for this runtime) with year. Month metadata is [month start, next month
start), not a completed-works statistic. Unknown completion stays unavailable.

## API, failures and performance

Additive `GET /api/dashboard`, schema `brand-operations-home-v1.0`:
`section=overview|attention|materials|running|recent`, `page>=1`, `page_size=1..50`
(default 20). Overview contains five actions and five recent records; dedicated
sections paginate the same scope, count and stable ordering. Callers cannot
select another Principal. Existing Session/initial-password checks and
`private, no-store` apply. Old `/api/workbench` remains compatible, including
current-customer and Operational Hold reads.

Responses contain bounded safe display fields and local route contexts, not Raw
Evidence, transcripts, media/source paths, operator phones, Task payloads or full
Persona facts. `partial`, source `available` and list `complete` distinguish a
partial read from empty. Affected totals are null; other sections remain usable.
Source failures expose only category names, never private error details.

One request-local identity index, Request index and scoped Task SQL read serve all
four metrics/lists. No per-KPI scan, media decode, model, creation preview or
production-planning trigger. Existing owners may reread small lineage artifacts
for validation; this does not claim one physical read per file. No persisted
index or permission cache is added. Scale measurements belong to delivery evidence.

## UI ownership and validation

`dashboard-view.mjs` owns home markup/time formatting; `dashboard.css` only
`.dash-*` presentation. Shared tokens/fonts/buttons/navigation remain in
`styles.css`; customer/Case lists remain in `brand-lists.css`. Retired workbench
overview/recent rules are removed. One aggregate read replaces four homepage
list/preview requests. Desktop: four cards plus work/shortcut columns. Mobile:
two KPI columns, attention → shortcuts → recent. Empty, partial and loading
states never flash fabricated zero. No framework/font/chart/notification added.

`browser_dashboard_v1.py` creates new SQLite, Canonical roots, cookies and ports.
Only acquisition/extraction boundaries use synthetic fixtures. Empty and broken
source scenarios use separate new nodes. NAV/CASE/E2 runtime DBs are never reused.
Evidence, test counts, protection and remaining boundaries are in the delivery
report; this contract itself is not a claim of production or visual acceptance.
