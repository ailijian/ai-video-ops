# CS-UAT-E1｜客户资料识别完整性与分类推荐根因报告

审计日期：2026-10-10。性质：Current Truth，只读根因审计，非修复交付或生产验收。

`SYNTHETIC_EXTRACTION_LIMITATION`

本次失败首先发生在**合成提取输出及其历史候选快照**：完整餐饮资料已保存，但该 Intake 只有客户名称候选，没有主营服务、顾客场景或具体业务事实候选。人工检查结束不能确认尚未生成的事实，因此 Business Readiness 正确继续阻塞。行业和人物类型也受合成提取器的明确能力限制影响，不能据此宣称真实 DeepSeek 分类失败。

另外确认了两类独立问题：重要限制没有进入现有结构化约束链；前端的完成提示、补资料原因和重复等待提示容易混淆“检查已保存”“资料充分”“档案已批准”。没有发现本客户存在两个重复 Speaker Draft，也没有发生自动批准。

## A. 实际环境与模型真实性

| 项目 | 实际观察 |
|---|---|
| 本机 | `LIJIAN` |
| 工作区 | `E:\cs-intake-v1`；原工作区 `E:\projects\ai-video-ops` 保留 |
| HEAD | `f10f3992433ab81df38ae90f9379ce1061a7afac`，实现仍为既有未提交差异 |
| 监听 | `127.0.0.1:18010`，PID `26304`，父 PID `24340`；未发现 8000 Console |
| 实际启动命令 | `python.exe -X utf8 internal-console\tests\browser_customer_speaker_intake_v1.py --workdir E:\cs3node --port 18010 --resume` |
| Python | `C:\Users\JIAN LI\AppData\Local\Programs\Python\Python312\python.exe` |
| 独立数据库 | `E:\cs3node\console.sqlite3` |
| canonical 数据根 | `E:\cs3node\ops-pipeline` |
| 正式 workers | Case、Customer、Speaker、background workers 均关闭；单个串行合成 driver 处理测试任务 |
| Customer Extraction | 向现有 analyzer 显式传入合成 `extractor`，输出 `model=synthetic-offline` |
| Speaker Discovery | 显式传入合成发现函数，包括本次 discovery-only retry |
| Speaker Analysis | driver 同样注入合成 personal extractor；本客户人物尚未开始此阶段 |
| 真实 DeepSeek | 本次相关任务没有调用正式 remote extractor；实际 egress/discovery 文件均标记 `synthetic-offline`，usage 为空 |

启动设置和注入路线见 [验收驱动](E:/cs-intake-v1/internal-console/tests/browser_customer_speaker_intake_v1.py:135)、[resume 设置](E:/cs-intake-v1/internal-console/tests/browser_customer_speaker_intake_v1.py:366)。`browser_manifest.json` 明确记录 `fixture_only=true` 和 `synthetic outputs only; no external calls`。Customer Analysis、Fact Review、Intake、Persona builder、Speaker Discovery、Privacy 的运行脚本与当前工作区逐文件 SHA 相同；不是旧 8000 后端配新静态文件的情况。

当前合成驱动包含两种有限路径：编号表单逐字复制；少量预置洗护样本关键词匹配。它没有通用语义理解能力。编号表单人物姓名、身份和个人材料来自本次输入，已核对引用均在安全投影中；没有把本次餐饮资料替换为另一客户的整份固定输出。历史业务候选只有名称，不是完整模型提取的结果。

初次合成提取的原始返回 JSON 未独立留存，本轮不声称逐项还原了当时响应。可直接证明的是已保存 AI 业务候选为 0、egress 为 synthetic-offline，且当前合成分支重演与旧候选不同。关于旧洗护限定驱动的历史诊断，保留在既有 Implementation Report 的 2026-10-10 修复记录中；本报告不以当前源码冒充当时完整驱动快照。

本轮未检查供应商账单或进行历史网络抓包；上述“没有真实模型调用”结论限定为本次验收任务的注入路径和保存证据，不推断其他机器或任务。

## B. 完整来源与事实链

审计对象：Business `customer_d6a5612fcc65442baefd9910ef11b3c0`，`intake_0001`。以下仅列安全摘要，不复制真实品牌名、姓名、生日、个人经历或原文全文进报告及测试库。

