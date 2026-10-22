# Product Decision Register — R3

Delivery: CREATION_BATCH_UX_1
Plan Revision: 3（本轮DR-01/02产品确认与设计交接；未获独立Plan批准）
Status: Draft / Pending Independent Review / Plan Freeze Not Authorized / Implementation Not Authorized
Baseline: Revision 1 / Approved / Frozen
Baseline SHA-256: 13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3
Previous independently reviewed PLAN SHA-256: fb845c980df7feb15e81e543a5bbcb5543ee917a8c82f0bdda6212e7c58c4a1c
Prior delivered Plan R2 SHA-256: 2a7081e10340cdb680d72f96e59f3357924529e29546ad233c6bf218ed4f5dbb
Working Plan input SHA-256: 0fd6aeff228cfc5f90a8e09ac175fb4c47a261319de6c63bd2037767d26765cd

依据：[唯一Baseline](BASELINE.md)、[真实批准链BR-02](BASELINE_APPROVAL_RECORD.md)、[独立Plan裁决来源](PLAN_INDEPENDENT_REVIEW_RECORD.md)。已批准产品规则（含本轮DR-01/02）、当前机器事实与待批Native合同分开记录。所有新增Schema/API/状态均为PROPOSED / NOT IMPLEMENTED；本轮不写功能代码或Native业务Receipt。


## 正式产品规则与推荐的分层

| 规则 | 内容 | 真实状态 | 来源 | AC | Gate |
|---|---|---|---|---|---|
| P01 | D-P01三类语义/来源/人物/禁称/结构/判据 | FOUNDER_APPROVED | Baseline D-P01；实际用户选择 | AC-08 | G-01 G-03 |
| P02 | 阶段一/二合计推荐后明确分配；初始未分配，无5:5/15:15默认 | FOUNDER_APPROVED | Baseline D-P02方案A | AC-09 | G-01 G-07 |
| P03 | Stage News默认Novel，Repurpose另选，不冒充新增语义配额 | FOUNDER_APPROVED | Baseline D-P03 | AC-10 | G-01 G-08 |
| P04 | Novel/Repurpose视频/语义/Presentation区分，原Human和历史保留 | FOUNDER_APPROVED / CODE_CONSTRAINT | Baseline及原Native Owner | AC-04 AC-10 | G-03 G-04 G-05 |
| P05 | News一份＋Mix一份汇总；零合法行不出空文件；不能退文件列表或按三Style分别出正式文件 | USER_CONFIRMED_PRODUCT_CLARIFICATION | 本次PR-2；细化原两模板交付目标，不改Baseline字节 | AC-07 AC-08 AC-10 | G-05 G-09 |
| P06 | 批次允许多个待审News、逐次安全Dispatch、之后集中人核 | FOUNDER_APPROVED_PRODUCT / NATIVE_APPROVAL_PENDING | 本轮DR-02明确答复；仅产品交互获批，A03仍独立 | AC-07 | G-01 G-03 G-04 |
| P07 | 总目标量为0时阻断启动 | FOUNDER_APPROVED_PRODUCT | 本轮DR-01明确答复 | AC-07 AC-09 | G-01 |
| P08 | 稳定期初始显示1个四天周期，但用户必须明确确认N，绝无自动无限循环 | FOUNDER_APPROVED_PRODUCT | 本轮DR-01；有限明确确认同时保留Baseline原规则 | AC-07 AC-09 | G-01 G-12 |
| P09 | 目标时长仅建议；没有真实成片时长保证 | CURRENT_CODE_CONSTRAINT / PROPOSED_PRODUCT_RULE | Baseline CT28当前约束；PR-4建议作为产品规则，非独立Founder批准；无数值默认 | AC-05 AC-07 | G-01 |
| P10 | 用户可明确结束部分批次，保留合法成果/差额；unknown不能被结束按钮消除 | FOUNDER_APPROVED_PRODUCT / NATIVE_SAFETY_CONSTRAINT | 本轮DR-01/02；结束不撤回在途、不消除unknown，合法成果按原Gate交付 | AC-07 AC-10 | G-01 G-04 G-05 |
| P11 | 不足量只提出调整，不静默替换类型/机会或制造事实 | PRESERVED_CONSTRAINT | Baseline事实/资格边界；PR-4重申 | AC-03 AC-07 AC-08 AC-10 | G-03 G-04 |
| P12 | Windows桌面Chromium、Android Chrome、iOS Safari为真实三端UAT建议；版本/设备待确认 | PROPOSED_TEST_SCOPE / NOT_VALIDATED | 本次PR-4；无手机截图PASS | AC-05 AC-07 | G-01 G-12 |


