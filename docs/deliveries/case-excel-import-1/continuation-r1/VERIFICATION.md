# 最新 Console 验证补充（2026-10-24）

`FULL_CONSOLE_REGRESSION_CLOSED`：cxi run `164b73c3`，1013 项；cc2 run `e8b50191`，884 项；两者失败/错误/跳过均 0，原协调器 PASS、state_unchanged=true。10 份真实原始 JUnit 已逐项与完整收集清单比对，无漏项或重复。

本轮仅改 cxi 验证器诊断、对应自测及操作说明，没有功能/Native/I3 代码增量。真实原因、命令、源码身份、分片收据、SHA、边界和保护结果见 [Console 超时诊断与收口](CONSOLE_REGRESSION_TIMEOUT_ROOT_CAUSE.md) 及 `E:/projects/ai-video-ops/.local/evidence/console-regression-closeout-20261024/FINAL_RECEIPTS.json`。

EX-S1、ME-R1、CC-01/CC-02 与 I3 继续待审；本结果不代签审批，也不代表全仓/真实模型/生产或完整 Founder UAT 通过。旧包与失败收据原字节保留。

---

以下为前一轮 EX-R1 审查快照的历史验证记录，其中“尚未关闭”“未改框架”等陈述描述当时状态，以本页上方的本轮补充为当前 Console 结论。

# 本轮验证与剩余 Gate

代码基底：`61efbc477ea28b9aee9a492d3ee96324718ef592`，分支 `codex/checkpoint-case-excel-i1-i2-founder-uat-20261024`；当前为未提交增量。精确源码 SHA、diff、命令、JUnit、浏览器截图和保护核验写入项目 `.local/evidence/case-excel-continuation-r1-20261024/`；最终 `FINAL_VERIFICATION.json` 与 review ZIP 为这次运行的准确身份，不能借用旧全仓收据。

已执行聚焦集合：Excel 私有保存/恢复、V0.3 解析和 HTTP、本人投稿新投影、原投稿/共享/Reviewer 隔离、UAT2、视觉规范、完整前端 JS 聚合。该次 JUnit 172 项零失败/错误；其中 JS 是一个 Python 聚合入口，其独立 Node 数量与源码见 `javascript.log/json`。随后只调整详情页标题文字，最终 Console 覆盖结果及准确测试源以最终收据为准。

首次完整 Console run `2af65aa1` 在取消恢复测试出现失败后中止诊断，不作为完整回归收据。已用原测试入口在 ZIP 时间戳跨界条件稳定复现：测试重新生成了内容相同、文件 SHA 不同的 XLSX，实际操作属于另一个 Batch；原生按文件身份区分批次是正确行为。修正仅让取消/旧 head 测试复用原始工作簿字节，未删除或放宽断言，未改生产幂等。原失败日志、时间戳诊断、复现 JUnit 和修复后 13 项聚焦 JUnit 保留。没有修改验证框架、运行时安全参数或测试预算；最终重跑使用原验证器的受限分片参数，并记录准确命令及源码。

完整 Console 最终尝试 `b0e4451f`：原验证器 `--target console --jobs 4 --timeout 1200 --windows-short-temp`，四分片均达到 1200 秒后以 exit 124 中止，缺少最终 JUnit；总时长 1202.332 秒，`state_unchanged=true`。结论为 **FULL_CONSOLE_REGRESSION_NOT_CLOSED**，不是 PASS。当前只读收口的最终聚焦集合另存 `final-focused/`，不得把未完成分片的点状进度或旧 965 项当作当前完整通过。

已观测的阻断是本次监督预算中止。历史 cxi `be5b07fb` 三分片总耗时 2107.651 秒，说明 20 分钟不能作为该历史规模的完整执行预算依据；历史时间不能证明当前必然只需增加时间，也不能替代新的性能/资源排查。当前分片 stdout、准确模块/测试收集及命令均保留；尚未证明无资源争用或无其他耗时来源。未修改测试框架或共享环境，后续完整链路实施/统一验收前仍须关闭该回归 Gate。当前包仅提交只读增量与合同审查，不申请正式发布。

新投影正负覆盖：普通用户本人精确行身份与类型 null；跨用户无明细；父链决定最新操作；Row 已落盘但结果未确认；部分取消；损坏 SHA/未知版本失败关闭；读取期间撤权/Session 过期；上传过期只改变当前读投影；重复读取不创建 Task/Group/Case 或重复卡片。测试使用原登录、原 R2 Writer/Reader、原上传入口；仅视频 probe 外部边界使用虚构返回。没有伪造 Reviewer grant 或批准记录。

浏览器在独立 18828、虚构既有测试记录、模型/worker 关闭的环境检查：本人列表 → 单行详情 → 展开未核原文 → 固定底部返回 → 刷新；1440/390/320 均保留真实行/操作，横向尺寸测量及截图另存。实际完成范围见 `BROWSER_EVIDENCE.json`，未执行内容不得据此写 PASS。手机宽度模拟不等于真实手机设备验收，Founder 全链路体验仍留在后续统一进行。

## 实施与验证边界

| 范围 | 当前证据与下一 Gate |
|---|---|
| I1 / I2 / EX-R1 | 原 I1/I2 有限定独立审查与 Founder 体验；本轮只读本人列表/详情增量本地验证，等待本轮独立审查；原保存 False Authority 标志与 Schema 不变 |
| EX-S1 | 精确解析准入/Task 映射/worker 接缝提案待批准；未创建表、迁移、Task 或接口，正负写入试验未执行 |
| ME-R1 | 投稿者只读本人原文已实现；其他 Reviewer 读取绑定行仍待独立批准，未打开权限 |
| CC-01 / CC-02 | 类型决定与 typed 共享提案待审；正式类型仍 null，旧 Case Approval/Shared Owner 与两份独立 Authority 不改 |
| 真实模型 / 生产 / 全链路 Founder UAT | 本轮未执行、未批准；不能把投影或合成边界测试视为解析质量或正式共享通过 |

原 V0.3、B0 ZIP、R2 原文件、旧 Manifest/SHA 与历史收据保留。原根工作区、cc2、原 24 个 Task、原 958 个非锁数据/静态文件的本轮对比以 `PROTECTION_RESULT.json` 为准；合法读取产生的锁元数据不是业务回写，不能还原锁文件冒充完全无 IO。

本轮没有 Git 提交/推送/合并、生产部署、真实模型调用或 AUTH/OIDC 变更。批准后的最小闭环、故障恢复、类型审核和共享兼容测试见 `EXACT_REVIEW_REQUEST.md` 与 `TEST_MATRIX.json`，当前待批项目保持 NOT_EXECUTED。