```text
Raw Request / Raw Intake：完整资料 3573 字符
    → Privacy Projection：3573 字符，与原文相同
    → Fact Candidates：1 项，只有 public_display_name
    → Human Fact Review：completed_persona_blocked，decisions=[]
    → Reviewed Known Candidates：仍只有 public_display_name
    → Business Readiness：3 个能力组缺口，无 Business Persona 或 Approval
```

| 层 | 文件与可核对事实 |
|---|---|
| Raw | `customer_onboarding_request_v1.json` 的 materials 与 `customer_intake_v1.json` 的资料 answer 相同；没有截断 |
| Projection | `customer_intake_privacy_projection_v1.json` 引用的 raw SHA 匹配；重要业务、限制、创始人关系均仍在投影内；annotations=0 |
| Candidates | `persona_fact_candidates_v1.json` 仅 `FC-intake_0001-001` → `public_display_name`，来源为 operator identity input，状态 `known_candidate`，并非 AI 业务提取 |
| Review | `customer_fact_review_v1.json` 于 `2026-10-10T03:24:29.211757+00:00` 保存；candidate SHA 与原文件匹配；0 项 AI 决策、没有行业人工选择 |
| Reviewed | `reviewed_persona_fact_candidates_v1.json` 没有新增业务字段，名称仍沿用显式录入依据；没有虚构主营或场景 KNOWN |
| Readiness | 保存的 review blockers 为 `business_identity`、`customer_use_context`、`production_bearing_facts`；纯内存用正式 builder 重算完全相同 |
| Persona / Approval | `business_persona_created=false`、`persona_approved=false`，current Approved Business 不存在；本客户人物也没有 Persona/Receipt |

`persona_onboarding_readiness_v1.json` 是分析时的派生快照，时间早于后续 Fact Review；客户缺口页面实际消费的是 review 的 `business_persona_blockers` 投影。本次两者结论相符，不能把分析时快照当作已更新的 Approval 或 Readiness 真相。

### 四个能力组的逐层覆盖矩阵

| 能力组 | 1. 原文明确证据 | 2. 是否提取候选 | 3. Fact Type 映射 | 4. 人工确认 | 5. Readiness 消费 | 6. 最终缺口原因 |
|---|---|---|---|---|---|---|
| `business_identity` | 有：客户名称、地方菜、宴请及聚会服务 | 只有名称；主营候选缺失 | 名称正确映射 `public_display_name`；应有 `primary_service → primary_products_or_services`，本次没有该候选 | 名称是既有显式录入依据；没有主营候选可审核 | 消费了名称，没有 offering evidence | 需要“身份＋具体产品/服务”，名称单独不能满足。失败在合成提取／遗留候选层，不是客户没写服务 |
| `customer_use_context` | 有：商务宴请、家庭聚会、节日聚餐、客人需求 | 无 | 正式映射 `core_audience`、`customer_use_case → customer_use_cases`、`customer_pain → customer_pains` 可用；本次无输入候选 | 没有对应人工决定 | Known 集为空，无法消费 | 提取遗漏，不是审核后的场景被 Readiness 丢弃 |
| `production_bearing_facts` | 有：食材与技法、菜单/主题安排、具体用餐组织和业务差异 | 无 | `differentiator → differentiators`、`service_process → process_facts` 等已有合法映射；本次没有候选 | 未审核这些事实 | 没有具体 Known evidence | 提取遗漏；没有证据支持“完整事实已确认但 Gate 错误拒绝”的判断 |
| `critical_constraints` | 有：品牌/获奖主体待核实、公开权限、禁止夸大、服务条件限制 | 无结构化限制候选；intake open_questions/conflicts 和 derived constraints 都为 0 | 当前 Customer 模型 topic 白名单没有 critical/forbidden 边界入口；Gate 消费结构化 critical questions/conflicts，不会扫描自由文本 | 没有对应限制审核记录 | 当前接收空 constraints，`satisfied=true` | **未被列为缺口，但不是覆盖通过**。这是原文限制未结构化的合同／来源投影缺口；不能据此认定已审核或没有风险 |

Business Gate 的真实规则见 [能力判断](E:/cs-intake-v1/ops-pipeline/scripts/build_persona_v1.py:213)。它只消费有效 Known 事实，不按原文篇幅或字段完成百分比判断；行业不是首次 Business Readiness 的必需字段。具体营销赞誉不足以替代可用于创作的实际事实。

