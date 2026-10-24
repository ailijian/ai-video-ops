# BR-02 — 既有Baseline批准链补证

这是本轮按PR-0授权记录的既有批准来源，不是新批准、Native业务Receipt或重新签署历史。唯一当前完整内容见 [BASELINE.md](BASELINE.md)，Status Approved / Revision 1，实际SHA `13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3`。本轮不改其任何字节。

## 可归属的用户来源

1. 本对话用户明确调用delivery-baseline并要求“冻结baseline”。
2. 本对话随后实际回答：D-P01“采用 D-P01 候选定义”；D-P02“合计推荐，代理商明确分配（方案A）”；D-P03“推荐数量默认 Novel；Repurpose 显式另选”。完整问题/答案保留在 [JSON记录](BASELINE_APPROVAL_RECORD.json) 和审查包 `evidence/APPROVAL_SOURCE_EXCERPTS.json`。
3. 本agent依持续冻结指令与上述明确内容补充，执行既有Draft首次批准并返回冻结后SHA；不是由Plan给Baseline签批准，也不是只根据Approved标签或Agent报告推断Founder决策。

没有独立外部签名/报告URL或消息时间戳可供核验，记录只归属本对话真实消息，不伪造它们。后续审查可独立取得用户原消息、前后完整输入和diff。本记录是现在补齐，不声称之前已存在BR-02。

## 字节与版本链

| 对象 | Status / Revision | SHA-256 | 可恢复来源 |
|---|---|---|---|
| 原审查包Baseline | Draft / 1 | `bbcd3414b97ad6ff3587912df29de4644c7a4c27a68dfd39ce0b6a87bb61054a` | 原Baseline ZIP成员 |
| 归位后Draft | Draft / 1 | `c8908e2296527425cbe1537ee607da1fdc5564801615f72ae34f05f1f74e3bb0` | 新包inputs/BASELINE_C890_DRAFT.md |
| BR-01限定事实审查后Draft | Draft / 1 | `34398530423f69953cb312a5170a788b8ed8f2d0c258bc597dafa81e80d4282c` | 新包inputs/BASELINE_3439_DRAFT.md及原Plan ZIP |
| 三项选择归一后的首次目标批准 | Approved / 1 | `13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3` | 当前Baseline及新包inputs/BASELINE_1384_APPROVED.md |

c890→3439仅审查metadata；3439→1384包含明确三项规则的归一、AC-08～10、批准状态/范围及导航交接。前后完整diff随新包inputs提供。AC-01～07、Goal、User Outcome、Non-goals、Preserved Constraints以及原Current Truth第1～8节逐字保持；不跨版本补造运行证据。

首次批准前文件为Draft，按照所选baseline-contract，Draft内容修订不要求递增Revision；只有Approved目标的正式Amendment才递增。因此Revision保持1有真实方法依据，不是漏增Approved Amendment。

## AC-08～10与规则的关系

| AC | 已明确选择的产品内容 | 生效关系 |
|---|---|---|
| AC-08 | D-P01三类语义、来源/事实/人物/禁称、结构与可区别判据 | 首次批准操作中归一为可观察判据，无新类型能力宣称 |
| AC-09 | D-P02方案A，未分配→用户明确分配；无均分默认；实际合计校验 | 同一首次批准归一，不把测试比例变产品比例 |
| AC-10 | D-P03 Novel默认、Repurpose独立选择与分别计数 | 同一首次批准归一，不批准Native Ledger变更 |

Founder明确选择了规则及冻结操作，未逐字签署AC编号；本记录如实区分用户原决定与agent的忠实归一。完整AC原文及Baseline SHA见新包 `evidence/APPROVED_AC_SOURCE.json`。本轮既不新增AC，也不重编号，不要求重复批准。

## Checkpoint关系与批准边界

代码仍是 `ceac16dabf1d680f72d1f4a02ca9aa07f2dda7dd`，父 `629a934d6a3a73525e7e14bec12f85e50f5fb4fa`，Checkpoint分支 `codex/checkpoint-publish-copy-founder-uat-20261022`，实际检出main。文档冻结没有新代码Commit或功能验收。

[BR-01](BASELINE_REVIEW_RECORD.md)仍仅证明其原限定Current Truth裁决，不改其原文/JSON。C01～C08、Native人审/资格、O-ACTIVE B、汇总Owner委托、PR-4新建议、Plan Freeze、实施/生产均不因本次补证获批。原审查包、Manifest及SHA保持不变。
