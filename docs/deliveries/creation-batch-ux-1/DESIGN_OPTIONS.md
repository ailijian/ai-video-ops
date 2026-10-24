# Design Options — R3收敛方向

Delivery: CREATION_BATCH_UX_1
Plan Revision: 3（本轮DR-01/02产品确认与设计交接；未获独立Plan批准）
Status: Draft / Pending Independent Review / Plan Freeze Not Authorized / Implementation Not Authorized
Baseline: Revision 1 / Approved / Frozen
Baseline SHA-256: 13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3
Previous independently reviewed PLAN SHA-256: fb845c980df7feb15e81e543a5bbcb5543ee917a8c82f0bdda6212e7c58c4a1c
Prior delivered Plan R2 SHA-256: 2a7081e10340cdb680d72f96e59f3357924529e29546ad233c6bf218ed4f5dbb
Working Plan input SHA-256: 0fd6aeff228cfc5f90a8e09ac175fb4c47a261319de6c63bd2037767d26765cd

依据：[唯一Baseline](BASELINE.md)、[真实批准链BR-02](BASELINE_APPROVAL_RECORD.md)、[独立Plan裁决来源](PLAN_INDEPENDENT_REVIEW_RECORD.md)。已批准产品规则（含本轮DR-01/02）、当前机器事实与待批Native合同分开记录。所有新增Schema/API/状态均为PROPOSED / NOT IMPLEMENTED；本轮不写功能代码或Native业务Receipt。


## 当前目标与方案状态

已确定的配置语义归Baseline：客户进入独立配置、继承已批资料、阶段/自由组合、人设故事初始未分配、News默认Novel、有限周期明确选择、真实Human Gates。PR-2明确最多两份分类汇总文件。本文件归一本轮明确批准的体验细节；批准来源归PRODUCT_DECISION_REGISTER，不替代原Native或冻结Baseline。

| ID | 本次收敛 | 状态与禁止替代 |
|---|---|---|
| O-STYLE | C01/C02使三Style在原Native链真实消费并保留身份 | 业务定义已批，机器策略/消费者仍待实施；只贴label不成立 |
| O-SPLIT | D-P02方案A | Founder已批，不再提供B/C为当前默认候选 |
| O-NEWS | D-P03 Novel默认＋显式另选Repurpose | Founder已批，无后台fallback |
| O-ACTIVE B | 一次确认有限批次，原Owner受限Admission，安全逐次Dispatch，可累积多个待审Native News，再集中人工核对 | Founder已明确采用B及审核边界；A03/来源预留的机器批准仍待原Owner。多待审不等于模型无限并发；不默认回退A |
| O-ACTIVE A | 现有同Business/profile active限制 | 仅当前事实/不可行时对照；本R3不把逐条人审作为交付降级方案 |
| O-MIX | 同Style子组K↔K逻辑Slot，原Concept/content映射和追加修订谱系 | D-A03需原Owner合同，K受实际资格/容量；同Request多Style未纳入候选 |
| O-EXPORT | News一份、Mix一份；零合法行不出该文件；Style在Mix row manifest，Novel/Repurpose在News row manifest | 固定产品目标；原Owner A04多parent Delta仍待批。文件列表/按三Style三份正式文件/第二Exporter均不作为fallback |
| O-STATE | Native refs＋协调事件＋只读状态投影 | 没有第二Approval、生成真相或Ledger；原Human确认与Task完成分开 |
| O-QUEUE | 复用原单进程/持久Task与GPU guard；安全逐次生成的产品方向已批，具体预算/调度合同仍是提案 | 并发1是隔离候选调度策略，非真实provider限额或已批生产参数 |

## 已确认的配置、候选B与部分结束边界（不授予Native权限）

以下产品语义已由本轮DR-01/02明确确认；所有实现/新机器枚举仍NOT IMPLEMENTED。