### 为什么更新 UI／合成驱动后旧客户仍缺事实

对现有安全投影只执行当前 `structured_form_outputs()` 的纯内存重演，得到三个 topic：`primary_service`、`core_audience`、`differentiator`。这说明当前规则表单分支能复制部分回答，但**旧业务候选文件没有重新生成**。

[原 analyzer](E:/cs-intake-v1/ops-pipeline/scripts/customer_onboarding_analysis_v1.py:992) 检测到同 Intake 的已有候选后校验来源并复用，不再次调用提取器。这是既有幂等和不可变边界，不应删除文件或绕过恢复逻辑“修好页面”。上次人物恢复只重试 Discovery，明确不重跑 Customer Extraction，所以不能补齐旧业务事实。

## C. 行业与出镜人类型推荐

### 行业

正式选项为：**餐饮、本地生活、零售、烘焙甜品、美容、教培、服装、饰品、通用行业**。前端复用 [行业字典](E:/cs-intake-v1/internal-console/static/assets/case-industry.mjs:1)；后端 [Customer topic 合同](E:/cs-intake-v1/ops-pipeline/scripts/customer_onboarding_analysis_v1.py:43) 使用相同选项。

正式模型合同允许 `{topic: "industry", value: "餐饮", evidence_quote: "来源原文"}`；值须在字典内、quote 须来自安全资料，生成的仍是 `requires_review` 候选。前端按 candidate field/value 呈现行业审核项，人工确认独立留痕。

本次没有任何 industry 候选。当前编号表单合成函数也根本不输出 industry；预置洗护路径只会推荐其预设行业，与餐饮表单无关。人工提交没有 industry_review，因此当前“待确认”不是已存在餐饮建议被前端丢弃。

**相邻投影风险，尚非本次根因：** `_customer_projection` 的摘要行业取 Persona 或 intake industry，不取已审核候选。在资料仍不足、尚未生成 Persona 时，即使以后人工确认了行业，摘要仍可能显示待确认。这是源码可见的覆盖缺口，后续应以带来源的审核分类标签展示，不能把标签升级为 Approved Customer Truth。

### 出镜人类型

正式枚举为 `owner_founder / frontline_expert / brand / generic`，Discovery 还允许未推荐 `null`。`owner_founder` 在现有界面显示“店主 / 创始人”，可承接本次希望的“老板/创始人”语义。

本次重试人物候选有明确创始人关系，引用均可追溯，但 [合成表单函数](E:/cs-intake-v1/internal-console/tests/browser_customer_speaker_intake_v1.py:83) **固定写 `speaker_type_hint="generic"`**，不做关系分类。validator 保留有效 hint，不从 public_role 再推断。前端忠实选择 generic，随后人工保存的 discovery decision 和 Speaker Request 也都是 generic。

正式 [Speaker Prompt](E:/cs-intake-v1/ops-pipeline/speaker_prompt.md:57) 允许 `owner_founder`，canonical validator 可接收且保留；本轮没有调用它，因此没有真实模型识别创始人失败的证据。明确身份也不能自动赋予出镜意愿、第一人称权限或 Persona Approval。

**相邻 UI 风险：** [候选表单](E:/cs-intake-v1/internal-console/static/assets/customer-views.js:139) 使用 `candidate.speaker_type_hint || "generic"`：未推荐会被呈现为“其他出镜人”；恢复时也没有优先读取 `confirmation.speaker_type`。应区分未推荐与确实 generic，并保留已有人工类型选择。本次已有保存值确实为 generic，不能把这个潜在恢复问题误报为本次人选遭覆盖。

### 重要限制与隐私的正式合同缺口

- Customer 模型白名单只覆盖十种业务 topic，没有可靠表达“禁止使用的宣传”“待核实主体”“关键未知”的结构化输出。纯内存验证 `critical_constraint` topic 会被忽略。需要明确接入已有约束和 Human Review 合同；不是增加几个标题关键词即可解决。
- 本次 Customer Privacy Projection 完整保留了出生年月字段；当前检测器没有此类标签策略。这里没有真实外发，但**投影验证 passed 不能证明所有个人资料均已最小化**。真实模型验收前须明确与业务提取无关的个人字段如何剔除或授权。本报告和 Golden 不复制该字段。已保存的 Speaker 个人材料不含该字段，不能替代 Customer egress 检查。
- 现有 Speaker Prompt 示例包含具名人物及企业经营年限的个人材料引用，存在示例污染和企业经历转个人经历的风险。它未参与本次合成提取，不是本次 generic 的原因。后续应改为完全虚构示例，并验证人名、身份、经历均来自当前来源。

