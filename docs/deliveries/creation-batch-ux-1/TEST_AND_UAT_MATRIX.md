# Tests and UAT — R5

Delivery: CREATION_BATCH_UX_1
Plan Revision: 5（开工准备细化；工程范围与原生资格均不代签）
Status: Draft / Pending Independent Review / Plan Freeze Not Authorized / Implementation Not Authorized
Baseline: Revision 1 / Approved / Frozen
Baseline SHA-256: 13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3
Previous independently reviewed PLAN SHA-256: fb845c980df7feb15e81e543a5bbcb5543ee917a8c82f0bdda6212e7c58c4a1c
Prior Preflight input Plan R3 SHA-256: 8d7e82a3abf9e0eb1b5bfb993192640062fddedab641695df7524651f928ddf7
Input Plan R4 SHA-256: f9cea03c7c160f586d8d3dda24515ca5400763056f4388b5c17931bf3b439e8e
Prior delivered Plan R2 SHA-256: 2a7081e10340cdb680d72f96e59f3357924529e29546ad233c6bf218ed4f5dbb
Historical R2 working-input SHA-256: 0fd6aeff228cfc5f90a8e09ac175fb4c47a261319de6c63bd2037767d26765cd

依据：[唯一Baseline](BASELINE.md)、[真实批准链BR-02](BASELINE_APPROVAL_RECORD.md)、[独立Plan裁决来源](PLAN_INDEPENDENT_REVIEW_RECORD.md)。已批准产品规则（含已确认DR-01/02）、当前机器事实与待批Native合同分开记录。所有新增Schema/API/状态均为PROPOSED / NOT IMPLEMENTED；本轮不写功能代码或Native业务Receipt。


| ID | 场景 | 阶段 | 合同 | Gate | AC | 所需实际证据 | 状态 |
|---|---|---|---|---|---|---|---|
| TC01 | PR-0身份/批准 | B1 B4 | C03 | G-00 | AC-01 AC-02 AC-06 | 全Baseline/3439→1384差异、真实用户选择/AC来源、当前SHA/历史包及工作区保护 | 本轮仅DOC_CHECK；不等于功能通过 |
| TC02 | 三Style/消费者 | B1 | C01 C02 | G-02 G-03 G-07 | AC-03 AC-08 | 三类合法事实和Speaker；原Native链消费确切Style，禁称/无资格拒绝，legacy reader不忽略新字段 | NOT_RUN |
| TC03 | 阶段/自由组合 | B1 B4 | C03 | G-01 G-07 G-10 G-11 | AC-07 AC-09 | P/S未分配不启动、显式分配10/30，可0/可改实际数；无5:5/15:15，修改失效旧preview | NOT_RUN |
| TC04 | 有限N/建议规则 | B1 B4 | C03 | G-01 G-12 | AC-07 AC-09 | 按本轮已确认P07/P08/P10验证总0拒绝、初显1仍明确确认、8N有限、时长仅建议、部分结束不completed | NOT_RUN；产品规则已确认 |
| TC05 | Mix K映射/部分审核 | B1 B2 B3 | C02 C04 C07 | G-02 G-07 G-08 G-09 | AC-03 AC-07 AC-08 AC-09 | 同Style K=2稳定Slot↔finalConcept/content；修订source版本追加、1通过1拒绝；G<K保留差额 | NOT_RUN |
| TC06 | 候选B受限admission | B2 | C04 | G-03 G-08 | AC-04 AC-07 AC-10 | 至少2独立合法Novel机会，多个待审Request合法存在；Dispatch预算实际受限；不同Batch/legacy active/越权不给例外 | NOT_RUN |
| TC07 | 预留与跨Request去重 | B2 | C04 C05 | G-03 G-04 G-08 | AC-04 AC-07 AC-10 | 同机会/语义跨Batch/Profile竞争只一Owner占用；未审也不能重复；Repurpose原source semantic0；不足不换源 | NOT_RUN |
| TC08 | memory/phase变动 | B2 B3 | C05 C06 | G-04 G-08 | AC-04 AC-07 | 生成epoch内外Ledger变动、review/export时序，已发intent fence保持；缺合同阻断，不重绑；仅合法Native closure消费 | NOT_RUN |
| TC09 | REC-01/初次失败/late worker | B2 | C04 C05 C06 | G-04 G-08 | AC-04 AC-05 AC-07 | 每provider阶段dispatch前后/保存response/timeout/late；unknown远端计数不增加、机会不超时释放；C3-05仅原范围 | NOT_RUN |
| TC10 | 重登/双击/取消/撤回 | B1 B2 B3 | C03 C04 C05 C06 C07 | G-04 G-07 G-08 G-09 | AC-04 AC-07 AC-09 | 同key同payload复用Request/Task，stale lease阻断；权限/源/Pattern/Compatibility/release撤回新写入fail closed；结束不抹unknown | NOT_RUN |
| TC11 | 集中人审/Publish | B3 | C07 | G-05 G-09 | AC-04 AC-07 AC-08 | 原Mix item/Novel Beat/Repurpose Slot scope，逐source/actor决定；部分提交恢复只补缺项；≤5 targets/call和exact draft独立确认 | NOT_RUN |
| TC12 | 两份汇总/身份/零类型 | B3 B4 | C08 | G-05 G-09 G-13 | AC-04 AC-07 AC-08 AC-10 | 最多News/Mix各一，Mix三Style row manifest，News两来源；零合法行无空文件；partial范围与差额明确，跨Business拒绝 | NOT_RUN |
| TC13 | 父证据/文件完整性 | B3 | C07 C08 | G-05 G-09 | AC-04 AC-07 AC-08 AC-10 | 逐行Native Approved/Publish confirmation/parent Receipt Completion/Closure/anchor；模板SHA、Mix5/News4 row4/5、OOXML/CRC/实际XLSX和manifest SHA | NOT_RUN |
| TC14 | 汇总中断/重放 | B3 | C08 | G-05 G-09 | AC-04 AC-07 AC-10 | 每文件prepared/发布/receipt及Set completion前后崩溃；不宣称跨文件原子事务；completed replay零新Task/Receipt/Ledger/delta | NOT_RUN |
| TC15 | 2～5真实接缝 | B2 B3 | C01 C02 C03 C04 C05 C06 C07 C08 | G-08 G-09 | AC-04 AC-05 AC-07 AC-08 AC-09 AC-10 | 合法隔离Native owner＋synthetic transport；需建立fixture/runner，准确Request/Slot/content/调用次数/资源及一代表失败，非40行mock | NOT_RUN |
| TC16 | 20→40→有限N容量 | B4 | C02 C03 C04 C05 C06 C08 | G-10 G-11 G-12 | AC-05 AC-07 AC-09 AC-10 | 按每级实际目标分配、合法来源、失败/待审/unknown不误报整体完成；行数和语义对账、重登、合成call/resource观测 | NOT_RUN / UNKNOWN capacity |
| TC17 | 三端真实旅程 | B4 | C03 C04 C07 C08 | G-12 G-13 | AC-05 AC-07 AC-09 AC-10 | 约定真实桌面Chromium/AndroidChrome/iOSSafari版本与设备；配置→确认→待审/失败恢复→审核Publish→两文件下载/历史/重登 | NOT_RUN / NOT_VALIDATED |
| TC18 | 最终全仓/历史保护 | B4 | C01 C02 C03 C04 C05 C06 C07 C08 | G-13 | AC-01 AC-02 AC-03 AC-04 AC-05 AC-06 AC-07 AC-08 AC-09 AC-10 | 最终候选python tools/verify.py完整隔离回归；原Canonical/Approval/Receipt/Closure/Ledger/anchor及其他工作树精确保护，独立验证与Founder操作 | NOT_RUN |


