# CS-UAT-E2｜Extraction & UX Closure Report

日期：2026-10-10。工作区：`E:\cs-intake-v1`。本报告是 **E2-A 合同边界诊断与修订提案**，不是功能完成报告、产品 PASS 或真实模型验收。

`CS_UAT_E2_BLOCKED_AT_STAGE_A`

**阻塞点：现有 Business Authority 合同无法完整表达“人工已经核对限制，但某项宣传仍待核实并禁止使用”，也没有把 Business 关键约束贯穿到 Persona 批准校验。** 直接沿用普通事实 approve/reject，会丢失未核实语义或约束本身；只向现有 derived constraints 写值，Business Persona 构建和消费又不接收这些语义。涉及的是限制的归属、作用范围、人审处置及批准/生产效力，不只是 UI 字段透传。

依本轮 E2-A.3：**“如果现有 Authority Contract 无法表达这种区分，先给出最小 Contract Amendment 方案。”** 本报告给出该方案。依 E2-A 阶段门禁及最终 STOP，暂停实现；没有进入 E2-B～E2-D，没有降低现有 critical blocker，也没有将现有只允许 Speaker 的控制层自行扩展为新的 Business 审批语义。

这里的停止是按本任务合同边界要求作出的判断，不是工具拒绝、测试环境故障或模型额度不足。现有合同可以通过下述修订修复；本轮未把提案当作已生效合同直接实施。

## A. Baseline / Worktree

| 项目 | 实际基线 |
|---|---|
| 主机 | `LIJIAN` |
| HEAD | `f10f3992433ab81df38ae90f9379ce1061a7afac` |
| 分支 | `feature/customer-speaker-smart-intake-v1` |
| E2 前差异 | 24 个 tracked 修改文件、8 个 untracked 文件；tracked diff 为 1,224 additions / 596 deletions，均为既有 CS-0～CS-3、UI 修复和 E1 报告 |
| 保护原工作区 | `E:\projects\ai-video-ops`；未编辑该工作区 |
| 保护 UAT | `E:\cs3node`；205 个原有 canonical JSON 建立 SHA 基线，现有数据库通过 SQLite 在线 backup API 创建独立安全快照 |
| 现有服务 | `127.0.0.1:18010`，PID 26304；没有启动第二个 Console、停止或重启现有服务 |
| 服务模式 | 既有 `browser_customer_speaker_intake_v1.py --workdir E:\cs3node --port 18010 --resume` 合成 driver；不代表真实模型能力 |
| 本轮模型 | Remote Model Calls = 0；没有调用 DeepSeek、Qwen、Whisper 或 GPU 工具 |

读取了当前 AGENTS、Operations Index、RUNBOOK、本机部署指南、Authority Map、验证路线及 E1 报告。开始前工作区字节快照、完整 diff、HEAD/status 和 UAT SHA 保存在 [start-baseline.json](E:/customer-speaker-e2-20261010/start-baseline.json)、[start-diff.patch](E:/customer-speaker-e2-20261010/start-diff.patch)、[start-status.txt](E:/customer-speaker-e2-20261010/start-status.txt)。安全快照保留在工作区外，不用于修改或恢复正在运行的 UAT 库。

## B. Root Cause Closure

E1 的 `SYNTHETIC_EXTRACTION_LIMITATION` 结论保留。本轮没有使用虚构预期输出评价 DeepSeek，也没有重新识别真实客户。

旧候选复用的幂等规则仍在；本轮没有删除候选、清空 checkpoint、重写来源 SHA 或伪造新的客户材料。旧提取遗漏尚未关闭，须在 E2-A 合同边界关闭后进入 E2-B。

本次增加的是**可复现根因证据**，不是根因修复完成声明。

## C. E2-A Constraint Extraction

### 已复现的合同断点

| 断点 | 当前实际行为 | 必须避免的“捷径” |
|---|---|---|
| Customer 输出 | `critical_constraint`、`forbidden_claims`、`unverified_claim` topic 不在白名单，会被忽略；顶层 constraints 也不被候选 builder 消费。正式 remote parser 最终只返回 facts/model/usage | 把限制挤进 differentiator，随后作为普通事实批准 |
| 标准人审 | 只支持 approve/edit/reject，不支持保留待核实；approve/edit 一律转 `known_candidate`，reject 清空值 | 用 approve 表示“我知道这项奖项尚未核实”，却把该宣传内容变为 Known |
| 限制容器 | Fact Candidate 的 `derived_authority_constraints` 可保存，但 Business input builder 不把它投影到 Persona | 写入一个没人执行的约束字段后宣布 Gate 完成 |
| Business 构建 | `persona_control_layer` 和非空 `critical_constraints` 明确只允许 Speaker；Business 输入会报错 | 改掉 scope 检查，却不定义批准及内容消费语义 |
| 批准共享校验 | Business `validate_required_fact_authority()` 不传入 critical_constraints；相同 facts 在外部 Readiness 收到关键约束时会阻塞，在该共享校验中不会 | 只在 Fact Review 时拦截，认为以后 Persona Approval 仍检查相同限制 |
| 补充解除 | `combined_critical_constraints()` 只要补充 Intake 有任一已批准/编辑事实，就把它全部 target_gaps 当作 addressed；无关菜单事实也能清除全局或指定 critical 缺口投影 | 把“补资料任务成功”当成“身份冲突已核实” |
| 内容约束 | 本地 blocked_terms helper 只读 `information_requiring_human_review.state=requires_review`；变为 known 后不再返回这些 terms | 用普通事实确认完成“限制审核”，同时丢掉待核实宣传的阻断 |

机器证据：[Customer 输出验证](E:/cs-intake-v1/ops-pipeline/scripts/customer_onboarding_analysis_v1.py:657)、[候选 builder](E:/cs-intake-v1/ops-pipeline/scripts/customer_onboarding_analysis_v1.py:689)、[remote 输出](E:/cs-intake-v1/ops-pipeline/scripts/customer_onboarding_analysis_v1.py:536)、[事实审核](E:/cs-intake-v1/ops-pipeline/scripts/customer_fact_review_v1.py:302)、[Business input](E:/cs-intake-v1/ops-pipeline/scripts/customer_fact_review_v1.py:460)、[解除逻辑](E:/cs-intake-v1/ops-pipeline/scripts/customer_fact_review_v1.py:586)、[批准共享校验](E:/cs-intake-v1/ops-pipeline/scripts/build_persona_v1.py:357)、[控制层 scope 检查](E:/cs-intake-v1/ops-pipeline/scripts/build_persona_v1.py:598)、[内容阻断词](E:/cs-intake-v1/ops-pipeline/scripts/generate_mix_scripts_v1.py:2506)。

**证据边界：**外部 Readiness 收到结构化 critical 时，当前 Gate 确实正确阻塞；诊断没有绕过 Console、运行 approve_persona、生成 Approval Receipt 或发现某个真实客户已经被错误批准。这里证明的是新增限制闭环不能依赖现有共享批准合同；不声称实际 UAT 已发生批准绕过。

### 最小 Contract Amendment 提案（尚未实施）

继续使用现有 canonical Intake、Fact Candidate、Human Review、Persona、Revision、Receipt；SQLite 仅投影。复用现有 `derived_authority_constraints` 容器，不建第二套 Constraint 数据库或生命周期。

1. **限制候选合同。** 在现有输出/候选容器中增加可验证的 restriction record：稳定 constraint_id、constraint_type、source_ref/raw_answer_ref、原始来源 SHA、逐字 evidence_quote、关联候选/主张引用、适用范围、待核实状态。四种类型为明确禁用、未核实宣传、主体/身份冲突、附条件事实。字段名与最终校验由现有机器 owner 定义；上述为提案，不能作为运行时 fallback。
2. **人审决定与事实决定分离。** 在现有 Human Review 扩展限制决定，支持确认限制、不采用不成立候选、保留待核实、基于来源解决具体冲突。记录 actor/time/原候选 SHA/引用证据。确认“禁止宣称获奖”只确认控制边界，不确认“已经获奖”。保留待核实不丢原始值，也不把宣传写成 Known。
3. **作用范围明确且 fail closed。** 未审核限制阻塞适用批准；来源明确的身份/核心真实性/整体安全冲突持续阻塞。只在运营明确确认“某项宣传被排除、其他事实独立成立”时，允许将该项未核实宣传保留为非生产内容。既有 critical 项不得因新的模型 scope、任意补充事实或通用 target_gap 被降级。无合法来源绑定/未知类型/未知范围均阻塞。
4. **Business 控制扩展进入同一批准合同。** 经合同确定后，扩展现有 Persona 控制层至 Business，并让 builder、approval validator、Console gateway、canonical resolver 与生产 Truth Projection 使用同一约束判断。只有确认的限制可成为控制记录；限制本身不成为可宣传业务 Fact。可排除主张不得进入可用 Known Truth；附条件事实不可在生成时丢条件。
5. **R1/R2 的限制生效点。** 需明确补充材料发现关键冲突时，对仍生效的 Approved R1 如何执行适用的批准/生产阻断：通过既有 canonical 约束解析与入口 Gate，保留 R1、Receipt 和 SHA，不改写批准字节，不让 Console 状态成为新真相。不得等到 R2 批准后才让已识别的核心安全冲突生效，也不得将 AI 候选自动升级为 Human 确认的客户事实。
6. **逐项解除，保留历史。** 删除“任意 known supplement → 所有 target_gaps addressed”的隐含推断。解除必须绑定确切 constraint ID、历史来源、具体新证据和显式 Human 决定；解决一个条目不解除其他条目。旧候选及旧人审始终不可变。
7. **兼容。** 无新增控制扩展的历史 Persona 保持原 content hash 计算、Approved bytes 和 Receipt；只对新增候选/Revision 写扩展。未知新字段或无效控制记录 fail closed，不能在旧消费者中静默忽略。相同来源/执行身份仍幂等。

