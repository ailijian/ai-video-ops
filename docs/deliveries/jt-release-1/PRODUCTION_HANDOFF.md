# 4090 生产交接：先核验再切换

本轮发布仍遵守原服务控制器、单 Console 进程、共享 GPU Guard、原存储和 Authority Owner。代码推进至 main 不等于生产已切换。

1. R4 只读核对真实主机、服务/控制器、受保护配置路径、运行 Commit、Python/Node、GPU、SQLite/Canonical/媒体路径、Active/Pending/Unknown、当前 Release、权限与 HTTPS/FRP。不得输出 Token、Cookie、密码、原始客户事实或完整配置。
2. 所有真实模型均未获本轮许可。部署时四个现有模型 Worker 必须关闭，Novel rollout 为 off、Batch 开关为 0、Publish Copy 默认 off。确认没有绕过 Worker 的同步模型入口及启动自动恢复调用，才允许启动。现有需生成的功能准确标记为暂未开放。
3. R5 通过原 Backup Owner 创建一致性备份；包括全部新 Excel/Type/Publication companion、原任务/会话与原正式文件。原工具排除的瞬时媒体需要按 Upload Owner 明确保留；不能声称其已自动备份。先验证恢复权限、SHA、行数和 Canonical 一致性。
4. 当前源码含 001～009 九个迁移。旧 CSI Runbook 的仅 001～004 校验不能直接当作新版本演练结果；必须针对真实备份、真实旧 Commit 验证完整迁移、重复执行、旧 Reader 和回退。不得删除表或手写迁移标记。
5. R6 预发布只能使用独立 SQLite、Canonical、Session 和端口，全部 Worker 关闭，不争用 GPU；不启动第二个生产实例。合成数据不进入生产，qualification_pending 不安装为 Production Release。
6. R7 仅在 R0～R6 完整 GO 后通过真实控制器有序切换；禁止覆盖 dirty 目录、直接 git pull 运行目录、重建 SQLite 或覆盖 Canonical。使用准确 Release Commit，保留旧服务和可验证回退路径。
7. R8 公网只读 Smoke 与明确授权的测试身份分开记录。正式类型暂缓为 null 合法；未批准的类型、Pattern、Compatibility、媒体权利不能由上线补造。

若生产安全认证、对象权限、备份、迁移/恢复或 Shared Authority 不满足要求，停止生产切换。若主线已推送，只能报告 `JT_RELEASE_1_MAIN_PUSHED_PRODUCTION_BLOCKED` 及精确原因，不能报告已部署。
