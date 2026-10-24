# Excel I1 上传预览与 I2 精确待审合同

- [真实无业务写入的上传预览](CASE_EXCEL_I1_UPLOAD_PREVIEW_READY.md)。核心解析的限定独立审查已通过；新增页面/HTTP接缝有真实测试与浏览器证据，仍待本轮独立核验。
- [I2精确候选合同与边界](CASE_EXCEL_I2_EXACT_CONTRACT_READY_FOR_REVIEW.md)、[候选Schema](I2_EXACT_WRITE_CONTRACT_R2_PROPOSAL.json)。仅待审材料，不是持久化授权。
- [原I1/B0身份与历史包](../i1/README.md)。I3正式分类及Typed Shared Display仍待独立Authority批准。

本轮完整Console最终收据与SHA、超时诊断、源码保护及浏览器证据见 `E:/projects/ai-video-ops/.local/evidence/capacity-case-review-closeout-20261024/REGRESSION_SUMMARY.json` 和同目录最终评审包。不以旧Pipeline/JS结果替代Console。

没有项目提交、推送、合并、部署、真实模型或新Case Approval。原V0.3模板、原ZIP、Manifest和历史SHA不改写。

最终Console已由原验证器正式通过：cc2 run a2757164，884例；cxi run be5b07fb，965例；均零失败/错误/跳过，state_unchanged=true。只关闭Console缺口，不代表全仓、真实模型或生产验收。最终ZIP：`E:/projects/ai-video-ops/.local/evidence/capacity-case-review-closeout-20261024/CAPACITY_C1_SHADOW_C2_EXCEL_I1_CLOSEOUT_REVIEW.zip`，SHA-256 `9062995083cf5fd6ee6ebe009bcca4702def0b0c9198b428e8317b3e10ed9b79`。

## 后续开发补修（2026-10-24）

按“先完成必要开发、最后统一验收”继续处理现有 I1 范围：已复现损坏 DEFLATE 数据泄漏 `zlib.error` 的错误路径，解析器现将其归入既有 `ZIP_INVALID_OR_CRC` 输入拒绝，HTTP 返回 422。未放宽 CRC、模板或输入预算，未改变任何业务 Schema、候选存储或 Authority。

新增两条回归先失败再通过；当前解析/HTTP 共 86 项通过，另有完整 JS 聚合通过。当前补修源码与测试身份、前后差异和保护检查见 `E:/projects/ai-video-ops/.local/evidence/development-closeout-r2-20261024/`。上面的 Console 965 项为补修前准确版本的历史收据，不借用为当前新版本全 Console PASS；本次最小错误处理修复仅执行相关解析/HTTP 与 JS 验证。原 ZIP/Manifest 字节保持不变。

Founder 体验放在最后统一进行；I2 精确写入合同确认仍待本轮明确答复，I3 和新 Novelty 规则继续独立待批。未自动提交、推送或部署；既有测试服务需要在统一体验前重新加载补修版本。

后续答复已收到：Founder批准准确R2的I2受限开发，最后统一验收。[当前I2实现及授权来源](../i2/README.md)为最新导航；上段“待答复”是当时记录。原R2、ZIP及SHA不改写。I3和新Novelty仍待独立批准。