需要 Architecture Review 收口的具体合同点是：限制的逐项人审决定与生产效力、Business 控制层作用范围、R1/R2 期间关键约束的执行入口。不是要求重议已批准的客户资料 UX 或降低 Readiness。

## D. E2-A Privacy / Egress Safety

对完全虚构的负向材料执行了真实 `build_privacy_projection()`、`build_prompt()` 和 `assert_safe_for_external_model()`，没有调用 provider：

- 标注“出生年月”的值仍进入实际 rendered Customer prompt，现有 egress validator 不阻塞。Schema 合法和 `external_model_gate_passed=true` **不足以证明最小化**。
- 带有一个私人电话的完整业务段落被 `project_safe_semantic()` 整段改为“文本包含联系信息（个人信息已隐藏）”。电话已去除，但主营服务、顾客场景和流程也同时丢失。这是输入内容相关的隐私投影缺陷，与合成 fixture 局限是两件事。
- 正式 remote entry 的确在调用 client 前检查 rendered prompt；问题是该检查与投影使用同一套不完整检测策略，本轮没有真实外发。

修订路线：保留本地原始来源；按 Customer / Speaker 任务处理最小必要字段，剔除生日、无关联系方式/证件、敏感经历和未经授权第三方资料；对长业务表单逐段/逐字段脱敏，不能让联系人字段吞掉全部业务内容；验证实际 rendered prompt，而非只验 Schema。Speaker analysis 继续消费其本人、必要、可追溯材料，不能复制整份客户资料。被过滤的片段不用于远端 evidence_quote，仍保留本地原文 SHA 和字段映射。

以上尚未实现。敏感经历与第三方信息的完整任务投影策略也未通过验收；不能宣布隐私安全 PASS 或允许 E3。

## E. Speaker Prompt Safety

现有 [Speaker Prompt](E:/cs-intake-v1/ops-pipeline/speaker_prompt.md:102) 示例仍包含具名人物、品牌和企业经营年限，并把企业年限放在 personal_material_quotes。诊断验证了后者；本报告不重复真实示例身份或经历。

方案为用完全虚构且不共享当前客户身份的示例替换，并增加企业经历/本人经历/其他人物归属的来源负向校验。仅把示例人名换掉不足以证明第一人称安全。尚未修改 Prompt，不声称污染风险已关闭。

## F. E2-B Saved Source Recovery

未进入此阶段。保留 Raw、Projection、旧候选、Review、Known Facts、Persona 与 Receipt。

后续应复用现有 Gap Supplement + Reviewed Context + Source Lineage，明确恢复意图、源 Intake ID/SHA 和目标领域；以独立新增候选及人审处理遗漏。相同恢复身份复用 Task/checkpoint，未新增事实不建空 R2，不重建已保存 Speaker。禁止删除旧候选或通过 same-input Retry 假装重新提取。

## G. E2-C Industry Recommendation

未实施。保持既有九项行业字典。建议必须有来源，未知不能默认通用；人工选择独立留痕。后续修复 blocked 客户摘要未消费人工行业的问题，分类标签不提升为 Approved Truth。

## H. E2-C Speaker Type Recommendation

未实施。维持 owner_founder / frontline_expert / brand / generic 与 null 的既有合同；null 不得隐式变 generic。后续 UI 优先持久化人工确认值，再呈现 AI hint；老板/创始人推荐不授予出镜意愿、本人经历或第一人称权限。

## I. Readiness Gap Explanation

未增加状态机。后续仅从 canonical 来源、候选、人审与冲突记录派生“原文未提供 / 提取遗漏 / 待审核 / 冲突 / 已覆盖”。不能按关键词或原文篇幅直接断言已满足能力组。

外部 critical 参数能够阻塞的现有事实已验证；没有放松 Readiness。E1 真实客户仍是合成提取遗漏，不需要重新提交已有主营、场景、具体业务和人物资料。

## J. Customer/Speaker UX Polish

本轮未改 UI、Toast、人物卡片、默认选择或流程文案；此前 CS-0～CS-3/UI 工作区成果全部保留。合并持久化结果反馈、减少等待提示及“事实保存 ≠ Persona Approval”的呈现仍待 E2-C。

## K. Golden Test Input

已核对指定 [Golden Input](E:/customer-speaker-uat-e1-20261010/golden-input.txt)：2,516 字符，完全虚构的餐饮业务、人物经历、服务条件、隐私限制、未核实荣誉和品牌关系，未复制真实客户全文。

本轮诊断另外使用少量独立虚构负向字符串；隐私负向样本中的出生年月不属于真人，不写入 Golden Input。没有把关键词规则加入 Production Analyzer。

## L. Golden Integration E2E

**未执行。** E2-A Gate 未通过，未启动新的 ASGI 验收实例、建立新业务记录或进行任何 Persona Approval。现有 18010 不被当作 E2 完整新前后端验收证据。

没有 mock 掉正式 Approval 后宣布 E2-D PASS；本轮根本没有运行 Approval。后续 Layer B 必须在独立 DB/canonical root，用正式登录、CSRF、Operation Lock、人审、Revision、Approval 与真实浏览器，仅替换模型边界。

## M. Negative Tests

运行 [诊断测试](E:/customer-speaker-e2-20261010/test_e2_a_contract_boundary.py)：**17 passed，0 skipped，0 failed，0.91s**。见 [JUnit](E:/customer-speaker-e2-20261010/e2-a-diagnostic.junit.xml)。

**这些断言要求现有缺陷可复现；绿色测试表示诊断成立，绝不是功能已修复。** 覆盖正确的显式 critical Gate、Business 共享校验遗漏、两个 Speaker-only extension 的拒绝、三种限制 topic 被忽略、顶层 constraints 被忽略、无 pending 人审动作、约束未进入 Business input、两种 target_gap 可被无关补充解除、生日进入 rendered prompt、电话导致业务投影丢失、普通 Known 转换丢失 pending blocked_terms、Prompt 企业年限示例，以及禁止网络的守卫自检。

所有测试只写全新短路径 pytest 临时目录；没有打开 UAT/生产 Authority、调用 approve_persona 或写 Approval Receipt。每个测试启用 socket/DNS 禁止守卫；所用函数无 provider 调用。没有模型费用。

## N. Desktop / Mobile Screenshots

**本轮无新增截图。** 没有 UI 修复，因此不拿旧截图冒充 E2 前后对比。所要求的行业/人物推荐、限制审核、恢复入口和真实缺口原因截图须在 E2-A～C 实施后按真实视口及操作验证。

## O. Full Regression

- 本轮已执行：17 项 E2-A 隔离合同诊断；`git diff --check` PASS。
- **未执行** E2-A 完整功能 integration、E2-B focused/integration、E2-C UI/API、E2-D Golden E2E 和 Full Repository Regression。原因是 A 阶段合同门禁阻塞，代码未实现，不把旧套件通过当作 E2 通过。
- 未执行 opt-in live Authority、真实模型或 4090 验收；均不计入通过数量。
- 待最终实现后仍需运行 `.\internal-console\.venv\Scripts\python.exe tools\verify.py`（仓库根目录）；Pipeline、Console/JS、Authority、migration/schema、compile 和 diff 验证结果须以实际新证据重新报告。

## P. Changed Files / Cleanup

本轮仓库唯一新增文件：本报告 `docs/design/CS_UAT_E2_EXTRACTION_AND_UX_CLOSURE_REPORT.md`。没有功能、Prompt、Schema、fixture、治理或运行配置改动。

工作区外新增基线快照、诊断测试、JUnit 和最终保护核对；未删除或归档任何旧脚本、旧输出、experiments 或 UAT 材料。32 个 E2 前已有 dirty 文件逐字节保护，原工作区数据库和 UAT canonical SHA 以 [最终保护结果](E:/customer-speaker-e2-20261010/final-preservation-results.json) 为准。运行库会话等自主写入不能被误称为整库字节不变，也不能为了哈希一致恢复运行库。

## Q. Remaining Risks

E2-A 的限制审核/生产控制合同、隐私最小化和 Prompt 污染尚未关闭。E2-B～D 尚未实施。行业、人物类型和丰富资料提取的真实 DeepSeek 质量没有验证。现有合成环境仍受输入支持范围限制，不可作为真实模型结论。

核心 blocker 是限制如何在既有 canonical 权威中持久化、逐项审核、作用于批准与生产，同时保持 R1/R2 不变量；不是要求客户再次填写同一份资料。

## R. Controlled Real Model Validation Plan

