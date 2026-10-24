# JT_RELEASE_1 — 主线整合与 4090 发布

Founder 已授权安全整合、普通非强制 Push 和按正式 Runbook 部署。当前文件记录候选范围，不预先宣称回归或生产 PASS。

候选从准确远程 main `f10f3992433ab81df38ae90f9379ce1061a7afac` 开始，保留 checkpoint `2a154da7c06a76ae7204797c1de3f602756ccd22` 的历史。C1 只选入独立 checkpoint `32f81004f338144cf41ab5631b8875a83cd298df` 的 14 个源码／测试文件，人工解决四个共享入口冲突；未合入 C2 实验代码或未提交研究资料。

[发布范围](RELEASE_SCOPE.json) 逐项记录原 Owner、Founder 实际验收和生产前置条件。原 Baseline、Plan、审查 ZIP、Manifest、Receipt、Canonical 与 Ledger 保持历史身份。新回归必须覆盖完整集成候选，不能复用上一轮 1,832 项 JUnit 收据。

默认关闭 `AIVO_CREATION_BATCH_ENABLED`，阻断批次写入、协调和已排队但尚未 claim 的批次派发。只读历史不因开关关闭而被改写。测试夹具明确开启隔离工程范围；开关不授予任何 Pattern、Compatibility、事实、人审或模型权限。C1 保留现有 News 开放规则。

实际 Git、源码 SHA、完整回归、敏感信息审查、远程身份和保护结果在主项目 `.local/evidence/jt-release-1-20261025/` 中由实测生成。最终提交不在自身文档中循环声明 SHA。R4～R8 必须等待实际 4090 盘点、备份、真实旧版本回退演练和预发布/生产 Smoke；开发机不能直接连接，Founder 将通过向日葵执行精确指令。

## 生产操作入口

使用 [本轮交接边界](PRODUCTION_HANDOFF.md) 与原 [部署 Runbook](../../operations/CASE_SMART_INTAKE_V1_1_PRODUCTION_DEPLOY_RUNBOOK.md)、[Local Node](../../../deploy/local-node/README.md)。本轮已明确授权经过扫描的 Public origin；不更改仓库可见性。