## 顺序、资源与证据范围

只在原Owner合同/合法隔离资格和对应阶段执行授权齐备后建真实接缝。先单Request的Style→原Human/Publish/Native交付成功与一次非法输入阻断；再2～5中的2待审Novel/同Style K=2及代表性故障；G-08/09后才20→40→明确N。源容量不足就是shortfall，不补造事实、重复机会或自动改Repurpose。

只替换外部provider transport，不stub Human/Compatibility/release、原source/memory/closure validators或Ledger。实际保存代码Commit和dirty内容身份、catalog/schema/fixture/release/config、命令、原结果、调用次数（含explicit retries/unknown）、资源峰值及观测耗时；未实测值UNKNOWN。合成吞吐/语义样本不等于真实模型质量、成本、API限额或生产承诺。

源撤回和Actor变更覆盖每个实际entry，不能只测UI按钮；完成/部分/拒绝/未知数量应独立可对账。20/40是目标规模，不是并发等级。当前原输入上限20不证明新Style K，NR05 price_offer范围也不证明某客户可提供10个Novel机会。

## 比例、规则和设备的真实状态

D-P01～03已有Founder来源；TC03/TC12不得继续把未分配和Novel默认当待选。TC04的总0/初始1仍明确确认/部分结束具体动作已由已确认DR-01/02确认。未知项及共享安全范围受原Gate限制，其他合法成果按原Gate处理；未来测试须验证这些规则，而不是重新把它们当待选或签未运行验收。设备建议需D-U02约定，记录真实版本、设备和旅程；缺端保持NOT_VALIDATED，任何截图/viewport自检不能替代三端UAT。

## 原验证路由与最终关闭

阶段聚焦/受影响验证使用仓库既有package和`python tools/verify.py --mode affected --base <实际阶段起点ref>`，占位符必须在执行时换成真实可恢复原比较边界；新测试runner未建立时明确由阶段Owner先建立，不伪造命令。