E3 **仅计划，不执行**。先关闭 E2-A～D Gate 和架构评审，再独立授权：固定正式模型/version、请求数和 token/费用上限；完全虚构资料；留存 source/projection/rendered-prompt SHA 及 egress 审计；用正式 provider 实际验证主营、场景、具体事实、行业、创始人、限制、不确定主张及第一人称归属。严禁回退到真实客户资料。

每一项输出只形成 Candidate，由人审判定；真实模型失败与 Contract/Projection/UI 失败分别记录。E3 不批准客户、人物、媒体权利或 Compatibility，也不部署 4090。

## S. Product Review Verdict Candidate

E2-A：BLOCKED；E2-B/C/D：NOT STARTED。无阶段 PASS、无最终 Product Review Ready。

需审查 C 节的最小 Contract Amendment 后再推进限制/隐私闭环；后续恢复与 UI 工作不得绕过未通过的 A Gate。已保护工作区既有修改、全部旧 UAT canonical 文件、Approved lineage 和原生产数据库。无 commit、push、部署、云/FRP 变更或远程模型调用。

`CS_UAT_E2_BLOCKED_AT_STAGE_A`

STOP，等待 Product / Architecture Review。

## T. 2026-10-10 Founder Approval 与正式实施追加记录

以上 A～S 是原诊断时的历史结论，未回写为通过。Founder 于
2026-10-10 明确批准最小 Contract Amendment；独立裁决为
`E2_A_CONTRACT_AMENDMENT_APPROVED_FOR_IMPLEMENTATION`，架构审批阻断已解除。

本次实际基线仍为 `f10f3992433ab81df38ae90f9379ce1061a7afac` /
`feature/customer-speaker-smart-intake-v1`，保留 24 tracked + 9 untracked
既有文件。现有 18010 未重启；本次 UAT 实查已有 207 个 canonical JSON，
全部建立 SHA 基线并保护（不是只保护旧清单的205个）。独立保护证据位于
`E:\customer-speaker-e2-implementation-20261010`。

### E2-A 正式 Gate

`CS_E2_A_CONSTRAINT_PRIVACY_PASS`

新增共享机器 owner `customer_constraints_v1.py`，在既有 derived constraints、
Human Review 和 Persona 控制扩展上实现四类限制、类型化人审、精确来源与
候选SHA、逐项有证据解除。它不写第二套 Authority。Business Builder、
Approval、canonical resolver 与生产入口执行同一规则；R2关键冲突临时
阻断R1生产，原批准与Receipt不撤销、不改写。Mix投影剔除禁用主张并检验
适用条件；未安全适配此合同的News路径明确阻断。详见Authority Map追加节。

Customer/Speaker任务投影按片段去除出生、联系方式及标明的敏感个人字段，
保留业务、否定、条件和归属；虚构Provider捕获测试检查完整实际Payload。
Speaker Prompt例子已虚构化，企业年限/他人经历有归属负向检查。

验证：35个Pipeline focused tests通过；正式HTTP认证、CSRF、business锁、
真实操作人和重放专项通过。最终受影响集成回归
`.verify/47f5745b/summary.json`：Pipeline、Console/JS、Authority release
全部通过，53.58s、state_unchanged=true。这是targeted，不标作Full或真实模型PASS。
旧17项诊断及原收据保留，不作为新正确行为标准。

保护复核：207个既有UAT canonical JSON未改变；原工作区数据库SHA未改变。
Remote Model Calls=0；无提交、推送、4090、生产资料或现有UAT数据修改。
E2-B/C/D随后按Gate继续，尚未据此宣告整个E2完成。

### E2-B 正式 Gate（2026-10-10 追加）

`CS_E2_B_SAVED_SOURCE_RECOVERY_PASS`

正式入口 `POST /api/customers/{business_id}/intake/recover` 使用认证、CSRF、
Business操作锁和已有Customer Task。恢复请求引用历史Intake、Raw/Projection
文件SHA和Raw Answers SHA、选定能力组、execution identity及已审核上下文。
同一身份重放返回原Task；失败仍使用已有retry/checkpoint路径，不删除旧候选。
新Intake显式标注历史来源恢复，不冒充客户新提交。模型前重新核验来源；新隐私
投影执行现行规则。只生成缺口候选，跳过旧Known字段与Speaker Discovery。
旧事实保留；无新增事实不创建空R2，新事实依旧独立人审与批准。

7项Pipeline专项、2项正式HTTP专项通过；受影响Pipeline/Console/JS/Authority
集成 `.verify/cc3d6e39/summary.json` PASS，50.12s，state_unchanged=true。
207个旧UAT canonical JSON和主工作区DB SHA复核不变。Remote Model Calls=0。
尚未以此宣告E2-C、D或正式模型质量通过。

### E2-C 正式 Gate（2026-10-10 追加）

`CS_E2_C_RECOMMENDATION_UX_PASS`

人审行业优先于旧AI/请求提示；blocked客户也展示已确认或明确不确定的分类，
该Projection不批准Persona。Speaker null不再默默变成generic，原AI hint与
人工类型分别保留，人工选择刷新后优先。人物UI默认预选，明确提交才建Draft。
Customer Prompt增加有逐字SHA来源的source_coverage观察（不是Known Fact），
页面依据来源、候选、审核、限制解释遗漏/待核对/未采用/冲突/已满足；历史无
覆盖证据时明确“尚未找到可验证来源”，不凭字数或关键词断言客户未提供。
事实提交只有一次与最终持久化结果一致的反馈，已保存人物不会再要求重新选择。

25项Pipeline专项、6项HTTP专项、JS真实渲染/回调专项通过。受影响集成
`.verify/50b26f83/summary.json` PASS（55.23s）。独立18011虚构环境浏览器
验证行业/owner_founder/四类限制、390×844真实滚动和保存点击、刷新与唯一人物
卡片；按钮top494.73/bottom542.73、无遮挡。截图及轨迹在外部E2证据目录。
207个旧UAT canonical JSON不变、Remote Model Calls=0。E2-D仍需独立完整验收。

### 最终闭环报告（2026-10-10；E2-A～D 当前结果）

#### 1. 实际工作树、完整增量与保护

主机 `LIJIAN`；工作树 `E:\cs-intake-v1`；分支
`feature/customer-speaker-smart-intake-v1`；HEAD 仍为
`f10f3992433ab81df38ae90f9379ce1061a7afac`。没有 commit、push、merge 或部署。
冻结 Case V1.1 未改动其业务代码、合同或 Approved 数据。

起始33个已有差异文件中，22个逐字节不变，11个在原成果上扩展；另有24个
起始无差异的文件发生本轮变化，其中16个是已有 tracked 文件、8个是新文件。
最终57个差异文件，**本轮实际增量涉及35个文件**。不能将包含CS-0～CS-3的
完整HEAD diff误写成全部由E2新增。

[开始快照与已有文件SHA](E:/customer-speaker-e2-implementation-20261010/start-baseline.json)、
[开始tracked diff](E:/customer-speaker-e2-implementation-20261010/start-diff.patch)、
[最终逐文件清单/SHA/分类](E:/customer-speaker-e2-implementation-20261010/final-worktree.json)、
[最终tracked diff](E:/customer-speaker-e2-implementation-20261010/final-tracked-diff.patch)
共同说明增量。Untracked新文件另列于清单，tracked patch本身不包含它们。

[保护复核](E:/customer-speaker-e2-implementation-20261010/final-preservation-results.json)：
全部207个旧UAT Canonical JSON SHA不变，原主工作区HEAD/status不变，原数据库
SHA不变。旧UAT数据库整库SHA发生变化；只读逐表比较显示仅`sessions.last_seen_at`
变化，账号、17个任务、migration、SQLite序列及案例批次表逐行不变。
见[数据库安全比较](E:/customer-speaker-e2-implementation-20261010/uat-db-read-only-comparison.json)。
没有恢复或覆盖这个运行库来伪造字节不变。原18010监听PID26304保持运行，未重启。

#### 2. 逐Gate裁决

| Gate | 当前结果 | 范围 |
|---|---|---|
| E2-A | PASS | 四类约束、类型化人审、批准/生产控制、最终Payload隐私、历史保护 |
| E2-B | PASS | 已保存来源恢复、精确SHA链、仅新增审核、幂等、无空R2/重复Draft |
| E2-C | PASS | 分类建议/人工优先/null、准确状态反馈、桌面与手机操作 |
| E2-D | PASS | 虚构Layer A/B、真实浏览器、正式全仓离线回归 |

`CS_E2_A_CONSTRAINT_PRIVACY_PASS`

`CS_E2_B_SAVED_SOURCE_RECOVERY_PASS`

`CS_E2_C_RECOMMENDATION_UX_PASS`

`CS_E2_D_GOLDEN_INTEGRATION_PASS`

上述是工程与隔离验收Gate，不是Founder Final Acceptance，也不证明真实DeepSeek
理解能力。原A～S的诊断结论及17项旧诊断收据仍保留。

#### 3. 机器合同与逐Gate文件

