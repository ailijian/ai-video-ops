# 请求独立裁决的准确范围

本文件是请求，不记录已获得批准。已有 B0 方向认可和 I2 私有候选批准不能被扩写为下列接缝授权。当前 HEAD 为 61efbc477ea28b9aee9a492d3ee96324718ef592，含保留的未提交增量；准确文件 SHA 见 SOURCE_OWNER_MAP.json 与审查包 SOURCE_STATE.json。

| 待批单元 | 最小决定 | 批准后才可实施的业务边界 |
|---|---|---|
| EX-S1 | 原 Case Intake/Task/Source Owner 的新来源准入、同事务稳定映射、worker 执行栅栏、当前上传/去重/清理及幂等恢复 | 本人一条准确 Import Row 明确提交后，关联原生 Case Task；不是保存时自动解析 |
| ME-R1 | 原 Case Access/Evidence Review 对准确 primary-origin Attempt 的最小审核说明读取 | 指定真实 Reviewer 只能看该次提交对应的必要未核说明，不能扫描其他私有行 |
| CC-01 | 原 Classification Owner 的版本目录和独立人工类型决定 | 原 Case Approval 之后只追加分类记录，不改已批准 Case，正式类型与生产资格分开 |
| CC-02 | 原 Shared Owner 的新 typed 预览/发布/撤回与版本化历史读取 | 有效 Case Approval、类型决定和独立 Human Display 确认共同成立，才发布新版共享投影 |

P-R2-01～05 仍为本包建议：unknown→null、批准后确认类型、typed 失效隐藏/重新发布、profile 冲突处置，以及首期来源支持边界。必须明确接受或修改，不能由“方向通过”推断。

建议的裁决表达：先核验 APPROVAL_SCOPE_BINDING.json 的 SHA，再逐项列明批准/附条件批准/退回的单元与产品决定、允许的本地实现/隔离测试范围。若接受整个本地范围，可以在一次裁决中绑定四单元及五决定；后续依次通过工程测试和 Code Review，不反复请求同一已批准范围。此建议不是当前审批结果。

审批不包括真实模型、生产/4090、部署、Git 提交/推送/合并、AUTH/OIDC、新 Novelty/CIU/Ledger 或新 Pattern/Compatibility。已有真实 Source/Reviewer/Human Gate 不随工程合同批准而自动通过。

批准后的最小路径：1 条虚构但真实可读取的视频，经合法 Native 来源与原上传回执 → 明确提交 → 原 Native 解析（仅外部模型边界合成）→ 原 Evidence/Quality/Human Approval → 原 Owner 正式类型确认 → 独立共享确认。首条及严格负向通过后，才检查多行部分失败、双击、重登、故障和旧收据兼容，最后 Founder 统一验收。本轮不提前代做上述待批功能。
