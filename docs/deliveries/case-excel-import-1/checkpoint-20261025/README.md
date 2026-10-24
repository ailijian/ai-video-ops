# CASE Excel V0.3：本地 checkpoint 范围

本文件记录 2026-10-25 授权的本地工程快照范围，不是新的业务批准、生产 Release 或真实模型验收。

## 当前成果与限制

- 原 EX-S1/ME-R1、JC-01、CC-01/CC-02、有限 EX-S2 均保留原 Intake、Task、Evidence、人审和 Publication Owner；源码及历史授权入口见 [R4 工程材料](../native-implementation-r4/README.md)。
- Founder 在全虚构隔离环境操作了 15 行原表：5 条绑定视频并完成解析、收录，其中 4 条共享、1 条撤回；其余 10 条保持待补证。同来源再次确认实际新建 0 个任务。
- 五条正式视频类型全部明确暂缓为 null。具体类型准确性、真实模型质量、真实平台来源和生产资格仍未验收。
- 上传界面明确区分选文件、来源确认和保存，更换文件需重新确认；底部主按钮随缺项切换。
- 编排结果使用原 Publication Reader 的只读状态，区分已撤回、共享未完成及需重新核对；原编排 state 保持兼容。

## 本次 Git 快照范围

提交包括自 `61efbc477ea28b9aee9a492d3ee96324718ef592` 后本专项的 Console/Pipeline 接缝、严格 Schema、目录、迁移、界面、测试、既有评审材料及必要验证器诊断/Windows fixture 可靠性修复。

不纳入 `.local/`、`.verify/`、虚拟环境、数据库、上传媒体、Cookie、真实凭据、主工作区模板资料或 cc2 工作线的未提交成果。`internal-console/ops-pipeline/.venv` 是既有本地测试链接，保留原位置并排除提交。

## 准确验证与保护证据

正式全仓回归须在源码冻结后使用仓库 `tools/verify.py --windows-short-temp --jobs 4 --timeout 3600` 实际执行；通过且源码不变后才允许创建 checkpoint 并提交。

本轮最终运行身份、JUnit、源码白名单、提交 SHA 和历史保护核对保存在项目主目录的 `.local/evidence/case-excel-regression-checkpoint-20261025/`。该目录由执行结果生成，不能以旧 R4 回归或本文件预先替代 PASS。

此前证据保留：

- `.local/evidence/case-excel-pending-ui-20261024/closeout-20261025/`：Founder 限定流程及撤回重放的实际复核。
- `.local/evidence/case-excel-upload-status-ux-20261025/`：上传入口、来源提示和撤回状态优化、相关回归及三屏交互。
- 原 R2/R3/R4 审查包、Manifest、Receipt、Closure 和 Ledger 原字节保留；本文件不改写其历史结论。