最终候选执行实际存在的`python tools/verify.py`完整隔离回归；package-only/affected和历史PASS不代替。先依据观测失败聚焦修复，再在最终状态重跑要求的完整路由。临时产物限.verify，证据限.local，普通mutation tests不得指向live Authority。新异步CI尚未选择，若采用需明确真实workflow和blocking性质；迟到真实blocker重开受影响范围。

本轮进行TC01范围文档/身份、合同候选/环境检查；继承R4已有renderer两Profile各2行组件校验；不执行TC02～18新功能/模型/浏览器UAT或全仓回归。组件结果不是TC12～14新multi-parent业务验证。原BL-0测试仅按其准确Checkpoint与覆盖范围继承，不签新Style/Batch/两文件能力通过。News仅已有合法资格隔离范围；G-14生产/4090/真实模型独立且本轮禁止。

## 本次技术审查补充的证据边界

- NCR-03 / TC08、TC11：在原memory有效时先完成相关生成与Human，之后Native逐项交付；并发其他Ledger写入应阻断受影响open attempt，不得重绑或自动重发；已完成draft/Native历史仍由原reader验证。未通过这条真实接缝不得扩大调度。
- NCR-04 / TC10：Batch结束只停未派发；旧Native disposition有实际Human/Authority条件，禁止循环abandon假装结束未知项。Novel仍是4～8 Beat一个视频，不能把审核剩3 Beat当合法partial视频。
- NCR-07 / TC06～10：真实Windows父子进程锁责任/短CAS/跨profile和legacy预留排斥要验证；不能仅以in-process mock或regex证明。
- NCR-06 / TC12～14：继承R4的RENDERER_PROBE仅两Profile各2行、重复字节不变/CRC及wrong-row拒绝，0模型/Request/Task/DB/Approval/Ledger；新multi-parent Receipt/父链/Set恢复仍NOT_RUN。

本轮未为写Plan跑交付suite。B1/B2/B3先建立缺失新runner和最薄真实接缝，命令存在后记录；B4在最终候选执行原完整tools/verify.py，所有已要求证据范围不缩减。Planning PASS不代表任何未来测试已通过。


## R5实现前资产与可执行验证安排

已有代码/runner命令和缺失能力分开：`python tools/verify.py --list`本轮实际成功解析pipeline/console/authority-release/frp-guard/verification；只读选择不执行suite。Pipeline声明11项精确依赖、Console声明dev范围、Python3.12/Node24/PowerShell5.1/Git匹配；没有安装新依赖，环境报告不证明回归通过。

B1先从原test_novel_news_v1的Native完整路径、generation_request_handoff的锁/资格反例、Console release-source拒绝能力构建新Style fixture/runner。现有fake_authorities/局部mock仅为其原覆盖，不能借用来宣布新资格通过。只合成远端transport，原Fact/Speaker/Pattern/Compatibility/Human/Publish/Export/Closure/Ledger验证参与。C01～08 JSON只做文档解析/字段与引用检查，不宣称完整Schema或Native接受。

| 可操作检查 | 时点/责任 | 观察与拒绝标准 |
|---|---|---|
| 配置和开始 | B1/获授权Codex＋Founder操作 | P/S未填、总0、stale preview、same key different payload拒绝；默认Novel/显式Repurpose/有限N/实际目标明确 |
| 单Style薄切片 | B1-P1/原Native实现与独立Reviewer | Style规则实际进入plan/prompt/validator/review/export；一合法成功＋一无事实/非法CTA或unknown version拒绝，先审后扩 |
| 状态和结束 | B2/B3/Native恢复Owner | 每Slot唯一phase统计；Review/Delivery是独立维度；unknown不终态化/不重发；部分结束保留目标与差额 |
| UI/键盘/错误 | B1/B3/前端与操作验证 | 既有组件/安全消息；label/错误关联、首错焦点、值保留、键盘可达；390/430/1440/1792无横溢和多层sticky，截图不代替UAT |
| 真实三端 | B4/Founder约定设备＋验证方 | Windows Chromium、Android Chrome、iOS Safari实际版本/设备/角色与完整旅程；未取得端NOT_VALIDATED，不提前填版本 |
| 多parent文件 | B3/原Delivery Owner | Intent仅输入SHA，Prepared绑定输出SHA；严格父链/行身份、全部关键故障窗与Set完整性；重放不多Task/Receipt/Ledger |

三Style正反样本是未来判据，无真实客户事实/模型输出，不签质量验收。A03首轮2～5建议上限与预算需人批准后生效；20/40之前原Owner据实际映射和小容量证据确认新scope。没有新增正式TC/AC/Gate编号，也没有运行TC02～18或全仓suite。