## D. 页面状态与重复提示

| 页面说法 | 当前真实状态与含义 | 审计结论 |
|---|---|---|
| “确认客户信息” | `fact_review_required` 的逐项候选审核页面 | 审核候选，不等于批准 Business Persona，也不等于整份原文已被提取 |
| “客户信息已确认” | Task completed 可表示 fact review completed；独立 Approved Persona 才有 `approved=true` | 后台保持分离；相同中文文案用于不同层级会误导 |
| “资料待补充” | review=`completed_persona_blocked` → Console=`needs_more_info` | 本次真实缺的是已确认事实集合，不是原始资料。页面没有说明提取遗漏，会让用户重复提交已有资料 |
| “出镜人待客户档案确认” | Speaker=`pending_customer_profile`，Business 无 Approved revision | 姓名/身份/个人材料已经保存，但独立分析及批准仍等待客户档案；合法 Gate，无重复批准要求 |

实际只有一条人物记录：`speaker_3e30c5f321f5f8`。Discovery confirmation=`completed`，outcome=`draft_created`、retry_required=false，候选 projection `confirmed=true`。Speaker Request 来源为 `customer_intake_speaker_discovery`，已有身份人工确认及来源 lineage，个人材料 944 字符；没有 Speaker Analysis Task、Persona 或 Approval Receipt。

重复提示来自同一状态的多处文案：客户摘要的“已保存，待客户档案确认”、人物行状态徽标、人物详情的徽标/副标题/正文标题。客户页面每条 `speakers` 记录只生成一个卡片，本次列表长度=唯一 Speaker ID 数=1。不能将重复提示说成重复创建人物。

另有确定的完成反馈问题：[客户审核提交](E:/cs-intake-v1/internal-console/static/assets/customer-views.js:539) 先根据 blocked 显示“已保存，仍需补充”，随后只要成功保存人物又显示“客户信息已确认，出镜人资料也已保存”。本次这两个条件同时成立。第二条反馈弱化前一条阻塞说明，但没有改变 canonical Approval。

缺口 projection 当前只提供能力组及固定补资料问句；除结构化 critical conflict 外，不区分“原文未提供”“提取遗漏”“待人工确认”“已确认事实冲突”。本次因此错误地把提取遗漏包装为需要客户补原文。创作入口仍要求 Approved Business 和至少一个适配的 Approved Speaker，本次为 false；后续还须内容机会、可行性及媒体权利，不能用资料完整代替这些 Gate。

## E. Golden Test Input 与只读合同重演

已制作 [Golden Input](E:/customer-speaker-uat-e1-20261010/golden-input.txt)，2516 字符。全部品牌、人物、活动、经历和业务事实重新虚构，保留 8 项品牌业务＋5 项人物资料＋4 项选填问题结构，以及密集的服务、顾客场景、流程、限制和个人经历；不包含真实生日、籍贯、原个人经历或真实荣誉。

| Golden 验收点 | 应有候选／边界 |
|---|---|
| 主营服务 | 堂食、商务聚餐、家庭菜单、主题晚餐 → `primary_products_or_services` |
| 顾客及场景 | 周边家庭/商圈聚餐与具体需求 → `core_audience / customer_use_cases` |
| 具体业务 | 预约人数/预算/忌口确认、试菜记录、菜单顺序 → `process_facts` 等具体字段 |
| 行业 | 有餐饮直接来源支持，候选 `industry=餐饮`，仍需人工确认 |
| 创始人 | 明确关系引用支持 `speaker_type_hint=owner_founder`，仍需人工身份及个人事实审核 |
| 重要限制 | 授权、禁止夸大、主体待核实须单独识别及审核；不能因普通字段齐全而忽略 |
| 未核实荣誉 | 不得成为 Known/Approved 荣誉；应保留未知、剔除或记录明确禁用边界 |
| 首次 Business | 完成足够具体事实的人审并正确处理关键限制后，允许形成待批准 Persona；绝不自动 Approval |

