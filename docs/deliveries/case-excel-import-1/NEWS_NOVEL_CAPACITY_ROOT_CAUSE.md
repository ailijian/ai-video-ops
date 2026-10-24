# 当前新闻新主题容量根因

证据：`evidence/NEWS_CAPACITY_PROBE.json`，代码 `4287234e5aa7f711751d7ec06dd0935ad6acbab2`；审计代码与验收环境4个关键脚本SHA逐一相同。仅对现有全虚构Golden验收客户 `customer_cacaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` / Speaker `speaker_bdbc2285ee0c5e`执行原只读投影。不是生产客户容量、模型质量或速度测试。

## 实际结果

Approved Business Fact Atom 中pricing_facts为3个；Business Ledger有4条Strong Memory。投影产生3个价格/优惠机会：

| 已批准事实（虚构） | 当前Novelty | 当前Gate解释 |
|---|---|---|
| 工作日自取午餐29元，不含配送 | already_communicated | 已表达，CONTENT_NOT_NOVEL，不再当新增语义 |
| 周末店内儿童小份餐15元，不参加工作日套餐 | already_communicated | 已表达，CONTENT_NOT_NOVEL，跨Mix/News共享记忆 |
| 周三自取线上预订菌菇午餐35元，每单一份 | novel | 当前隔离Pattern/Compatibility/Release与事实资格supported |

available_novel_count=1，production_ready_count=1；不是“整批所有类型只可交付1条”。其余2条的unsupported来自CONTENT_NOT_NOVEL，不能误读成缺Case或缺Pattern。当前剩余机会的eligible_case_count=3，固定结构参考已足够通过；无reservation阻断、无当前Constraints阻断。Scope仍为human_authorized_isolated_qualification，不代表对所有客户开放。

## 准确机器链

S28先由原Persona resolver取得Approved Business/Speaker，调用assert_production_allowed；只取安全事实原子中的pricing_facts且匹配PRICE_OR_OFFER，再按S29强记忆、语义签名及共享Ledger排除已表达/不确定，按原Content Intent Reservation排除占用。剩余Novel才进入S30原News Runtime的当前Pattern/Compatibility/Release、客户事实及quantity=1资格校验。S31 Batch预检按实际Novel＋supported机会计数，10条目标大于1，原生拒绝；UI只显示原拒绝，没有减少数量或换成Repurpose。

当前范围是price_offer_led_only，Pattern为pcv1_news_price_offer_led_micro_information；精确activation/release/pattern/decision refs与SHA保留在原只读探针。native binding的三条Case结构引用已固定，新增Case不自动进入这个已批准Release，也不授予新闻资格。

## 快速导入更多案例是否直接增加News新主题

**不能直接增加。** Case属于可借鉴结构和来源证据，不能变成该客户的新价格、事实、经历或已批准Business Truth。三种制作/业务类型标签也不改变Novelty；导入或审核更多Case不会清除这4条Strong Memory，也不能把已表达事实重新累计为Novel。

更多合法Case只可能改善结构研究/creative feasibility，且须原Case批准、Fingerprint、Pattern、Compatibility及Release各自适用Gate。本次具体瓶颈是客户可用事实与已用语义，剩余机会已通过创作结构资格，故“导入Case”不是本次容量修复。

## 独立改善建议（未实施）

1. 本批数量可由代理商明确调低并重新预检；不自动替换类型或补量。
2. 若客户确有新的、独立且可发布的价格/优惠及适用条件，走原Customer Fact Review与Business Persona批准，保留旧Ledger；仅重写同义句或升级Persona版本不会恢复Novel。
3. 要支持非价格的新主题，独立审查News Pattern/Coverage/Compatibility/Release扩展；导入Excel或阶段选择均不能越过这道Gate。
4. 已有内容需要改编时，显式选择合法Repurpose来源，保留Presentation History、不增加新增语义数；不得后台替代Novel目标。
5. 若下一轮需要完整20/40隔离UAT，单独准备有足量真实一致的虚构事实与合格来源的隔离夹具；本轮没有补造客户事实或修改运行库，也不把旧容量测试当这名客户有10个新主题。

这里只读诊断，不恢复性能优化、不清Ledger、不改原验收客户、Pattern、Release或生成功能。
