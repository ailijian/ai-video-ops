# Final activation-review verification

Current local result: independent Code Review R4 PASS; canonical full repository
regression PASS. Production is not activated. The final attributed record is
[ACTIVATION_REVIEW_RECORD.md](ACTIVATION_REVIEW_RECORD.md).

| Final route | Observed result |
|---|---|
| Canonical `tools/verify.py --windows-short-temp --jobs 4 --timeout 3600` | 1,948 actual checks PASS; `.verify/b287f0b6/summary.json` |
| Console | 1,127 PASS across all three shards; JS bridge included |
| Pipeline | 751 PASS; 264 opt-in live Authority cases deselected |
| Authority Release / FRP Guard / verifier | 12 / 30 / 28 PASS |
| Fresh R8 repairs and actual Native seam | 26 unit checks plus one complete Native scenario PASS; both exporters' same-Task closure recovery, successor history/new write, generation identity, relative roots, K=2,2,1 serial execution and negatives |
| Compile / strict schemas | 26 Python files; 11 Draft 2020-12 Schema documents PASS |
| Protection | 879 historical files and six other worktrees unchanged; Baseline SHA 13844cf74cd3eaf3a80e104fad26fbf56aa4548204c26597ab2e9623625fd0c3 |

Final raw review, exact source identities, all current JUnit/summary logs and
checksum package are retained under
`.local/evidence/jt-production-creation-1-activation-review-20261025/`.
The verification receipts predate the later authorized white-list checkpoint;
no production mutation is asserted by them. Push remains unauthorized. Real-model quality
and production readiness need their own actual evidence and Native decisions.

## Earlier retained verification (historical, not substituted for the final run)

# 本地验证与交接 — 2026-10-25

状态：激活前独立复审与追加验证进行中；4090 尚未激活本次候选。以下为首份审查包对应的历史观测，最新修复状态见 [激活前审查记录](ACTIVATION_REVIEW_RECORD.md)。
真实模型执行已获 Founder 明确授权，本轮测试使用合成外部传输，实际付费调用为 0。

代码基于 `85eae99a90d9fbb97968b0d91771bb881f2cfc22`，保留未提交增量。
准确字节身份、完整新增文件与 patch 由审查包 `SOURCE_IDENTITY.json` 及 Manifest 绑定。

已观察的结果：

- Console 合同、权限、旧版 Release、HTTP/HTTPS 与 JS 包装测试：59 PASS。
- Pipeline 旧合同及 Content Quality：59 PASS；按原默认策略排除 9 项 live Authority 检查。
- REC-01 调用前/响应后中断恢复：2 PASS，未知结果不自动重发。
- Native 完成续测：1 PASS；原生 Reader 重新验证五条批次及 Conversion 交付，随后完成合法价格来源的 Repurpose。
- JavaScript：60 个文件、295 项 PASS；此组也包含在上述 Console 的一个包装测试中，不能重复解释成两组独立覆盖。
- Chromium 1440/390/320px：真实登录、原生资格核对、修改失效、刷新重新核对及明确阻断提示 PASS；无页面 JS 异常或横向溢出。
- 阻断提示的浏览器测试注入了已测 HTTP 409 响应；真正缺失 Runtime 的 Native HTTP 负向测试另行执行。
- 11 份 Schema 定义通过真实 Draft 2020-12 检查，另有 15 个隔离生成实例通过该验证器。
- Python 编译、diff 检查、旧 Baseline/合同/策略字节及其他工作树保护检查通过，详细范围在证据包中。

组合 Native 脚本的中间失败没有被改写为 PASS：R8 在已完成五条交付、故障恢复和 Conversion 后，复用了相同客户投稿，触发合法去重；第一次续测又选择了没有价格锚点的故事来源，原 Repurpose Reader 正确拒绝。修正了测试样本，未放宽来源规则。最终在相同机器源码和保留隔离环境中重新核对已有正式结果并完成剩余合法改编链，形成独立 JUnit。修正样本后没有从空库重跑整个组合脚本；不将该脚本原失败收据宣称为 PASS。

新增生产用途的五条批次包含 Novel 2、人设 1、故事 2，并形成 News/Mix 两类 Excel；Conversion 与 Repurpose 分别验证。原 Human Review、Publish Confirmation、Receipt、Closure 和 Ledger 仍由原 Owner 形成。全部数据为独立虚构环境，均不是正式激活输入。

候选生产 Batch 上限为 5，单客户逐次派发；20/40 条生产批次及真实吞吐未验证。单个 Native Request 仍使用原 Owner 的数量、事实和资格合同，不能把原合同数量上限解释为新的生产实测。

全仓 `tools/verify.py` 本轮未运行，遵循 Founder 暂停全仓回归的指令。未提交、推送、部署，未写入真实生产数据。正式激活仍依赖独立审查、准确源码 Commit、真实公司级结构 Authority/Control 与原生人审决定，见 [激活交接](ACTIVATION_HANDOFF.md)。

本机审查目录：`.local/evidence/jt-production-creation-1-review-20261025/`。
原始失败记录和全部中间材料原地保留；审查包提供脱敏失败说明和原收据 SHA。