实际执行的 [纯内存重演](E:/customer-speaker-uat-e1-20261010/golden-contract.py) 使用正式候选 builder、人工决策函数、Persona input builder、Readiness 和人物 validator；期望提取输出**人为编写**，人审决定**明确为模拟**。没有模型调用、Task/数据库/Authority 写入、Persona 构建落盘或 Approval。

观察结果见 [Golden 合同结果](E:/customer-speaker-uat-e1-20261010/golden-contract-results.json)：

- 人审前，AI 候选 `requires_review` 不满足三个 Business 能力组；模拟逐项确认后组级 blockers 为空，证明已有映射与 Gate 能接收足够已审核事实。
- industry 正常接收餐饮；人物 validator 保留 owner_founder，无 Persona/Approval 输出。
- 模拟编辑差异点去掉未核实荣誉后，它不进入 Known facts；显式未解决 critical constraint 仍阻塞，未降低 Gate。
- 当前合成 parser 对同 Golden 只输出三个业务 topic 和 generic 人物类型，不推荐行业，也未识别结构化限制。

此重演**没有证明正式模型提取质量、限制自动识别闭环或真实人工批准**。完整 Golden 正向验收还缺限制发现与独立处理的实际链路。不能把手写期望输出、内存组级 readiness 通过或上轮 851 项离线回归当成真实 UAT 模型 PASS。

## F. 根因分类及精确最小修复建议

以下均为建议，本轮未实施。

| 优先级 | 问题分类 | 最小建议与保留边界 |
|---|---|---|
| P0（真实模型验证前） | 限制提取／合同覆盖 | 明确 Customer 输出中限制、待核实宣传及主体冲突的候选来源，并接入现有 canonical 约束、人审与补充机制。缺少约束不得作为覆盖成功；不得改 Gate 为只看业务三字段。涉及被冻结事实/约束合同的变化须先单独确认映射方案 |
| P0（真实外发前） | 隐私投影覆盖 | 确定出生年月等非必要个人字段的投影策略；对实际 rendered prompt 做 minimization/egress 验证，再授权真实调用。本次不外发或修改原文 |
| P1 | 合成夹具能力 | 使用完全虚构 Golden 及明确的模拟输出覆盖行业、角色和限制；任意真实输入不受支持时明确失败或标记不可评价，不能返回“完整 AI 解析成功”。不在正式 analyzer 中新增第二套关键词流水线 |
| P1 | 旧候选恢复 | 提供“使用已保存资料补齐识别”的显式动作，复用现有增量 Intake/Human Review，引用原 source ID/SHA，仅补未覆盖字段。保留旧 Review、Known facts、Persona/Receipt。当前同原文 reanalysis 返回 same_input，analyzer 复用旧 candidates，单纯重试不能修复；不得删除候选或伪造新资料 |
| P1 | 来源 lineage／恢复入口 | `gap_supplement` 已支持 source_lineage 和 reviewed context，可作为恢复底座；Console 入口须明确原文再提取来源，不能把旧原文装成新客户事实。若现有请求无法表达，应做最小可审查合同扩展，不能静默重写初次 Intake |
| P1 | 分类字段 | 保留正式行业字典与 evidence_quote；人物类型依据明确关系生成非权威 hint，统一处理“创始人”等通用角色，禁止品牌/人名特例。AI 建议和人工最终值独立留痕 |
| P1 | 完成反馈／缺口原因 | 合并一次提交反馈，根据 Fact Review/Readiness/Speaker 保存结果表达“已保存检查结果，业务识别仍未补齐”。缺口增加来源不足、提取遗漏、人审待完成和冲突原因，不能一概要求用户重新填资料 |
| P2 | 重复提示／默认类型 | 待客户批准状态保留一处主要说明；人物卡片保留简短状态，不重复强调“待确认”。恢复类型先取人选最终选择，再取系统 hint；无建议显示待判断，不冒充 generic 推荐 |
| P2 | 已确认行业摘要 | 资料不足且 Persona 尚未生成时，显示已有人工分类与来源，但不作为 Approved Business Truth |
| P1（真实模型验收前） | 示例污染风险 | 以虚构、独立归属示例替换 Speaker Prompt 中具名/企业年限引用；禁止将企业、他人或示例事实迁移为本人经历 |

最小修复顺序：先使验收模式和数据来源诚实可辨识，再补齐保存来源的合法恢复和限制覆盖，最后整理状态文案与分类呈现。**不需要重做 Case Pipeline、放宽 Readiness、另建 Authority 或自动批准任何人。**

