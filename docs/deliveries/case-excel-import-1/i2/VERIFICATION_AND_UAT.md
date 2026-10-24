# 验证与最后统一验收

真实收据在 `E:/projects/ai-video-ops/.local/evidence/case-excel-i2-20261024/`。`i2-focused-final-fixed.xml` 和 `javascript.json/log` 记录实际执行；最终 `FINAL_RESULT.json` 绑定源码及完整Console状态。不能借用上轮旧版本PASS。

聚焦覆盖：36项I2、79项I1解析、7项I1 HTTP、19项原生上传、1项全JS桥接，共142项pytest；JS内部242项。原uploader探测的单元测试在外部媒体边界注入；浏览器另走真实PyAV检测全合成视频。没有真实模型或真实视频解析质量PASS。

| 要求 | 实际证据 |
|---|---|
| 只预检无写入，确认后保存 | `test_prepare_has_no_writes_then_exact_replay_and_owner_projection` |
| 16虚构向量、错误行、并发重复点击 | `test_concurrent_double_submit_and_all_sixteen_vectors`及错误行测试 |
| 九个发布边界异常和真实进程退出 | `test_each_atomic_boundary_recovers_same_intent_without_duplicate`、`test_actual_process_exit_releases_locks_and_recovers` |
| 变更意图/head冲突、跨文件同源 | `test_changed_operation_or_stale_head_is_rejected`、同源新编号测试 |
| 私有隔离、他人上传、撤权 | 跨用户、解析中撤权、已存首行后撤权测试 |
| 绑定、过期、完成重放 | `test_real_upload_binding_expiry_projection_and_completed_replay` |
| 纯文件名、错源、未知版本、危险输入 | 对应source/Schema/HTTP测试及原I1安全集 |
| 定向取消与新意图 | `test_cancel_remaining_after_partial_publication_preserves_saved_row` |
| 取消Intent后退出、逐行引用尚未发布、媒体已过期 | `test_durable_cancel_intent_stops_old_save_even_before_row_markers`、`test_accepted_cancel_does_not_require_expired_media_for_unsaved_row`；前者已先复现失败后修复 |
| 刷新后从原记录恢复 | `test_recover_from_persisted_record_after_refresh` |
| 1440/390/320真实点击、视频上传、刷新/重登 | `BROWSER_RESULT.json`、`BROWSER_SOURCE_BINDING.json`与I2截图 |

浏览器证据为桌面Chromium viewport，不能代替真实iOS/Android或其他内核。当前cxi完整Console使用原验证器单独执行，不与cc2重型回归争用。cc2源码未变，保留原884项精确版本结果，不拿它替代cxi。

浏览器另经测试环境的单次I/O中断执行：首行保存后返回recovery_required → 刷新 → 从原记录恢复为2行；另一批同样中断后明确取消 → 仅保留已存1行。仅在隔离启动器注入I/O异常，实际身份、Canonical写入、锁和所有业务Gate照常执行。修改行选择后旧确认失效；不变视频复用同一上传引用，服务端仍重新校验。

初次完整Console run `9b432db8` 在审查发现取消Intent边界缺陷后主动停止，保留日志，不报PASS。`cancel-intent-before.xml`记录2个真实失败，`cancel-intent-after.xml`记录修复后通过；最终完整回归必须在修复源码上另行执行。

后续run `7223d628`发现品牌检查仍要求旧app.js缓存版本；已隔离复现并更新准确版本断言，同时保留所有原品牌检查及新增模块/样式版本检查。`branding-before.xml`记录原失败，`branding-after.xml`记录两项品牌测试及完整JS桥接通过。该中止run也不报完整PASS，最终结果只取最终稳定代码的真实JUnit与summary。

## Founder最后统一体验

自动化收口后，从18827案例Excel入口：选择虚构模板后自动检查 → 在同一核对页查看问题、选择行及可选补充本行视频 → 点击底部“保存 N 条私有投稿”一次明确保存 → 进入独立结果页。上传视频仍须明确确认权限与来源对应关系。随后从“查看本次投稿”及“我的导入记录”刷新、重登查回；正式类型仍未审核，没有解析任务或共享。

来源不足可保存待补证候选；错误行不写有效候选。同源不同编号关联已有投稿且保留新说明。中断使用原保存恢复或取消未存部分；“候选已保存”不等于Case Approved。