新增机器Owner：[customer_constraints_v1.py](../../ops-pipeline/scripts/customer_constraints_v1.py)。
合同`business-restriction-v1.0`使用已有`derived_authority_constraints`、
Candidate/Human Review和新的Business Persona控制扩展。没有SQLite业务Schema
变更或独立Constraint审批生命周期。稳定ID、四类受控类型、business/claim范围、
影响字段/禁止用语/成立条件、关联主张、Raw Answer/Intake引用与SHA、逐字quote、
pending_review/active/resolved、类型化Human Decision均由此Owner校验。

旧Persona hash算法未重定义；可选扩展只进入新候选/Revision。未知类型、范围、
无效来源和不一致审核SHA阻断。普通fact approve不能代替限制审核；exclude仅
用于未核实主张，resolve/dismiss要求准确来源及人审说明。Authenticated actor由
Console服务器绑定，不能由请求自行伪造。

E2-A：修改Business builder、approve、review、resolver、Customer/Speaker隐私
投影、Speaker Prompt及现有生产消费者；UI新增限制审核。E2-B：扩展已有
Customer Gateway/Task入口与analyzer的Gap Supplement来源合同。
`POST /api/customers/{business_id}/intake/recover`保留认证、CSRF、Business锁；
source+targets+execution identity重放返回原Task。E2-C：Customer Projection、
现有customer视图/组件、原JS回归。E2-D：扩展已有隔离浏览器driver，只在模型
边界注入两份明确虚构fixture，不另建运行Pipeline。

最终负向检查又发现并修复两处来源精度问题：

- 已保存Request的materials必须与原Raw的`freeform_customer_materials`完全相同；
  同时验证原Projection的business/intake及raw materials SHA，防止篡改Request
  冒充历史原文。模型前失败，无新Artifact。
- 不同Intake可存在相同legacy constraint ID。旧ID-only解除能错误清除另一来源，
  复现后改为ID+Intake+Raw Answers SHA+constraint SHA精确匹配；UI选择值也携带
  指定来源。解除一项后另一项继续阻断。原候选与决定均保留。

这两项修复完成后重新运行32项Pipeline专项、9项HTTP专项及正式全仓回归。
客户列表的数量本来统计Approved Speaker，最终文案明确为“已确认出镜人 N 位”，
不将Draft尚未批准误写成出镜人资料丢失；此最终UI状态也重新完成全仓验证。

#### 4. 风险与正向/负向证据

最终[Pipeline专项32项](E:/customer-speaker-e2-implementation-20261010/e2-d-final-source-contract.junit.xml)
及[正式HTTP专项9项](E:/customer-speaker-e2-implementation-20261010/e2-d-final-http.junit.xml)
均PASS，包含以下实际断言：

| 风险 | 已验证行为 |
|---|---|
| 四类限制被遗漏或批准为事实 | 有来源候选、独立typed人审；漏决定先阻断写审核 |
| 未核实宣传混入Known | exclude后独立事实可批准，奖项从Truth剔除 |
| R2 pending自动替换/改写R1 | R1/Receipt/SHA不变；有来源核心冲突暂时阻断当前生产 |
| 无关补充自动解除全部限制 | 无关Known不解除；精确解除一项不影响另一项，包括legacy重复ID |
| 来源/Quote/SHA篡改 | Raw、Projection、Candidate、Review及Request不一致均失败 |
| 非必要隐私进入远端 | Customer/Speaker实际Provider Payload捕获并验证；网络守卫禁止运输 |
| 公司/第三方经历转为第一人称 | 归属负向验证；Prompt使用完全虚构示例 |
| 恢复覆盖历史/重复成本 | 新Gap Supplement、保留原SHA、重放原Task、checkpoint复用 |
| 空恢复创建R2 | 无新增有效事实不建空Revision，Approved R1不变 |
| 分类覆盖人工/未知变generic | 人工行业及类型优先；null保留；明确uncertain独立保存 |
| 越过认证/人审/锁 | 正式HTTP登录/CSRF/锁/actor/重放；Business与Speaker分别批准 |
| 任意输入套用预置完整结果 | 不匹配fixture明确UNSUPPORTED_OFFLINE_FIXTURE，无候选/真实模型调用 |

原CS回归继续覆盖R1→R2、Speaker对精确新Business SHA显式复核、人物子步骤失败
不撤销客户审核、独立retry、Content Novelty与Ledger保护。它们在最终Full中执行，
没有用新Golden Expected Output声称正式模型已通过。

#### 5. 批准与生产消费者贯通

| 正式入口 | 实际适配与边界 |
|---|---|
| Business Builder/Approval | `build_persona_v1.py`与`approve_persona_v1.py`共享限制校验；仍需独立Human Approval |
| Canonical当前版本 | `show_customer_status_v1.py`验证新控制/hash，保留Approved R1并只读投影当前临时限制 |
| Console Creation Entry/options | `customer_gateway.py`、`content_gateway.py`限制creation_ready；不授予素材权利 |
| Canonical Creation/Capacity | `content_creation_entry_v1.py`在profile路径消费同一policy；机会与可行性维持独立 |
| Fact Atoms/Capacity计算 | `content_quality_v1.py`从合法Persona引用执行gate与安全Truth投影，禁用主张不成为生产atom |
| Source Matching/Mix plan | `match_generation_sources_v1.py`执行gate；既有Case/Pattern/Compatibility审核继续有效 |
| Mix生成/修订/审核 | `generate_mix_scripts_v1.py`加载时gate、安全投影和约束；成稿验证禁止用语及适用条件 |
| Mix导出 | `export_mix_excel_v1.py`核对实际Persona路径/SHA并检验发布限制；正式Console另验证批次lineage |
| Mix关闭/Ledger | `close_generation_export_v1.py`在closure前gate，不能通过旧批准批次绕开当前冲突 |
| Novel News机会/生成/审核/导出 | `novel_news_opportunity_v1.py`/`novel_news_v1.py`：含此新控制合同明确阻断，尚无安全适配 |
| News repurpose | `news_delivery_v1.py`：含此新控制合同明确阻断 |

共享Owner不写Authority。R2普通未核实宣传经明确排除后，不无理由阻断独立充分
事实；核心冲突在合法解决前维持阻断；解除不撤销旧审批或改写R1。
Legacy无lineage离线导出fixture的原兼容行为保留；其结果不能当作正式Console
可发布证据。正式发布路径须先完成canonical batch/source lineage验证。本轮没有
运行真实生成、发布、素材权利审批或Ledger生产写入。

#### 6. 最终Prompt/Egress与历史不变量

`project_task_materials`在已有隐私Owner中按片段处理生日、电话、证件及标明的
敏感个人信息，保留业务段落、否定、条件和归属。Customer投影不因一个电话
抹掉整段服务与场景；Speaker仅消费安全的本人资料。隐藏值不可回流为远端quote。
专项`test_actual_provider_payload_is_task_minimized_without_remote_calls`捕获实际
Provider将外发的完整Payload，断言敏感测试值缺席及业务语义保留；不是只检查
Projection Schema或安全标记。虚构测试socket/DNS禁止，真实传输次数为0。

旧UAT207个文件的保护见第1节。隔离浏览器恢复前76个Canonical JSON也全部
保持SHA，见[恢复保护](E:/customer-speaker-e2-implementation-20261010/d-browser-recovery-preservation.json)
与[最终隔离运行摘要](E:/customer-speaker-e2-implementation-20261010/d-runtime-final.json)。
同一恢复客户只有一个Speaker onboarding request/Draft；旧Raw/Candidate/Review
未覆盖；新候选位于新Intake。Layer B重放审核/恢复验证Approved Persona和Receipt
未改变。没有改写真实客户、Approved Case、Fingerprint、Compatibility或历史Ledger。

#### 7. Golden与真实浏览器轨迹

输入：[GOLDEN_INPUT_FICTIONAL.md](../../internal-console/tests/fixtures/customer_speaker_e2/GOLDEN_INPUT_FICTIONAL.md)；
输出：[synthetic_outputs.json](../../internal-console/tests/fixtures/customer_speaker_e2/synthetic_outputs.json)。
品牌、人物、服务、荣誉均虚构，不含真实出生年月/联系方式/客户经历。输出为预置
Contract候选，Production Analyzer没有加入品牌关键词匹配或fixture fallback。

Layer A五项确定性合同测试PASS；Layer B三项正式ASGI集成PASS，它们包含在上述
32/9项中，不重复累计。Layer B用独立SQLite/Canonical Root、正式认证/CSRF/锁/
Fact Review/Approval/Revision，只替换模型边界。默认运行数据库没有借用。

浏览器环境：`E:\cse2node02`，独立DB/Canonical Root，完整当前ASGI/Static和
逐SHA匹配的当前Pipeline scripts。正式HTTP健康为ok；当前实际监听
`127.0.0.1:18012` PID **21688**（venv launcher父PID10712），命令为现有
`browser_customer_speaker_intake_v1.py --workdir E:\cse2node02 --port 18012 --stage-delay 0.8 --resume`。
每端口独立session cookie。旧C阶段18011已确认无queued/running任务后停止；根目录
及证据保留。原18010保持运行；没有启动第二个Console操作它的数据库。

[浏览器轨迹](E:/customer-speaker-e2-implementation-20261010/e2-d-browser-trace.json)：