## G. 建议增加的回归与无需重新提交内容

1. 完整虚构餐饮 Golden：主营、场景、具体事实、行业、创始人类型和来源逐项覆盖；禁止套用预置其他客户输出。
2. 原文完整但旧 AI candidates 空：明确报告提取遗漏；既有候选重试仍幂等；显式增量恢复保留旧文件、审核指纹和来源 SHA，不循环生成新 Intake。
3. `primary_service / core_audience / customer_use_case / service_process / differentiator` 的真实合同映射；未审核不可用于 Readiness，完成人审后组级能力通过，Approval 仍独立。
4. 待核实荣誉、混用品牌、禁止公开及夸大限制：不得 Known/Approved；关键未决事项必须阻塞，明确排除或处理后才继续。不得一项无关补充审核清除全部关键限制。
5. 人物 public_role 创始人：保留非权威 owner_founder 建议；null 与 generic 区分；人工改类型后的失败恢复/重开不丢值；不因身份自动确认出镜或第一人称能力。
6. Customer blocked＋人物保存成功：仅一条准确反馈；页面区分检查完成、资料充分、待批准和已批准。共享读取/刷新仍使用同一 Speaker ID，已保存候选不再次显示待选择。
7. 人工行业已确认但 Business blocked：摘要正确显示人工标签及来源，不授予 Persona、创作资格或媒体权利。
8. Privacy 和个人归属：虚构敏感字段从不必要远端输入剔除；企业年限和其他人物经历不迁移给人物；提示词示例不污染当前候选。

**不需要客户重新提交：**主营服务、顾客/使用场景、菜单与技法等具体业务、限制原文以及已经保存的创始人个人材料。本次 request/raw intake 完整，Speaker Draft 及 source lineage 也已保存。下一步应复用这些来源，识别遗漏后再由运营逐项检查；不要要求客户重新写一份资料。

仍需人工处理的是：来源已写明但尚未核实的获奖主体、品牌关系、授权或其他不确定事项。恢复提取不能把“尚待核实”变成事实；只有确实无法从原资料确定的问题才要求补充真实证据。

## H. 只读证据与验证限制

- [安全链路结果](E:/customer-speaker-uat-e1-20261010/safe-audit-results.json)、[审计脚本](E:/customer-speaker-uat-e1-20261010/audit.py)、[审计前 canonical SHA](E:/customer-speaker-uat-e1-20261010/data-hashes-before.json)、[最终保护校验](E:/customer-speaker-uat-e1-20261010/final-preservation-results.json)。结果只保留长度、ID、状态、字段、SHA 和安全摘要，不保存真实全文副本。
- 只读 SQLite `mode=ro` 核查两条相关 Customer Task 均由 `isolated-synthetic-extraction` 执行并 completed；无对应 Speaker Analysis Task。事实、人物保存和批准状态以 canonical 文件/解析器为准。
- 首次纯只读重演窗口前后，两数据库及 205 个隔离 canonical JSON SHA 相同。最终收口再次核对：205 个 canonical JSON 及原工作区数据库仍不变；原数据库为 `ffe5c72fbc16ca8151589875fff815584f1e434df22977b40c28221aa0ca54ea`。
- 服务持续运行期间，隔离数据库的整体 SHA 后来发生变化；两条相关任务的完整抽查字段仍相同，未出现人物分析或新 canonical 数据。观察到活动会话的 last_seen 时间更新，符合 [登录服务](E:/cs-intake-v1/internal-console/app/auth_service.py:204) 每 300 秒允许更新会话时间的行为。本轮没有前后全库行快照，不能断言会话是文件变化的唯一原因；审计脚本仅使用 `mode=ro` 查询，未尝试恢复、锁定或改写运行库。不能宣称整个验收期间隔离运行数据库字节不变。
- 本轮产品代码、Schema 和已有 UAT 数据未修改；只新增本报告及工作区外的安全审计/Golden 证据。无真实模型、无提交业务请求、无人工事实/Persona/Compatibility 自动批准、无 commit/push/部署。
- 没有重跑完整回归或进行真实模型/4090验收。本报告不是生产通过证明；Golden 重演只界定合同可用性和合成驱动覆盖限制。

`CS_UAT_EXTRACTION_ROOT_CAUSE_READY`