以上状态以实际来源为准，不把本次ChatGPT建议或本agent静态可行性分析升级为Founder或Native Human批准。D-P01～03不再待选；原候选表不构成当前产品Authority，完整定义归Baseline。

P05是本次用户对既有“News/Mix两种最新模板按类型交付”的明确细化：最多两份正式XLSX，同一Mix文件包含persona/story/conversion行，准确Style身份由不可变row manifest绑定，不增模板列。Novel/Repurpose同归News汇总，但各自source和semantic计数分开。部分合法交付只列实际行，同时展示原目标、已交付、待审、失败、拒绝、unknown和差额；不能把总目标改成已交付数来显示全部完成。

## 已关闭的产品决定与剩余工程义务

- D-A01产品体验已确认：采用B，一次确认、逐次安全生成、生成告一段落后集中核对。A03受限Admission、来源预留、memory与撤回合同仍待原Owner独立审查，不能回退A或删active check。
- D-A02：News/Mix汇总目标保持。原Export/Delivery A04机器合同仍待批准；不能以文件列表替代。
- D-A03：原Mix Owner审查同Style K、Slot/Concept/content及部分审核映射；旧20输入边界不是新Style能力。
- D-U01已关闭：P07/P08/P10按本轮实际用户答复确定，不再请求重复批准；精确动作归DESIGN_OPTIONS的已确认边界。
- D-U02：具体真实设备/浏览器版本与UAT责任由Planning在依赖验证前落实；属于后续验证义务，不再作为未定产品目标阻断设计。

## 定义的验收输入（尚未执行）

| 类型 | 合法虚构样本方向 | 必须失败的表现 | 身份要求 |
|---|---|---|---|
| persona | 已批Speaker解释其实际流程/判断，有具体fact引用 | 编十年经历/无权限背书/观点变保证 | Native Mix＋persona版本贯穿到原Human与Mix汇总row |
| story | 已批事件主体、行动与已知结果，缺失不编结局 | Case研究冒充亲历/虚构客户对白、转折、效果 | 相同逻辑Slot的Concept/content/修订谱系可追踪 |
| conversion | 已批服务价值、适用需求/价格条件和获准CTA | 虚假优惠/收益承诺/省略条件/未经批联系方式 | CTA规则必须由原Native消费者验证，不只是文末加购买号召 |

这些是后续隔离用例方向，非真实客户事实、素材、正式Pattern批准或模型效果PASS。新Style机器合同、Native消费者、Pattern/Compatibility/release和原人审均未因D-P01定义获批而实施。

## 本轮真实产品确认来源与范围

用户先要求“解决当前的阻断”，随后对完整DR-01问题答复“采用这组规则（推荐）”，对完整DR-02问题答复“采用候选B及上述边界（推荐）”。原问题、准确答案与可归属的questionItemId由有权控制记录者留存在[PRODUCT_APPROVAL_SOURCE.json](../../../.local/evidence/creation-batch-ux1-design-resolution-r3-20261022/evidence/PRODUCT_APPROVAL_SOURCE.json)，不是从Plan标签推断批准。

批准只覆盖P06/P07/P08/P10的产品交互。D-P01～03、News/Mix两份汇总、Human/事实/历史边界保持；P09仍是已有机器约束及产品建议，不伪造额外Founder决定。没有授予新Native资格、审批权限、Plan Freeze、执行或生产许可。

这是Baseline已明确留给设计的细节确定，不替换Goal/User Outcome、Non-goals、Key Decisions、Preserved Constraints或AC；Baseline Revision1及1384字节保持不变，无新增/重编号AC。原R2的DR-01/02非PASS结果继续作为历史，不改写为当时已通过。
