# Console 完整回归超时：诊断与收口

状态：`FULL_CONSOLE_REGRESSION_CLOSED`。2026-10-24，本状态只表示准确工作树上的完整 Console 已通过，不授予 Native 合同、I3、真实模型或生产权限。

## 当前代码与真实最终收据

| 工作线 | HEAD / branch | 原验证器 run | 完整 Console | 耗时 |
|---|---|---|---|---|
| cxi | `61efbc477ea28b9aee9a492d3ee96324718ef592` / `codex/checkpoint-case-excel-i1-i2-founder-uat-20261024`；含本轮之前已存在的 EX-R1 未提交增量及本轮验证器改动 | `164b73c3` | 1013 passed；0 failures / errors / skipped；4 份原始 JUnit | 1741.143 秒 |
| cc2 | `32f81004f338144cf41ab5631b8875a83cd298df` / `codex/checkpoint-capacity-c1-founder-uat-20261024`；本轮不改代码 | `e8b50191` | 884 passed；0 failures / errors / skipped；6 份原始 JUnit | 1401.662 秒 |

两次协调器均 PASS、`state_unchanged=true`、exit 0。独立收集清单与每份最终 JUnit 逐个 node identity 比较：全部实际执行，且每条工作线内每项仅一次，没有漏项、重复或跳过。两条工作线含重叠的既有测试，不能把相加数量称为独立产品能力数。

完整 JS 原始记录随所属 Console 聚合入口执行：cxi 260/260，cc2 243/243，失败、取消、跳过均为 0；这些 Node 项不是额外 Python 用例。验证器自测 28 项通过。另有一个有意触发的 3 秒超时负控，实际状态为 FAILED/124、无 JUnit；只验证诊断行为，不混入 Console PASS 数量。

证据目录：`E:/projects/ai-video-ops/.local/evidence/console-regression-closeout-20261024/`。从 `FINAL_RECEIPTS.json` 查看准确收据、每片 SHA 与源码身份；`console-cxi/`、`console-cc2/` 保存原 summary、JUnit、stdout/stderr 合并日志和 JS 日志，均按原字节复制。

## 原因与证明

1. 前轮 `b0e4451f` 四分片都在 1200 秒被监督进程终止，exit 124，未到 pytest 最终写 JUnit 的时点。旧失败记录保持原状态，不补造收据。
2. 旧 965 项成功收据的累计测试时间为 6283.131 秒；沿该历史单位成本，理想四片也至少约 1570.783 秒，已超出 1200 秒。旧证据用于预算判断，不替代当前测试。
3. 当前版本隔离复现五 Slot 完整原生链路，call 约 313 秒、协调总计约 320 秒，真实 JUnit PASS。90 秒堆栈显示等待原生审核子进程；后续发布准备、发布导出、汇总预览/导出/list 子进程持续推进并最终结束。该路径未观测死锁。
4. 当前最终 1013 项累计测试时间为 6883.490 秒，四片实际完成为约 29 分钟，最慢片 1739.163 秒。完整运行穿过旧 20 分钟中止边界后正常完成；监督预算不足已由当前收据直接证实。
5. 原生生成、审核、发布、历史及故障恢复测试有大量真实子进程与文件/lineage 校验；其中发布稿进程恢复保留真实 lease 等待。没有通过删断言、跳过 Native Owner 或缩短安全 lease 来提速。当前短时资源样本见两个 `*_RESOURCE_SAMPLES.json`；它们不量化旧并行运行的争用、杀毒或 OS 各项成本。没有把未测因素宣称已排除。
6. 原验证器在超时后的 JUnit 读取异常覆盖了最初的 `Exceeded ... timeout`，且点状日志无法直接定位在途用例。这是诊断信息丢失，不是业务成功。本轮已修复。

前一轮已修复的 XLSX 时间戳测试夹具问题与监督超时分开：重复生成内容相同但 ZIP 时间戳不同的文件改变了文件 SHA/Batch。测试现复用原工作簿字节，原生幂等未放宽；本次完整运行覆盖该测试。该修复来自前一轮，本轮未再次修改业务或该测试。

## 本轮最小变更与执行策略

- cxi `tools/verify.py`：Console 加 `-vv` 显示具体测试身份；缺失 JUnit 时保留原超时原因。成功标准、选择规则、Source 状态检查和 Native 操作限时不变。
- cxi `tools/tests/test_verify.py`：新增超时、缺失 JUnit、FAILED/124 与精确模块选择不变的回归断言。28 项验证器自测通过；真实子进程超时负控也保持 FAILED/124。
- cxi `tools/README.md`：记录完整 Console 的显式预算和单套执行方式。未提高全局默认值，慢主机或串行诊断仍须据实设置 CLI 预算。
- 本轮无 app/static、Native schema、Writer、审批或 I3 代码修改。原有未提交功能增量保持原字节。

准确命令（各自在对应工作树根执行）：

```text
<cxi Console Python> tools/verify.py --target console --jobs 4 --timeout 3600 --windows-short-temp
<cc2 Console Python> tools/verify.py --target console --jobs 6 --timeout 3600 --windows-short-temp
```

真实可执行路径在 `FULL_RUN_INPUT.json`、`cc2-FULL_RUN_INPUT.json` 与各 summary 的 command 字段；上面尖括号是说明，不是可直接粘贴的 shell 参数。cxi 完全退出后才启动 cc2；6 是原验证器已有的有界并发选项，在本机 12 个逻辑 CPU 的默认上限内。cc2 仍使用其未修改的验证器。3600 是每片监督上限，不改任一 Native 操作超时或生产限流；所有模块实际执行，不用结果缓存。

## 保护与仍待审边界

`PROTECTION_RESULT.json` 确认：958 份原非锁数据/静态文件、8 个历史 ZIP、9 份历史收据共 975 项 SHA 不变；cc2 三份未提交 C2 文档不变；原 24 个 Task 的元组摘要不变；原 V0.3 Excel/JSON SHA 不变。三个项目工作树 HEAD 未变、暂存区为空，没有项目提交/推送/合并。测试中既有的隔离 Git Source fixture 提交不是项目提交。

旧 ZIP、Manifest、SHA、FAILED 收据不改写。只在当前可编辑文档补充新的验证结果。验证结束后本目录仅更新说明/导航；已测试实现及测试源不再修改。

EX-S1、ME-R1、CC-01、CC-02 / I3 仍待独立审查，未由测试 PASS 自动批准。未开发新 Novelty、正式解析提交、Case 类型批准或 typed 共享。全仓回归、真实模型质量、生产与 Founder 完整链路统一验收不在本次 Console 结论内。
