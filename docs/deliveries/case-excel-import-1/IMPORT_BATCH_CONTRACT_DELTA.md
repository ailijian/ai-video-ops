# Excel Import Batch / Row / Intent 候选合同

状态：IB-01、SI-01 / PROPOSED / NOT_NATIVE_APPROVED / NOT_IMPLEMENTED。Owner为原Case Intake / Source / Task / Access，新增伴随记录不拥有Case Approval。

## 保存与解析必须分开

原create_group会被dispatch_groups送入既有Task admission（S02/S03）。所以“上传／校验／保存候选”不能简单复用该POST并期待它不调用模型。建议I1只产生私有预览；I2先在原Intake Owner下保存不可变Candidate；后续用户明确授权“提交原生解析”后才通过既有单Case gateway派发。三种提交方式、平台/媒体/合同资格决定哪些行可派发；文字-only与未核来源行不能靠占位URL进入Native。

## 建议最小身份与状态

候选schema名称：case-excel-import-intent-v1.0 / case-excel-import-row-v1.0 / case-excel-import-result-v1.0。建议放在原Intake治理下的隔离候选命名空间（确切存储路径待Owner审查），SQLite只投影进度。

Batch绑定server ID、node namespace/user_id、client_operation_id、XLSX/规则/模板registry SHA、解析器/校验策略版本、源文件大小、预览摘要、显式选中行集合、intent SHA、expected_parent SHA、时间。Row绑定稳定server row_id、external_case_key、sheet/物理行/字段key定位、raw/normalized数据SHA、submission_mode、manual-notes/ref、上传manifest/ref、原生映射Case/Attempt/Task（存在才填）、原Owner结果/拒绝码。

同一actor＋operation＋intent重放恢复原结果；相同operation不同输入必须409，不覆盖。物理行号是定位信息，不独占业务身份；同批Row ID及引用冻结后重放不重新分配。重排/修改文件需新预览/意图或显式新版本。跨批原视频去重继续按canonical video ID及真实media SHA，不能按external_case_key判断“新Case”。

建议候选状态：validation_failed / candidate_saved / pending_source / pending_evidence / analysis_authorization_required / native_task_linked / native_failed / duplicate_linked。它们不是Case生命周期或人审结论。整批/逐行进度只投影原写入；绝不由Import状态反写Case approved/shared。

保存时可按准确、已确认的合法行集合逐项持久化：每行先取得原锁/意图，再保存write-once结果并绑定准确目标，失败项保留差额。首次只允许明确选择“保存已通过校验的行”，不自动吞错；损坏ZIP/身份/表头等整文件错误阻断全部。崩溃后查原Row/意图和原Task结果，再完成缺失步骤；外部模型结果未知不自动重发。部分保存/取消/重新上传策略需Owner审批；未批准前不实施写入。

## SI-01 来源适配缺口

V0.3允许只有真实媒体文件名或纯文字；现有source_upload与approve_case都要求抖音URL/平台ID。最小范围先保存独立Source Candidate及真实上传引用，保持pending_source，不能伪造平台ID。原Source Owner需审查本地/其它平台身份、引用和私有媒体协议之后才允许其原生解析；原Case Approval Owner若未支持这种来源，继续阻断批准。为保持模板体验不能静默把无URL行改成“非法模板”丢弃，也不能假称当前Native已能批准它。

media_filename只允许文件基名，拒绝绝对路径、盘符、UNC、父目录、任何路径分隔、NUL、设备名、ADS与编码后的穿越；重名且字节不同的上传必须显式消歧。服务端将文件名解析到本用户真实上传manifest，校验upload ID、bytes SHA、来源、当前权限/有效期及是否已消费，客户端不能提交“已存在/已批准”的可信标记。不会扫描服务器磁盘找同名文件，也不取“最新文件”。

## 权限与输入防护候选

沿用Session、CSRF、原Source/Case锁与私有投稿归属；上传者可读本人的Import，不因重复来源获得他人私有内容。普通投稿者不能确认正式类型、Evidence、Case批准或共享；指定Reviewer的有效grant在实际决定时再查。大批草稿不放宽Task/GPU安全容量。

建议首期上限（未获机器批准、未实测吞吐）：XLSX5MiB、最多10案例/200分段/10许可行、ZIP256成员/32MiB总解压/单成员8MiB/压缩比100、单元格文本8000字符、XML节点及CPU/解析时间预算。格式预留101行不是正式101条容量。具体阈值/错误码/依赖版本由原Owner审查后冻结。

顺序：先验证认证与文件体限额；验证ZIP签名、CRC/成员唯一、压缩/解压预算、路径、加密、宏/ActiveX/OLE/嵌入对象/外部连接；安全XML禁止DTD/实体；只接受完整8表、B3身份、三个正式表的第3/4行固定定义；按key校验顺序/缺失/重复/额外字段；第5行后跳过完全空行。公式单元格（含共享/数组）、DDE、外部关系拒绝，数据验证的常量下拉元数据仅按冻结白名单接受；普通source_url只读文本，经正式resolver，不执行Excel超链接。此严格外部关系策略也会拒绝自动生成的hyperlink relationship，UI需提示以普通文本粘贴，不能在实现时静默放开。

五个非输入表仅作身份/安全扫描，不解析业务行；DEMO表中的完整示例不进入候选列表，DEMO-编号即使复制进正式表也拒绝。跨表外键、连续唯一序号、许可最多1行都在服务端校验。未声明权利=unknown，既有原生Gate照常。

本提案不是已批准Schema/API：未知字段/版本应fail closed，不利用旧Pydantic忽略额外字段来“接纳”Excel。所有新错误码、记录路径及write恢复合同在I2前必须通过原Owner审核和精确授权。