1. 完整虚构资料录入→自动进入事实审核；餐饮、owner_founder和四类限制建议。
2. 逐项人工审核→独立客户档案确认→真实显式Business Approval。
3. Speaker分析→本人三项事实审核→独立Speaker Approval→实际点击进入创作页。
   没有点击生成或运行远端模型。
4. 历史充分原文但旧候选只有名称→保存人工行业与一个Draft→点击“使用已保存
   资料补齐识别”→仅三项新增业务事实和四类限制→人审→停在独立Business批准入口。
5. 关闭页签重新打开、刷新，以及第二个既有虚构账号读取，均恢复服务端持久状态。
   原操作人归属保留，没有重新分析/选择同一已存Draft。
6. 显式合成失败→“继续分析”→回到候选审核。正式任务系统保留失败Task及一次
   显式retry Task，沿用同一Intake；这不是恢复请求重放，也没有并行重复模型运行。
7. Desktop1366×900、Mobile390×844真实滚动与点击。客户批准按钮top550.64/
   bottom598.64，实际点击成功；手机恢复审核底部按钮top711/bottom759，hit-test为
   button，未被导航遮挡（因候选未核对仍disabled，符合Gate）。C阶段保存按钮也实际点击。

主要真实视口截图均在外部证据目录，不使用full-page截图替代移动点击验证：

| 内容 | Desktop | Mobile |
|---|---|---|
| 分类/限制审核 | [分类](E:/customer-speaker-e2-implementation-20261010/d-desktop-fact-review.jpg)、[限制](E:/customer-speaker-e2-implementation-20261010/d-desktop-constraint-review.jpg) | [恢复审核底部](E:/customer-speaker-e2-implementation-20261010/d-mobile-retry-review-bottom.jpg) |
| 独立批准 | [批准后客户](E:/customer-speaker-e2-implementation-20261010/d-desktop-approved-customer.jpg) | [客户批准](E:/customer-speaker-e2-implementation-20261010/d-mobile-business-approval.jpg)、[本人审核](E:/customer-speaker-e2-implementation-20261010/d-mobile-speaker-facts.jpg)、[人物批准](E:/customer-speaker-e2-implementation-20261010/d-mobile-speaker-approval.jpg) |
| 创作入口 | 完整轨迹已实际进入 | [创作入口](E:/customer-speaker-e2-implementation-20261010/d-mobile-creation-entry.jpg) |
| 原文遗漏恢复 | [恢复入口](E:/customer-speaker-e2-implementation-20261010/d-desktop-omission-recovery.jpg)、[仅新增候选](E:/customer-speaker-e2-implementation-20261010/d-desktop-recovered-new-candidates.jpg)、[等待独立批准](E:/customer-speaker-e2-implementation-20261010/d-desktop-recovery-awaiting-approval.jpg) | C阶段[已存人物/阻塞原因](E:/customer-speaker-e2-implementation-20261010/mobile-saved-blocked.jpg) |
| 共享读取/失败恢复 | [第二账号](E:/customer-speaker-e2-implementation-20261010/d-desktop-second-actor-shared-review.jpg)、[失败](E:/customer-speaker-e2-implementation-20261010/d-desktop-retry-failure.jpg)、[恢复](E:/customer-speaker-e2-implementation-20261010/d-desktop-retry-recovered.jpg) | 手机滚动证据如上 |

#### 8. 正式全仓回归、未执行项

最终代码运行 `.\internal-console\.venv\Scripts\python.exe tools\verify.py`：
[正式summary](../../.verify/e6031b40/summary.json)，PASS，**51.59秒**，
state_unchanged=true。[安全结果摘要](E:/customer-speaker-e2-implementation-20261010/final-regression-results.json)。

| Target | 实际通过数 |
|---|---:|
| Pipeline | 457 |
| Console | 369 |
| Authority release | 12 |
| FRP Guard纯离线回归 | 30 |
| Verification coordinator | 24 |
| 合计 | **892** |

所选测试0失败、0错误、0跳过。默认opt-in live Authority被排除，**未计入892**。
Console执行16个JavaScript文件，exit_code=0；JS是Console嵌套验证，不额外作为
16项Python测试计数。Migration/schema测试包含历史账号/任务保留、已填充备份
升级、重复启动检测、失败事务回滚及并发initializer一次应用；001～004均无本轮
SQL变更。隔离DB当前正式migration正常应用；不将测试备份升级等同生产migration。

全仓route没有独立compile target，因此另运行stdlib `compile`扫描Pipeline scripts/
tests、Console app/tests/scripts及tools共204个Python文件，PASS，无写入runtime。
见[Compile证据](E:/customer-speaker-e2-implementation-20261010/python-compile.json)。
最终`git diff --check` PASS。最终Full执行后仅追加本报告与Authority Map说明，
未再修改可执行代码。

未执行真实DeepSeek/Qwen/Whisper/Qiyun、4090部署、真实Production Approval/生成/
发布/媒体权利、opt-in live Authority或实体第二设备测试。浏览器跨账号和关闭重开
已测，但不宣称真实手机硬件/实体跨设备或真实模型质量PASS。

#### 9. 修改文件与替代关系

以下35项为本轮实际增量，完整HEAD差异另见第1节57文件清单。

**原有差异上扩展11项：**

```text
docs/design/CS_UAT_E2_EXTRACTION_AND_UX_CLOSURE_REPORT.md
docs/operations/AUTHORITY_MAP_V1.md
internal-console/app/content_gateway.py
internal-console/app/customer_gateway.py
internal-console/app/main.py
internal-console/static/assets/customer-components.js
internal-console/static/assets/customer-views.js
internal-console/tests/browser_customer_speaker_intake_v1.py
internal-console/tests/js/customer-speaker-smart-ux.test.mjs
ops-pipeline/scripts/customer_fact_review_v1.py
ops-pipeline/scripts/customer_onboarding_analysis_v1.py
```

**起始无差异、本轮修改的已有16项：**

```text
ops-pipeline/scripts/approve_persona_v1.py
ops-pipeline/scripts/build_persona_v1.py
ops-pipeline/scripts/close_generation_export_v1.py
ops-pipeline/scripts/content_creation_entry_v1.py
ops-pipeline/scripts/content_quality_v1.py
ops-pipeline/scripts/export_mix_excel_v1.py
ops-pipeline/scripts/generate_mix_scripts_v1.py
ops-pipeline/scripts/match_generation_sources_v1.py
ops-pipeline/scripts/news_delivery_v1.py
ops-pipeline/scripts/novel_news_opportunity_v1.py
ops-pipeline/scripts/novel_news_v1.py
ops-pipeline/scripts/privacy_projection_v1.py
ops-pipeline/scripts/show_customer_status_v1.py
ops-pipeline/scripts/speaker_discovery_v1.py
ops-pipeline/scripts/speaker_onboarding_analysis_v1.py
ops-pipeline/speaker_prompt.md
```

**新增8项：**

```text
ops-pipeline/scripts/customer_constraints_v1.py
ops-pipeline/tests/test_customer_constraints_e2_v1.py
ops-pipeline/tests/test_saved_source_recovery_e2_v1.py
ops-pipeline/tests/test_customer_speaker_e2_golden_contract.py
internal-console/tests/test_customer_constraints_e2_http.py
internal-console/tests/test_customer_speaker_e2_golden.py
internal-console/tests/fixtures/customer_speaker_e2/GOLDEN_INPUT_FICTIONAL.md
internal-console/tests/fixtures/customer_speaker_e2/synthetic_outputs.json
```

新共享Owner替代原review中“任意Known补充清空全部target gaps”的逻辑；Task、
分析Pipeline与浏览器driver均在原文件扩展。旧17项诊断保留历史用途，不放进
正式默认回归作为旧错误行为标准。没有新增第二套运行入口、清理experiments、
删除旧候选或Approved Artifact。本轮外部证据脚本只做只读核对与收据生成。

#### 10. 评审候选与剩余风险

当前达到**Product / Architecture Review Candidate**。无已知阻塞回归。
以下为后续验收边界：

- News对新Business限制合同尚无完整安全消费适配，明确fail closed；不得按Mix
  隔离通过推断News可生产。解禁需独立实现/评审。
- 限制候选及行业/人物建议的真实提取质量尚未验证。来源coverage属于可追溯的
  AI观察，不是Human Truth；历史无coverage时保留来源未知，不伪称用户缺资料。
- 当前片段隐私规则处理受支持格式及标明的敏感字段；自由叙事、变体隐私表达和
  模型对否定/条件/归属的实际理解仍需E3受控验证。规则不被宣称为所有自然语言
  隐私的自动检测保证。
- 发布检查对合同中的来源绑定用语/条件采取保守精确检查；真实生成的同义改写、
  提取遗漏及跨主张影响需要真实模型与Founder审核评估，仍保留Human内容审核。
- 当前隔离浏览器为合成验收入口，不应用于真实客户资料；不匹配输入明确不支持。
  `http://127.0.0.1:18012`保留供离线评审，DB与Canonical Root在`E:\cse2node02`。

