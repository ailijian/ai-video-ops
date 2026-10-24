# 最小实施路线、审查Gate与隔离预检设计

全部新设计为PROPOSED / NOT_EXECUTION_AUTHORIZATION。本包只为架构审查；不冻结可执行Plan，不请求或代签任何人审回执。

## I1 / I2 / I3

| 阶段 | 建议范围 | 进入条件 | 安全停止点及退出证据 |
|---|---|---|---|
| I1 Excel上传/严格校验/预览 | 只读解析8表身份、正式21/10/9字段、三模式、类型建议与关联/重复/风险，逐行错误；0正式Case/Task | B0独立审查接受；原Intake/Source/Security Owner冻结IB-01解析策略、文件预算、未知字段与枚举规则，Founder明确I1实施范围 | 预览可丢弃，原附件不变；失败ZIP/身份整文件拒绝。无解析模型、候选保存、批准或共享写入 |
| I2 保存Import Candidate | 原Intake委托下稳定Batch/Row/Intent、manual-notes/rights/source refs、私有归属及幂等恢复 | IB-01＋ME-01候选保存范围获原Owner批准；SI-01明确本地/未知平台待核来源；真实上传manifest协议与独立权限检查通过；Founder明确I2 | 保存未核Candidate后可停止，不建Approved Case；原URL路径只有另经明确解析授权才能入原Task队列。未知结果查原意图，不重发 |
| I3 正式核验/类型/共享 | 合法源媒体原生解析、Evidence Review、CC-01类型确认、Human Quality、Case批准及CC-02安全共享 | 原解析来源资格成立；新内容类型/共享版本分别Owner批准；原Reviewer当前grant；真实模型/生产仍独立Gate | 可停在待补证/待审/仅批准未共享；联合按钮仍有两个独立Authority Receipt；历史永不重写 |

不要求先完成CC-01/02才研发纯预览的I1，但I1不得显示“已确认类型”或承诺共享；不以I1成功自动放行I2/I3。正式新增contract消费者各先最小正负测试再接UI，候选/Schema/版本适用范围须独立审查。

## 进入实施前的具体审查对象

| Gate | 当前状态 | 原Owner决定对象 |
|---|---|---|
| G-TEMPLATE | FOUNDER_ACCEPTED；字节核验PASS | 产品V0.3及既有SHA，不重复要求Founder批准 |
| G-IMPORT-01 | OPEN / PROPOSED | IB-01 idempotent Row intent、保存和解析分离、存储/失败恢复/选中行语义 |
| G-SOURCE-01 | OPEN / PROPOSED | 文件-only/其它平台如何保存待核来源，以及原Case来源仍不兼容时必须停止的位置 |
| G-MANUAL-01 | OPEN / PROPOSED | ME-01手工说明等级、来源/逐字段SHA及原Evidence Review接缝，禁止伪ASR/Frame/Shot/Proof |
| G-TYPE-01 | OPEN / BLOCKS formal business type | CC-01词典/Reviewer确认；原普通operator-label权限不得自动升级 |
| G-DISPLAY-01 | OPEN / BLOCKS typed Shared publication | CC-02新版本及原Case批准/共享两份独立Receipt、withdraw/current/source绑定 |
| G-SECURITY-01 | OPEN / PROPOSED | XLSX解析库/安全预算/外部关系策略/上传隔离；Session/CSRF/Reviewer/私有权限沿原Owner |
| G-LEXICAL-01 | OPEN / PROPOSED | observation_basis下拉原文与JSON解释词的规范化别名；行业建议标签差异保留原文，不能静默改义 |
| G-EXECUTION | NOT_AUTHORIZED | ChatGPT架构审查后的精确I1/I2/I3实施授权、Design/Planning流程适用范围 |

建议局部文件/行数等阈值仅在IMPORT_BATCH_CONTRACT_DELTA中提出，不能从XLSX预留行或当前测试数量推导生产吞吐/成本。真实费用、延迟、限流、所有平台能力保持UNKNOWN。

## 预检和测试

ISOLATED_TEST_INPUTS.json准备16条虚构Case行以及14组包/权限/重放等变体，均DESIGN_ONLY_NOT_RUN；不生成虚构“真实上传回执”。覆盖六种类型标签、other漏说明、profile冲突、纯文字、重复原视频、缺媒体、DEMO复制、连续分段与unknown许可；其后完整安全/跨用户/恢复矩阵逐项执行。示例工作表业务读取为零，同时必须在安全扫描中发现任何恶意对象。

I1测试：原模板全空=0候选、三模式必填、H/I/J严格顺序和key映射、所有禁用表/DEMO、ZIP/XML/公式/宏/外链、异常值/跨表、真实来源resolver（离线网络注入）与逐行UI错误；不通过Excel下拉代替服务端校验。

I2测试：上传者保存自己的Candidate和私有查询；无Session/CSRF、跨用户、未知字段/版本、重名媒体/变SHA/过期/已消费拒绝；相同operation/intent重放、不同输入冲突、每个持久化边界故障与重登恢复；部分成功必须显式选择且不创建重复Case/Task。保存后统计模型调用必须0。

I3测试：当前指定Reviewer真实授权、撤回后旧context失效，类型冲突逐项处理；原Media/ASR/Visual/Shot/Privacy/Claims/Proof/Final Quality完整验证；Case Approval Receipt与Shared Display Receipt分开执行来源与权限检查。错误/未知项不能批准。Shared白名单与类型版本严格读取、撤回和replay无重复。旧Case/Pattern/Compatibility/Business/Ledger SHA保护。

模型边界默认只用全虚构合成返回。成功解析演示不代表真实视频ASR/OCR/语义质量通过；真实付费模型另批。媒体容器测试应通过现有合法fixture或本地生成的合成视频经过真实上传Reader；文件名存在声明不能当作证据。

本轮已实际执行的是原有Case/Novel Owner的聚焦隔离回归、附件ZIP/字段核验与现有UAT只读Novel探针，见evidence/EXISTING_OWNER_TEST_RESULTS.json；它们验证复用边界，不是Excel导入测试。新增Adapter/候选保存/正式类型均未实施，测试状态仍NOT_RUN。全仓与真实Founder UX验收待对应阶段适用Gate。

后续建议提交边界：I1只读Adapter/UI；I2候选Schema/Owner及写入接缝；I3类型与共享分别版本化接缝。各边界独立Code Review及受影响回归后，按授权提交，不一次混入Batch工作树。停止/回退只撤新Adapter或新指针，不删历史Candidate、Case、Receipt、Ledger；已保存的明确Human决定依原恢复合同保留。
