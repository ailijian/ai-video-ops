# Content Uniqueness & Editorial Quality V1.0

## Freeze Record

- Status: **Approved / Frozen**
- Version: **V1.0**
- Implementation Baseline: **V1.1.1**
- Freeze Scope: Content uniqueness, historical exposure, editorial selection, capacity stop, and content-gap boundaries
- Regression Baseline: **129 tests PASS**
- Real-customer baseline: `shufang_zhiyuan_community_canteen`

本文件将已通过 V1、V1.1、V1.1.1 实验验证的规则固化为长期 Product Authority。它不重新定义内容战略，也不改变 Persona、Case、Pattern、Privacy、Proof 或 Human Approval Authority。

## Frozen Principles

### 1. Semantic Novelty

内容是否为新内容，由 Semantic Information 决定。标题、Hook、wording、Speaker、Case、Narrative Style 与 Shot Order 的变化均不得重置 Novelty。

### 2. Historical Exposure

Approved、Exported 或 Published 内容中，只要某项信息已经被 explicit communicated，无论它当时是 Primary、Supporting 还是 Incidental，均进入 Strong Historical Exposure。Rejected 或 abandoned generation 不永久占用 Semantic Space。

### 3. Communicated Information Unit

Content Ledger 必须记录用户在正式内容中实际被明确告知的信息，不得只记录 Central Claim。每个 Unit 保留 normalized meaning、Fact Atom refs、来源摘录、communication role、explicitness 与 source content lineage。

### 4. Atomic Fact Identity

Planning 层使用稳定 Fact Atom 标识事实。Fact Atom 必须可追溯到 Persona SHA、原 Field 与原 KNOWN Fact。Fact Atom 只提供 Planning Identity，不创建事实，也不改变 Persona Authority。

### 5. Material Information Gain

新 Content Concept 必须带来实质新增的信息、决策价值、具体场景、具体事实、授权故事、Speaker-specific observation，或对历史信息产生新的解释与行动价值。

以下变化不能单独形成 Novel Content：

- Audience Label 变化；
- Hook、标题、Speaker 或 Case 变化；
- 同一 Fact 的换表达；
- Historical Supporting / Incidental Information 升级为 Primary Topic；
- 已有 Use Case 绑定到另一已知客群；
- 同一 Customer Story 仅更换 takeaway wording。

### 6. Audience Need Provenance

每个 Audience Need 必须记录 `audience_need_origin` 与 `audience_need_source_refs`。Known Customer Pain、Question、Use Case、Authorized Feedback 与 Service Decision Need 必须引用稳定 Fact Atom。没有有效来源的兴趣推断必须标记为 `editorial_hypothesis`、`editorial_only`，不得伪装为已知用户需求。

`service_decision_need` 只允许用于可追溯到价格、等待时间、服务限制、流程、定制、加工能力或免费项目等实际 Business Facts 的决策问题。

### 7. Speaker Authority Is Not Speaker Fit

Speaker Authority 回答“该角色是否有资格表达”；Speaker Fit 回答“该角色是否自然会这样表达”。Speaker Fit 是 Editorial Signal，不得扩大或替代 Fact Authority。

### 8. Exclusive Anchor Is Not Novel Exclusive Anchor

Exclusive Anchor 是当前客户特有的具体信息。Novel Exclusive Anchor 还必须满足该信息未被 Strong Historical Content 明确消费。普通 Exclusive Anchor 不自动带来 Novelty。

### 9. Content Capacity Stop Rule

`requested_quantity` 不是强制交付数量。只有通过 Novelty Gate、Material Information Gain 与 Editorial Quality Gate 的 Concepts 才能进入 Selected Plan。容量不足时必须返回 `capacity_limited`，不得生成 Semantic Duplicate 或 Low-quality Padding。

### 10. Content Gap Boundary

Content Gap Report 只负责告诉运营下一步值得向客户补充哪些资料。它不得自动生成答案、依据行业常识补事实、从 Case 迁移事实、用网络搜索替代客户输入，或把推测写入 Persona。

新资料只有经过 `Human Input → Persona Review → Approval` 后，才能成为 Generation Authority。

## Configurable and Non-frozen Items

以下项目保持 provisional / configurable，不属于长期冻结规则：

- Candidate Pool 默认数量（当前为 30）；
- Editorial Score 权重与 Score Threshold；
- Exclusive Anchor、Customer-specific 与 Generic 的实验目标比例；
- Expected Capacity Gain heuristic；
- Semantic Judge 的具体实现方式；
- 当前 Generation Provider 或 Model；
- 当前 Approved Case 数量与具体 Case；
- 当前 Approved Pattern 数量与具体 Pattern。

调整这些参数不得绕过 Frozen Principles，也不得弱化 Authority、Privacy、Proof、Human Review 或 Capacity Stop Rule。

## Frozen Implementation Baseline

Canonical implementation responsibilities：

- `ops-pipeline/scripts/content_quality_v1.py`
- `ops-pipeline/scripts/generate_mix_scripts_v1.py`
- Content Signature
- Content Ledger
- Communicated Information Units
- Fact Atom
- Historical Exposure / Novelty Gate
- Audience Need Provenance
- Editorial Ranking / Speaker Fit
- Capacity Stop Rule
- Content Gap Report

冻结时的真实实验结果：

- B0 Approved / Exported Content: 10
- V1 initial reported capacity: 7
- V1.1 calibrated capacity: 3
- V1.1.1 closure capacity: 2
- Final status: `capacity_limited`
- Padding generated: No
- V1.1.1 diagnostic Remote Model Calls: 0

历史 B0、V1、V1.1 与 V1.1.1 Artifacts 保持只读，不因本次冻结重新生成、批准或导出。

## Change Control

未来修改 Frozen Principle、Authority Boundary、Historical Exposure Definition 或 Capacity Stop Rule，必须经过新的 Product Authority 与显式版本升级。实现细节、可调参数与启发式可以在不削弱本文件规则的前提下演进。