E3计划仍**未执行**：另行Founder授权后，用完全虚构资料固定正式Provider/model/
version、请求数及token/费用上限；先审核完整safe projection/rendered prompt及
Payload SHA，再受控真实提取。验证四能力组、行业、Founder类型、四类限制、
未知宣传与公司/本人/第三方归属；输出仍仅Candidate，禁止自动Approval或生产。
若privacy/contract/egress Gate失败立即停止，不外发真实UAT原文。

`Remote Model Calls = 0`

`CS_UAT_E2_EXTRACTION_AND_UX_READY_FOR_PRODUCT_REVIEW`

STOP，交回独立Product / Architecture Review；不提交、不推送、不部署。

### E2-UX 异常优先审核：UX-1 合同审计与停止记录（2026-10-10）

本节是 Founder 授权 `E2-UX Review-by-Exception Amendment V1.0` 后的新审计，
不改写上面的 E2-A～D 历史结果，也不把旧 892 项 PASS 计作本轮验收。

**当前裁决：`CS_E2_UX_BLOCKED_AT_UX_1`。**

#### A. Engineering Baseline 与保护

- 主机 `LIJIAN`，工作区 `E:\cs-intake-v1`，分支
  `feature/customer-speaker-smart-intake-v1`，HEAD
  `f10f3992433ab81df38ae90f9379ce1061a7afac`。
- 起始已有 56 条 Git status 差异记录；tracked HEAD diff 为 40 文件、
  1996 insertions / 733 deletions，包含此前 CS/E2/UI 成果，不是本轮新增。
- 已记录全部 408 个非忽略源码文件的 SHA，并在仓库外保留源码快照和完整
  tracked diff。证据目录：`E:\customer-speaker-e2ux-20261010`。
- 本轮保护基线：`E:\cs3node` 207 个 Canonical JSON，
  `E:\cse2node02` 98 个，原工作区 `E:\projects\ai-video-ops` 951 个。
  运行数据库以只读连接逐表取摘要，仅排除既有 Session `last_seen_at` 心跳字段。
- 18010 PID26304、18012 PID21688 均仍监听 `127.0.0.1`。未重启、借用运行库或
  建立新的验收服务。原工作区和旧审核没有修改。

#### B. UX Before / Target 与真实阻断

普通事实默认待统一确认、四类限制预填、最终一次提交，均是获批的 UX 目标。
当前后台已经能在一次请求里形成多项真实人审决定，但只能审核**完整候选集合**。
不能把“审核已保存但档案因核心冲突未批准”和“部分普通事实尚未审核”混为一谈。

本轮只读检查确认两处尚不能安全映射的要求：

1. **修改限制内容、成立条件或适用范围。**
   `customer_constraints_v1.normalize_decisions()` 仅保留现有类型化决定、说明、
   解除证据与精确目标。尝试带入修改后的条件、影响字段或禁用词，字段会被忽略；
   新的限制 `edit` 决定也被拒绝。`apply_decisions()` 保留原始控制内容，
   `collect()` 会从原候选及人审决定重新计算并逐项比对，不能用 UI 文本替换它。
   因此显示可编辑字段却提交原限制，会造成屏幕与实际生产控制不一致。
2. **暂留未处理普通事实异常，仅保存其他合法事实。**
   `customer_fact_review_v1.validate_decision_coverage()` 要求覆盖全部
   `requires_review`；普通决定只有 `approve / edit / reject`，没有暂留决定。
   部分集合返回 `FACT_REVIEW_INCOMPLETE`；借用 `reject` 表示“尚未核对”会伪造
   人工不采用决定。已终结的该 Intake 人审指纹不可替换，不能通过第二次覆盖来补齐。

现有 `identity_conflict → defer` 能保存全部合法事实决定而继续阻断档案批准；
这是可复用能力，但它不能证明普通事实的部分提交和逐项恢复已经实现。

依本轮实施指令 UX-1：“如发现必须变更新的事实 Authority 或生产安全规则，
停止并提交最小 Contract Delta，不自行实施。”因此未进入 UX-2～UX-5。
没有仅隐藏按钮、自动拒绝异常或新增前端真相来绕过这个 Gate。

#### C. 可直接复用的 Authority Mapping

| 待提交界面建议 | 最终明确提交时的现有 Canonical 决定 | 边界 |
|---|---|---|
| 普通安全事实：采用此信息 | `approve` | 打开页面不写人审；缺证据、冲突或未知类型不预选 |
| 事实修改 / 不采用 | `edit` / `reject` | 修改值进入现有审核；保留原候选与来源 |
| 禁止使用这类宣传 | restriction `confirm` | 宣传禁用持续有效，不生成宣传 Known Fact |
| 暂不宣传这项信息 | restriction `exclude` | 仅用于未核实主张；不等于核实奖项 |
| 需要进一步核实 | restriction `defer` | 保留现有阻断；不擅自放宽 Persona / Production Gate |
| 主体冲突：相关内容暂不能使用 | restriction `defer` | 不能默认变成 `resolve` |
| 仅在原条件下使用 | restriction `confirm` | 必须展示并保留完整原条件 |
| 纠正识别 / 补充核实资料 | `dismiss` / `resolve` | 必须准确的新来源、说明和精确目标 SHA |

认证、CSRF、business Operation Lock、逐项 actor/time、候选 SHA 和旧不可变审核
仍由原 Console Gateway / Canonical Owner 负责。本轮不新增审核 Authority。

#### D. 最小 Contract Delta 提案（未批准、未实现）

1. **限制修订：**由 `customer_constraints_v1.py` Owner 在现有 Human Decision
   容器中定义受控的修订载荷，保留原 `constraint_id`、原候选 SHA、原始来源与
   控制内容，并绑定修订依据及 actor/time。只允许证据支持的影响字段、禁用内容
   或条件变化；核心身份冲突的类型及 business 范围不得降级，解除仍用精确证据 Gate。
   `apply_decisions / collect / policy` 必须一致派生有效控制，不能只更新前端或 SQLite。
   历史 Approved Persona / Receipt / SHA 不重写，新字段仅用于新的人审/Revision。
   字段名和合同版本应由 Owner 审查确定，本提案不定义新的运行时 fallback。
2. **部分审核：**由 `customer_fact_review_v1.py` Owner 明确同一 Intake 下的
   可追加、不可变逐项人审记录及恢复语义。已提交决定必须绑定准确候选集合/SHA；
   未处理候选保持待审核，不自动 `approve/reject`。已有决定不被下一次提交覆盖。
   Gateway 只编排这些既有 Human Decisions，不建立新的业务 Batch Lifecycle。
   Canonical Resolver/Builder 对尚未覆盖的关键事实保持现有安全 Gate；不能只删除
   全量覆盖校验就宣称支持部分保存。多文件操作不宣称事务原子性。
3. **提交保护：**使用 actor 绑定的审核上下文，包含 Intake、候选集合/文件 SHA、
   已有人审、当前约束状态、相关 Persona Revision/SHA。锁内比较过期状态；合法
   重放先识别相同提交及已持久化项，恢复剩余步骤，不覆盖别人的人审或包含未展示新增项。
   这些是 Gateway 编排适配，不替代 Canonical 人审。页面打开只做只读 Projection，
   不缓存真实材料到 localStorage。

权限补充：现有工作台允许已认证同事读取共享客户，E2 曾验证跨设备/账号读取。
本轮应阻断他人审核上下文和提交身份的复用。若“跨账号读取阻断”指客户记录本身
新增按账号隔离，需另行明确权限决策，不能静默破坏既有协作读取。

#### E. Safety / Browser Evidence

只使用虚构内存候选调用实际 Contract Owner。未打开或提交现有 UAT 人审，未调用
远端模型、创建 Speaker/Persona 或改变 Authority。诊断输出只包含合同字段和错误码。
原 18010/18012 保留；新的三条轨迹和部分失败浏览器验收尚未执行，不能引用旧截图
代替本轮 Review-by-Exception 成果。

#### F. 本轮验证与证据

- [合同诊断收据](E:/customer-speaker-e2ux-20261010/ux1-contract-audit.json)：
  修改字段被丢弃、限制 edit 不被接受、部分事实集合被拒绝、普通 defer 不被接受，
  以及现有四类合法映射。前四项是**阻断证据**，不是新 UX PASS。
- [起始保护快照](E:/customer-speaker-e2ux-20261010/start-baseline.json)、
  [起始完整 tracked diff](E:/customer-speaker-e2ux-20261010/start-diff.patch)。
- [最终保护与本轮文件清单](E:/customer-speaker-e2ux-20261010/protection-and-changes.json)。
- 本轮产品代码、Schema、运行数据无变更；只在本报告追加新审计章节。
- 未执行 focused 新行为测试、integration、新浏览器 UAT、full regression；原因是
  UX-1 尚无完整合法合同映射，按 Gate 要求停止。旧 892 项通过保留为历史证据。
- `git diff --check` 单独验证文档变更；live opt-in、真实模型、生产验证均未执行。

#### G. Remaining Limits / 后续入口

需要独立 Product / Architecture Review 审查 D 中两个 Canonical Amendment。
批准后才实施默认选择、异常区域、统一保存、精确提交身份及失败恢复，并按
UX-2→3→4→5 执行本轮验收。News 路径继续原阻断；E3、4090、生产资料均未触及。

`Remote Model Calls = 0`