以上为取得本轮人工确认前的准备记录；后续限定 Founder 实测结果见文末追加记录，未代签 ChatGPT 独立验收。I3分类/共享与正式语义政策不在本轮已实现范围。


## 2026-10-24 整体导入交互优化（未提交）

本次证据目录：`E:/projects/ai-video-ops/.local/evidence/excel-import-flow-20261024/`。本节独立于上文历史 I2 收据，不借用旧完整 Console PASS；准确最终源码 SHA 及执行结果以本目录 `FINAL_VERIFICATION.json` 和 `focused-final.xml` 为准。

- 入口统一为“Excel 批量导入”。选择表格即只读预检，只显示当前步骤；正常保存合并为一次明确操作，移除重复的准备/确认复选框，保留真实视频的权限确认。
- 固定底部主按钮按状态切换，错误行不可选、零选择不可保存；保存中禁止重复操作，预检变化必须重新核对。
- 准备成功后先绑定精确 Batch/Operation 地址。保存后读取原生记录进入独立结果页；未知结果仅查询原操作，禁止新意图自动重发。
- 原生中断可刷新后继续原保存；明确结束仅取消尚未保存部分，确认使用既有页面内对话框。结果区分已保存、未保存已结束、填写需修改、结果待确认。
- 个人导入记录单独分页，使用原 Reader 获取真实标题及保存状态。会话恢复仅允许受限的本地 Excel 路径，原登录、CSRF、权限与密码门不变。
- 本次仅修改前端及相应测试；55 个后端 Owner 源文件、本轮开始前 1027 个受保护文件均逐字节核对，结果见最终收据。

隔离浏览器已执行正常保存、上传权限负向、真实合成视频原上传器、刷新、退出重登、错误行、空表、1440/390/320 布局及原操作恢复。测试专用 18828 与 Founder 18827 数据隔离，所有 Worker 关闭。浏览器原生确认曾阻塞自动化，已改为复用现有页面内确认；最终该路径的实际复验范围和残余限制须查看 `BROWSER_CHECKS.json`，不得将未执行项写为 PASS。

Founder 已经自行保存的两条投稿保持原 Batch/Operation，不再次保存：`import_2fcd38f4cbe5e06acd91d0564e3aa0ca` / `import_230b710e-3aee-409b-a838-3bc26646c1ac`。下一步请在新结果页点击“查看本次投稿”，刷新后确认两条原题目及待核验、来源待核对状态。该人工体验在本节形成时仍待 Founder 回答；后续本人答复见文末记录，本文件不代签。


### 浏览器阻塞解除后的补验

`E:/projects/ai-video-ops/.local/evidence/excel-import-flow-followup-20261024/` 保存本轮追加证据；上轮 Manifest、SHA 和测试收据保持不变。运行代码和测试与上轮 125 项 Python、257 项 JS PASS 的精确版本一致。

新版页面内结束确认已经实际点击通过：取消确认不写入任何 Intent/Result；明确结束后保留已保存 1 行，仅结束剩余 1 行；刷新后分别显示“待核验”和“未保存 · 已结束”；个人记录列表显示真实标题及数量，并能回到准确操作。原首行与此前 29 个隔离导入文件 SHA 不变，原始 Founder 资料及 1027 个受保护文件保持不变。18828 测试页和服务已关闭，18825/18827 验收服务保留。

本次自动化补验完成时，Founder 两条原投稿的刷新体验仍等待本人确认；后续本人答复见下节。


### Founder 私有候选保存与刷新查回确认

2026-10-24，Founder 对“查看本次投稿、刷新、两条原题目及待核验/来源待核对状态”的直接答复为：“两条内容和状态一致，刷新后仍能查回”。本步骤限定人工验收通过。原 Batch/Operation、两条私有未核候选及来源状态保持不变，没有新建分析任务、正式批准或共享。

准确答复来源、代码/证据 SHA 和统一验收范围记录在 `E:/projects/ai-video-ops/.local/evidence/capacity-excel-founder-closeout-20261024-151546/FOUNDER_UAT_RECORD.json`。此前容量说明数值及三份 Excel 预检结果由各自原答复支持；不能把本次刷新确认扩大为所有界面视觉设计、新语义规则、I3 分类/共享或生产验收批准。原历史 Manifest 与 SHA 保留。
