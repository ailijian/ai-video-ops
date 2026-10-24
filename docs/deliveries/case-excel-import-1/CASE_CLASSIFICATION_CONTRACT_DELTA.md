# Case视频内容类型与共享投影最小Delta

状态：PROPOSED / NOT_NATIVE_APPROVED / NOT_IMPLEMENTED。确有缺口：S19/S20/S33只含industry/profile；S21/S22明确无正式video_type分类。不得通过字段改名把制作形态当业务类型。

## CC-01：原Case Classification Owner的版本化补充

建议新增独立Case内容类型词典与SHA绑定的分类确认companion（版本名`case-content-type-catalog-v1.0`、`case-content-type-review-v1.0`均为候选）。不改旧case_v1.json/approval_receipt或既有case-classification-review-v1.0。原行业/profile接口继续原语义与原权限，新正式类型确认必须校验原Case Reviewer的当前grant，不能让普通投稿者通过原operator-label API写正式类型。

初始候选映射固定为：新闻体→news，人设型→persona，故事型→story，高转化型→conversion，其它→other，待判断→unknown。原始建议空值保留为空，不伪造已确认unknown。词典由原分类Owner版本化扩展；other说明仅是建议文本，不注册正式类型、Mix Style、Pattern或Compatibility。Case内容类型词典与CREATION_BATCH Creative Style Catalog可引用相同字面ID，但没有互相授予资格的效力。

确认候选最小字段：schema_version、Case/Attempt、candidate_sha256或确切approved_case_sha256、Import Row/notes SHA、原建议、catalog_ref(path/SHA/version)、confirmed_type_id、other_note、coherence_state、冲突处理与理由、当前Reviewer actor/grant_ref、operation_id、expected_parent_sha256、timestamp、immutable decision SHA。写前在原Case锁中重读来源和权限；错版本/未知字段/未知词典条目拒绝；重复操作恢复同一结果，不复写旧决定。

profile=news且type=story等只生成needs_human_review，不自动改成mix/news。建议Reviewer显式选择“保留观察到的两种分类并说明”“修正投稿建议”“继续待判断”；最终可接受的冲突处理集合须原Owner审查。未完成冲突处置不作为正式展示类型。类型确认只处理标签，不确认客户事实、Proof、兼容或媒体权。

## CC-02：原Shared Display Owner的独立增量

不能直接给旧receipt填值。建议发布新共享投影/receipt版本，保持v1.0/v1.1原字节和严格读取；新版本才可读取有效CC-01确认，绑定Case Approval Receipt、类型catalog/ref和decision SHA、当前publication head、原展示授权及安全白名单。先有准确Case批准，再有明确共享决定；两份独立Authority Receipt继续存在。

unknown/other仅在新Owner批准的展示规则下显示“待判断／其它·待分类”，不能看起来像正式已覆盖生产Style。没有有效类型确认，保留旧null/未分类语义。类型撤回、词典失效、Case/Attempt修订或来源变化使当前类型投影失效；历史共享receipt保留，不补写旧历史。批准Case之后的标签修正不得篡改批准Case或老Receipt。

CC-01需Case Classification与原Reviewer授权Owner审查；CC-02需Shared Display Owner独立审查。未来测试必须证明普通投稿者仅能保存建议、Reviewer越权/撤回/跨Attempt/旧SHA拒绝、重放不产生第二确认，旧批准/共享/Pattern/Compatibility不变。B0不签发任何决定或授权。