`CS_E2_UX_BLOCKED_AT_UX_1`

STOP。未达到 `CS_E2_UX_REVIEW_BY_EXCEPTION_READY_FOR_PRODUCT_REVIEW`。

### E2-UX 正式合同与异常优先审核实施（2026-10-10～11，UX-1 批准后）

本节追加真实实施记录，保留上节诊断时的 BLOCKED 裁决。Founder / 独立架构
裁决为 `CS_E2_UX_UX1_CONTRACT_APPROVED_FOR_IMPLEMENTATION`；授权范围是限制
修订、同一 Intake 的追加式部分审核、现有 Gateway 提交上下文及 UX-2～5。
该批准没有授予 Persona、Speaker、Case、媒体权利或生产兼容性自动审批。

#### 1. Engineering Baseline / 本轮增量与保护

- 主机 `LIJIAN`；隔离开发工作树 `E:\cs-intake-v1`；分支
  `feature/customer-speaker-smart-intake-v1`；HEAD 保持
  `f10f3992433ab81df38ae90f9379ce1061a7afac`。
- 本轮起始仍有 56 条 status、40 个 tracked 文件差异。当前整个工作树包含此前
  CS-0～3、E2-A～D、UI 改动，不能把 HEAD diff 全部算成本轮工作。
- 新证据目录为 `E:\customer-speaker-e2ux-implementation-20261010`，保留
  `start-baseline.json`、`start-diff.patch`、逐文件 `source-before/`。
  `incremental-diff.patch` / `incremental-files.json` 记录相对本轮起点的增量，
  `final-diff.patch` 记录最终完整 tracked HEAD diff。未提交文件也进入增量清单。
- 独立浏览器节点 `E:\csuxnode01`，SQLite `console.sqlite3`，Canonical Root
  `E:\csuxnode01\ops-pipeline`，端口 18013。正式 ASGI/Static/登录/CSRF/
  Business Lock/Review/Persona Owner 均使用当前代码，仅模型边界为明确的合成夹具。
- 既有 18010（PID 26304）、18012（PID 21688）未重启；新 18013 监听 PID 24628。
  本轮仅重启自己的新节点以加载代码，先检查无运行/排队任务；不使用旧运行库。
- 只读保护核验：`E:\cs3node` 207 个、`E:\cse2node02` 98 个、主工作区
  951 个 Canonical JSON；共 1256 个 SHA 与本轮开始一致。既有 SQLite 表摘要、
  主工作区 HEAD/status 一致。表摘要仅排除正常 Session `last_seen_at`。
  详细结果见新证据目录 `protection-and-changes.json`。
- 未修改数据库 Schema、迁移文件、原 Approved Persona/Receipt、Case 冻结成果，
  未清理实验或历史候选；未 commit/push/merge/deploy。

#### 2. UX-Contract-A：限制修订与一致消费

唯一 Owner 仍为 `customer_constraints_v1.py`。原 `business-restriction-v1.0`
保持不变，在新 Human Decision 中使用 `restriction-amendment-v1.0`：

- 精确绑定原 constraint digest、Candidate 文件 SHA、原来源/quote/control；
  保存 effective control、修订 quote/source、reason、production_impact，
  以及正式 Reviewer/time。原候选不改写。
- 正式控制字段为 `scope/affected_fields/blocked_terms/condition`。未知字段、
  不受支持版本、缺来源/理由/影响、SHA 不一致一律拒绝，不静默丢弃。
- 只允许在 `confirm/defer` 上修订，不借修订执行 `resolve/dismiss/exclude`。
  不改变 scope/type；核心主体控制变化必须走原精确解决 Gate。
- 禁用词须出现在修订依据；缩小禁用词/影响字段不能仅复用原证据或原句的拼接。
  附条件事实保留原有成立条件，并验证有效条件来自原文；不生成无条件版本。
- `normalize_decisions → apply_decisions → collect → policy` 同源；Builder、
  Resolver 和受支持消费者继续消费这个 Owner 的有效结果，没有 SQLite 控制真相。
  未核实宣传不会因编辑或限制确认变为 Known。
- 浏览器 AM 轨迹将禁用词从原三项扩大加入原文已有的“最好”，填写准确依据、
  原因和影响；统一保存后刷新，正式 `collect/policy` 和档案只读页均显示新控制。
  原 Candidate SHA 不变，原控制保存在 Human amendment 中。
- 已保存决定不能从新批量请求直接更正。后续更正继续使用既有有来源的补充/
  Revision/精确解决流程；本轮不新建更正生命周期。

#### 3. UX-Contract-B：部分保存与最终完成独立

`customer_fact_review_v1.py` 在同一 Intake 下新增
`customer-fact-review-progress-v1.0`：`review_progress/<sequence>_<operation>.json`。
这是原 Fact Review Authority 的不可变增量，不是第二套 Batch Authority。

- 每个增量绑定 Candidate 文件 SHA、Intake 文件 SHA、候选 ID、原来源、实际
  actor/time、请求摘要、服务端 operation identity 和父 receipt SHA。
- 确定性读取所有增量，只对本次选择逐项生成既有正式 Human Decision。未提交
  项仍 Pending，不虚造 defer/reject。重复 operation 必须 actor/内容完全一致。
- 完整审核仍要求覆盖全部必须审核的事实和限制；`FACT_REVIEW_INCOMPLETE`
  保留。部分保存不生成 Persona Input 或 Approval，不标记任务已完成人审。
- 覆盖完整后才调用原完整 Review / Builder，逐项保留各次真实 actor，最终
  Persona 是否可批准仍独立经过 Readiness/Restriction/Revision/Human Gate。
- 历史完整审核格式仍可读、不转换、不重算 SHA；已有 journal 不允许 legacy
  完整请求覆盖。已落盘决定也不允许新的操作身份覆盖。
- 新正向测试覆盖 10 项一次提交、10 项先 8 后 2（含修改/不采用）、两 actor、
  原 receipt/候选 SHA 不变及最后两项提交前完整审核不能 PASS。

#### 4. UX-Contract-C：提交身份、多人协作与中断恢复

`customer_gateway.py` 签发只读、actor/node 绑定上下文。里面有 business/intake、
Candidate SHA、当前全部 Intake/Review/Constraint/Persona 快照 SHA、operation ID。
token 不含事实内容，也不成为 Authority；进程 HMAC key 不落盘、不输出。

- 正式 POST 在认证、CSRF、Business Lock 内重核快照，然后才调用 Owner。
  页面打开/筛选/预选/展开依据不会写 Human Review。
- 当前 actor 必须匹配；其他同事仍可读取共享客户，但不能借上下文/幂等身份
  提交。新增候选、其他人已保存审核、Persona/约束变化使旧页面明确失效。
- 精确已提交请求可从不可变 receipt 校验重放，即使进程重启 HMAC 改变也不重复
  决定。尚未提交的旧 token 则须刷新；不能从旧页面默默包含新增候选。
- receipt 是已持久化决定的提交点，后续多文件整理**不宣称原子事务**。中断后
  UI 显示实际保存数量、待处理数量和恢复入口；原提交同事刷新后继续后续步骤。
- Browser D 的第一张 receipt：同事 B 的 2 条事实；第二张：同事 A 的 4 条事实+
  3 项限制。故障发生在第二张落盘后、完整 Review 文件写入前；恢复后仍恰好
  两张 receipt，没有重复决定。未发生自动 Business Approval。

#### 5. UX-2 Before / After 与状态映射

普通安全候选直接展示、默认“待统一确认”，保留修改、不采用、暂不处理及实际
来源展开，取消普通项逐条确认主按钮。资格由合法来源、quote、事实类型、冲突和
当前限制派生，不使用模型自报置信度。高风险/来源不完整项不默认采用。

四类限制建议映射现有 Enum：宣传禁用 `confirm`；未核实主张 `defer`；身份冲突
`defer`；完整条件 `confirm`。`exclude` 必须由同事明确选择，提交摘要逐项公开
展示；`resolve/dismiss` 仍要求准确来源与说明，不能一键解除主体冲突。

底部一个“确认并保存已核对的信息”，动态显示采用/修改/不采用/待核实/未处理/
关键冲突数量，以及每项重要决定；限制编辑额外展示修改控制、依据、理由和影响。
已保存事实、限制只读重读；不要求重复确认。编辑后切回采用时恢复原值预览，
确保屏幕值与提交值一致。恢复后正式完成只写“事实审核完成”，不冒充档案已批准。

Speaker 默认预选及独立审核不变；仅保存人物时仍复用已有 discovery confirmation
入口，不伪造空 Fact Review。客户与人物部分成功只出现一条与持久化结果一致的
反馈。未提交编辑仅存在内存，离开提醒；没有敏感事实 localStorage 缓存。

#### 6. UX-3 Focused / Integration

新结果（非旧 892）：Pipeline 三模块 41 项通过；追加 10 项一次性覆盖分支后，
Owner 最终模块 28 项通过；Console 四个受影响模块 38 项通过；界面与 JS 桥接
10 项通过。直接 Node 专项检查也通过，包含真实 binder 预览状态转换、十条默认
选择一次 POST、独立 Speaker 保存兼容和一次准确反馈。