| 场景（展示语义，非新Native枚举） | 已确认的行为与可用动作 | 保留边界 |
|---|---|---|
| 配置 | 总量为0不启动；人设/故事未分配不等于0；用户明确填写、确认实际总量 | 不创建无意义Request/Task；各单项仍允许0，不默认均分 |
| 稳定期 | 初始显示1个四天周期，确认页明确显示本次有限N和实际目标 | 初显不是授权；不自动重复周期，不虚构周期上限/产能 |
| 生成中 | 一次确认有限批次后安全逐次生成，积累待审；可看进度/合法成果预览，按原权限暂停或结束后续工作 | 生成完成不等于审核通过；多个待审不批准无限并发 |
| 生成告一段落 | 队列本轮生成结束、明确失败或用户暂停/结束后，集中核对准确Native版本；有在途/未知项须显式列出 | 不把“告一段落”命名为全部完成；审核仍逐项服从原Owner的当前安全门 |
| 明确失败或拒绝 | 保留合法成果、原目标和准确差额，可继续处理其余合法内容 | 不自动补量、换类型、改来源或制造事实 |
| 在途/未知结果 | 不撤回已发调用，不自动重发；未知项不能批准/导出，提供原生恢复入口和阻断原因 | 原Owner判断受影响的安全scope；无影响成果仅在原Gate允许时审核/发布确认/交付。不能默认全部封死，也不能绕过共享memory fence |
| 结束部分完成批次 | 停止未派发工作，保留已有成果、在途/未知项和目标差额；合法成果仍可继续原生审核与交付 | 不取消已经发生的模型调用，不清空unknown，不把目标改成实际数来显示全部完成；不暗中补生产 |
| 集中审核与交付 | 各项准确source/version，原内容Human与Publish Copy确认分别完成；最终News/Mix各一份，零合法行不出空文件 | 未知/未批准/失效项不入文件；部分交付scope与差额明确，原Receipt/Closure/Ledger一次性 |

“结束后续创作”和每项Native的真实执行、审核、交付状态分开展示；结束意图不能把在途/未知项强写成终态。能否解除某项阻断由其原Owner证据决定，操作按钮不创造事实。修改/恢复/再次明确尝试继续使用原source、actor、权限和REC-01费用/范围确认；当前确认不授予自动重试许可。

暂停或结束后，原有合法成果的只读预览/审核/交付按现有权限继续。未来要补剩余目标须另有明确创作确认及原资格检查，不能自动补齐。客户、事实、人物和历史不因结束被删除。

## 不能隐藏的产品与工程接缝

1. 候选B须先有原Request/Quality Owner受限Admission、唯一机会预留、generation-result与memory有效性合同。原active check保持legacy路径；不能让Console直接绕过。若当前规则不能安全支持，显示合同阻断并升级，不悄悄逐条人审。
2. 多个未审Request必须仍由其原Native owner负责生成/审核/撤回。原Owner需审查生成阶段与Ledger写入时序，避免已发尝试因别项导出变memory后被静默重绑。详细候选见C04～06；它不是已获批算法。
3. 按Profile汇总在原Delivery委托边界内完成；原单Request文件合法不自动证明汇总合法。每行source/确认/父Receipt/Closure/anchor均重验；单文件独占原子发布，两文件集合用Prepared/Completion完整性，不宣称跨文件原子事务。

## 真实设备与可实施设计输入

建议Windows桌面Chromium、Android Chrome、iOS Safari三真实环境，记录具体版本/设备/视口、权限角色与source状态。配置、确认、待审/失败/unknown、审核编辑/拒绝、Publish确认、两文件/零文件/部分下载、重登恢复均需真实旅程证据。目标截图只属Founder Visual Reference，未取得原图SHA不声称已核验；本轮没有手机/浏览器UAT。

沿用仓库Productized UI的工程词隐藏、单一主操作、响应式规则，以及Internal Console原Human/数据边界；NAV1客户导航覆盖全局入口旧规则。缺失图稿/token可在语义确定后作为实施前义务，不凭缺Figma阻断；P06/P07/P08/P10的关键交互已明确；余下状态/组件细化须忠实于上表与原Owner，不能引入新的产品语义。

本轮Design Readiness独立于文档标签对真实产品来源和当前输入复核；结果及输入关联由有权记录者留存新证据目录。原非PASS保留历史；设计就绪不等于Native审批、Preflight通过或实施许可。
