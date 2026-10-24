# Verification and protection

先验证Draft2020-12 Schema和语义负向、原Owner/HTTP，再验证单原生完整链路，主要恢复通过后进入EX-S2。Focused失败/修复历史全部保留在`.local/evidence/case-native-r4-20261024/focused-*`，不能将早期失败记录改为PASS。

完整回归使用原 `tools/verify.py --mode full --jobs 6 --timeout 3600 --windows-short-temp`，运行前冻结源码和文档，最终summary/JUnit及source-state对比存放外置证据。只有实际完成且source-state一致才输出Ready。原1793项结果不替代本轮新代码。Node子测试日志单列，不把子测试重复计入Console pytest数量。FRP/verification原非JUnit结果保留原日志，不伪造JUnit。

`SOURCE_STATE.json`、`CURRENT_GIT_DIFF.patch`及完整文件SHA区分本轮R4和已保留R3/更早未提交增量。原Root/cc2/cxi HEAD、staged状态、历史976份文件、R2/R3审查包、模板及原24Task摘要在`PROTECTION_RESULT.json`重新验证。运行测试均使用隔离副本，没有对历史客户/Case/Persona/Receipt/Closure/Ledger进行测试写入。

评审包不含数据库、原始视频、Cookie、凭据或密钥。必要Human命令快照中的临时签名token仅在打包副本脱敏；原证据及其SHA本地保留，脱敏副本与原件身份分开记录。Manifest不自包含，SHA256SUMS包含Manifest，ZIP SHA外置；CRC/Manifest/SUMS逐一实际验证。

本地工程验收不替代ChatGPT独立工程/产品评审或Founder验收。真实模型、生产、4090、部署、AUTH/OIDC未执行；没有自动提交或推送。