证据在新目录：`focused-pipeline-final.xml`、`focused-owner-final.xml`、
`focused-console-final.xml`、`focused-presentation-final.xml`。这些集合有重叠，
不简单相加作为独立覆盖数量。

覆盖来源/SHA、限制修订、无依据缩小、未知版本、条件丢失、核心冲突、精确单项
解除、legacy 重复 ID、历史不可变、partial/full、候选变更、其他 actor、CSRF、
共享读取、重放、崩溃恢复、无自动 Persona Approval 和原生产 Gates。

执行中出现的失败保留：默认 Windows Temp 路径过长/pytest-current 权限问题，
改用新短路径后通过；第一次短路径调用缺少父目录，setup 错误，不计为测试通过。
首次 full 的唯一失败是旧 Customer `ReviewList` 结构断言，已按批准新交互修改，
Speaker 原有 `ReviewList/bindDecisionControls` 检查保留；不是删掉安全测试来 PASS。

#### 7. UX-4 新隔离浏览器轨迹与证据

所有截图均为本轮新 18013，不复用旧 E2-D 图。完整安全 Canonical 摘要、逐项
决定/actor/时间/operation/receipt SHA、source SHA、有效控制、截图 hash 在
`browser-canonical-evidence.json`。只包含新节点虚构样本，不含真实客户原文、
密码、Cookie 或完整日志。

| 轨迹 | 实际操作与结果 | 新截图（相对证据目录） |
|---|---|---|
| A 正常 | 6 条普通事实默认待确认；明确排除未核实宣传；一次提交 6+3 项；Review 完整、Persona 仍未批准 | `desktop-overview-normal.jpg`、`normal-review-complete-not-approved.jpg` |
| B 修改/排除/部分保存 | 改行业及服务两项，不采用一项；另两项事实保持 Pending，未核实宣传 defer；先保存 4+3，再刷新提交 2；不采用未被重新采用、宣传仍待核实 | `desktop-edited-facts.jpg`、`mobile-submit-summary-before.jpg`、`mobile-partial-progress.jpg`、`mobile-partial-finished-still-blocked.jpg` |
| C 核心冲突 | 无证据 resolve 被阻断且不写审核；其他事项分两次合法保存；最终主体冲突仍 active、Approval/Production 仍阻断 | `desktop-critical-conflict.jpg`、`critical-conflict-review-complete-blocked.jpg` |
| D 双同事/中断 | 两 host 的独立登录 Session 读取同一客户；B 保存后 A 旧页面拒绝；A 刷新提交后整理故障，刷新恢复未重复决定 | `two-actors-stale-page-blocked.jpg`、`durable-decisions-completion-interrupted.jpg`、`two-actors-recovery-complete-not-approved.jpg` |
| AM 限制编辑 | 有来源扩大禁用词并记录修订影响；保存后刷新，正式控制与只读档案页一致 | `restriction-source-backed-amendment-before.jpg`、`restriction-source-backed-amendment-after.jpg` |
| 手机来源/编辑 | 实际 CSS 视口 390×844，展开依据、编辑、底部点击、刷新；另外聚焦 textarea 的 390×500 缩短视口无横向溢出，真实提交成功 | `mobile-source-and-edit-390x844.jpg`、`mobile-reduced-height-edit-390x500.jpg`、`mobile-final-review-pending-persona.jpg` |

手机主按钮实测 48px 高，底部导航之上保留间距，最后卡片可以滚动操作。截图
输出受浏览器捕获尺寸影响，文件像素尺寸另在 JSON 记录；不将其冒称设备原生
截图。`mobile-reduced-height-edit.jpg` 实际为另一标签未缩放的桌面截图，JSON
明确标记不作为手机证据。未测试实体 iPhone 与真实软键盘，缩短视口只是补充证据。

正常 Golden 的合成变体明确移除不存在的主体冲突来源，若原文仍有冲突则拒绝
套用无冲突结果。预置额外事实均有精确虚构 quote，不是正式 Analyzer 品牌规则。
一次初始合成 quote 不匹配导致显式失败，修正夹具后走正式 Retry，保留任务历史，
没有删除候选或把不支持输入伪装为真实分析成功。

#### 8. Changed Files / 旧实现关系

相对本轮起点的代码/测试/Owner导航增量：

```text
ops-pipeline/scripts/customer_constraints_v1.py
ops-pipeline/scripts/customer_fact_review_v1.py
internal-console/app/customer_gateway.py
internal-console/app/main.py
internal-console/static/assets/customer-views.js
internal-console/static/assets/app.js
internal-console/static/assets/styles.css
ops-pipeline/tests/test_customer_constraints_e2_v1.py
internal-console/tests/test_customer_speaker_e2_golden.py
internal-console/tests/js/customer-speaker-smart-ux.test.mjs
internal-console/tests/test_productization_ui_stage2.py
internal-console/tests/browser_customer_speaker_intake_v1.py
docs/operations/AUTHORITY_MAP_V1.md
docs/design/CS_UAT_E2_EXTRACTION_AND_UX_CLOSURE_REPORT.md
```

正式运行、页面、测试 driver 均在既有文件扩展；客户专属控件替代其逐条确认，
共享 Speaker 控件没有替换。外部只读快照/摘要脚本是证据工具，不是第二套运行
入口。历史 UX-1 诊断、旧审核、Approved Artifacts 和 experiments 均保留。

#### 9. Remaining Limits / 停止边界

本轮仅离线工程与浏览器合成验收；真实 DeepSeek 提取质量、E3、4090 部署和生产
验收均未执行。News 新限制合同下继续 fail-closed。不能将合成候选、测试数量或
默认 UI 选择视为真实模型质量、Human Approval、媒体授权或 Production PASS。

限制修订采取保守来源 Gate：核心范围不通过文字编辑降级；条件修改须保留原条件。
已保存决定不能在新统一提交中直接覆盖。未提交上下文在服务重启后需刷新，已提交
精确请求可重放；恢复完成步骤由原最后提交同事执行。多文件恢复不是原子事务。

UX-2、UX-3、UX-4 的本轮证据已成立；UX-5 以随后正式完整回归结果为准。
`Remote Model Calls = 0`。不自动进入 E3，不提交、不推送、不部署。

#### 10. UX-5 最终回归与 Product Review Candidate

最终代码和测试状态运行正式根入口：

```powershell
.\internal-console\.venv\Scripts\python.exe tools\verify.py
git diff --check
```

本轮 Full Regression `539aeaef`：**906 passed、0 failed、0 errors、0 skipped**，
55.18 秒。运行期间源状态稳定，全部选择目标执行完成。
收据：`E:\cs-intake-v1\.verify\539aeaef\summary.json`。
首次失败收据 `ce4bddc8` 保留，不用其代替最终结果。

| 正式检查 | 实际结果 |
|---|---|
| Pipeline 默认隔离回归 | 467 PASS |
| Console，包含全部 JS 桥接/权限/迁移/HTTP | 373 PASS |
| Shared Authority release | 12 PASS |
| FRP Guard **offline**（仅正式回归、不操作 FRP/云） | 30 PASS |
| 验证器自身回归 | 24 PASS |
| Console JS 实际文件清单 | 16 个文件，Node exit 0；不额外重复计入总数 |
| Python compile | 208 个 Git 跟踪及非忽略源文件，纯编译、不执行；PASS |
| `git diff --check` | PASS |
| Migration / Schema | 正式回归中填充备份升级、重复启动、事务回滚、并发初始化及 Authority-only schema 检查 PASS；本轮没有新增迁移 |
| 历史 Review / Persona / Constraint 兼容 | 正式回归 PASS；真实既有保护 SHA 逐文件一致 |

默认 live opt-in 属于未执行层，不计入 906，也不称为已跳过后通过。
真实模型/付费 Provider、E3、实体 iPhone 软键盘、4090/生产验收均未执行。
实际浏览器 Gate 是本轮虚构合成样本上的正式应用与 Authority 操作，独立于 pytest
计数；合成期望结果不证明真实 DeepSeek 提取能力。

收尾补充：原生 SPA 浏览器返回也检查未保存的审核修改；实际浏览器出现 confirm，
取消保留与确认离开的路由分支由真实 handler 回归验证。浏览器 dialog handle 在下一
工具调用时已关闭，未把这次尝试算作真实浏览器取消分支 PASS。此验证不写 Human
Review，新增的虚构 UX-BACK 记录保留待审核。同时修正概览边框引用，复用已有
`--line` 颜色变量。针对这个最终代码状态的关闭复核记录另存新证据目录
`final-verification.json`（实际运行 ID / summary 路径 / 结果）；不使用前述结果替代
收尾代码的复核。

最终 Gate：**UX-2 PASS / UX-3 PASS / UX-4 OFFLINE_BROWSER_PASS / UX-5 PASS**。
历史 1256 个 Canonical JSON、旧数据库摘要、主工作区与 HEAD/branch 均保护通过。
仍有真实模型和生产验收边界，但没有本轮已知阻塞回归。

`CS_E2_UX_REVIEW_BY_EXCEPTION_READY_FOR_PRODUCT_REVIEW`

STOP，交回 ChatGPT 独立 Product / Architecture Review，不进入 E3，不提交、不部署。
