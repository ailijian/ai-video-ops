# AIVO FRP Dynamic Public IPv4 Guard V1

仅部署在 RTX4090 Production Host。Guard 管理 FRPS 控制通道 `47.116.109.155:7000` 的单个公网 IPv4 白名单，不开放应用隧道端口 18000，不修改 frpc.toml、token、TLS、Nginx 或业务数据。

## 文件与安全边界

| 文件 | 位置 |
| --- | --- |
| Guard | `E:\AI-Video-Ops-Network\frp-ip-guard.ps1` |
| 非敏感配置 | `E:\AI-Video-Ops-Config\frp-ip-guard.json` |
| JSON 行日志 | `E:\AI-Video-Ops-Logs\frp-ip-guard.log` |
| 本机状态及互斥锁 | `E:\AI-Video-Ops-Logs\frp-ip-guard-state\` |
| 安装器 | 本目录 `install-frp-ip-guard.ps1` |

配置模板不包含真实地域/安全组。此次用户确认的外部配置为 `cn-shanghai` / `sg-uf61unqey0n2ft005unq`；安装时仍需核对它绑定的是公网 IP `47.116.109.155` 的 ECS 实例。

管理范围同时满足：Ingress、TCP、7000/7000、Accept，以及大小写精确的 Description：`AI Video Ops FRPS Control - RTX4090`。其他规则不修改。V1 支持 VPC 安全组；经典网络或规则形态异常会拒绝运行，需要单独审核。

执行顺序：检测公网 IPv4 → 查询所有分页 → 如需则添加当前 /32（Priority 1）→ 再查询确认 → TCP 7000 连通 → 只按规则 ID 删除旧的自有规则 → 启动/恢复 FRPC → 最多 30 秒验证服务、子进程及公网 health。失败不会删除尚未替代的旧规则、放宽来源或开启别的端口。新增成功但后续失败的 /32 可以保留，下一次执行会重新检查。

同 IP 已存在则不修改安全组；运行中且 IP 未变则不重启 FRPC。停止的服务在安全组/TCP 确认后启动。状态文件保留中断后的重启意图，避免首次更新后中途退出无法恢复。进程存在但 health 失败时记录失败，不不断重启同一 IP 下的健康进程。

## 一次性人工步骤：阿里云 RAM

1. 在阿里云 RAM 创建独立用户，例如 `aivo-frp-guard`，用于程序访问。不使用主账号 AccessKey，不授予 `AliyunECSFullAccess`。
2. 创建自定义权限策略。使用同目录 `ram-policy.json.example`，仅保留三个操作：`ecs:DescribeSecurityGroupAttribute`、`ecs:AuthorizeSecurityGroup`、`ecs:RevokeSecurityGroup`。将 Resource 填为：

   ```text
   acs:ecs:cn-shanghai:<主账号UID>:securitygroup/sg-uf61unqey0n2ft005unq
   ```

   主账号 UID 可从账号基本信息查看（不是密钥）；也可按官方安全组策略示例将账号段写 `*`，但必须保持具体地域和这个安全组 ID，不能把整个 Resource 写成 `*`。策略限制安全组，Description 的精确归属检查由脚本负责，并非云端 RAM 能按描述限定授权。
3. 仅给该 RAM 用户绑定此自定义策略。由用户在 RAM 控制台创建其 AccessKey；不要把 ID/Secret 发到聊天、放到仓库、脚本参数或日志里。
4. 在 4090 的专用 Windows 用户内交互式配置 CLI（见下节）。不在开发机配置或代建云凭证。

官方依据：[指定安全组的 RAM 策略](https://help.aliyun.com/zh/ram/manage-ecs-security-groups-within-an-alibaba-cloud-account)、[按规则 ID 删除入站规则](https://help.aliyun.com/en/ecs/developer-reference/api-ecs-2014-05-26-revokesecuritygroup)。如果精确策略在真实 API 上拒绝，不扩大到 ECS 全权限，先核对策略与资源 ARN。

## 一次性人工步骤：4090 的 CLI 与 Windows 身份

1. 用 Windows 设置/计算机管理创建专用普通用户，例如 `AivoFrpGuard`，设置安全密码并首次登录以建立用户 Profile。不要使用 Administrator 或 SYSTEM 作为 Guard 身份。
2. 安装官方 Windows CLI：从 [阿里云 CLI 官方安装文档](https://help.aliyun.com/zh/cli/install-update-alibaba-cloud-cli)下载 Windows amd64 ZIP，解压到 `C:\AliyunCLI`，使 `C:\AliyunCLI\aliyun.exe` 存在。无需从其他网站安装。
3. 在这个专用用户的 PowerShell 中执行（不是管理员账号的 Profile）：

   ```powershell
   & 'C:\AliyunCLI\aliyun.exe' version
   & 'C:\AliyunCLI\aliyun.exe' configure --mode AK --profile aivo-frp
   ```

   按交互提示输入独立 RAM 用户的凭证，地域填 `cn-shanghai`；不要把凭证写进命令行。CLI 保存在该用户的 `.aliyun\config.json`，该文件包含秘密，只存在新主机本地。
4. CLI >= 3.3 使用插件，仍在该专用用户下安装 ECS 插件：

   ```powershell
   & 'C:\AliyunCLI\aliyun.exe' plugin install --names ecs
   & 'C:\AliyunCLI\aliyun.exe' plugin list
   ```

   Guard 检查当前 API 帮助的参数契约；不会自动下载安装插件，不输出 CLI 原始错误。保留旧 CLI API 命令兼容适配，但新安装建议使用官方当前版本。[插件文档](https://help.aliyun.com/en/cli/managing-and-using-cli-plugins)、[交互式 AK 配置](https://help.aliyun.com/zh/cli/ak-credential)。

## 4090 安装服务与计划任务

把本目录脚本/模板复制到 4090，例如 `E:\AI-Video-Ops-Network\setup\`；不要复制开发机的用户凭证、frpc.toml 或整套开发工作树。旧开发机的 `-PrepareOnly` 产物不能表示新主机已安装。

在 4090 上先记录 `hostname`。检查并停止已有手工 frpc 或已有 FRPC 服务；不要停止 Console。安装器在 FRPC 仍运行时拒绝更改服务绑定。清除/禁用历史 FRPC 自启动任务须由操作者核对，不能有第二个启动入口。

在管理员 PowerShell 中运行，`-ExpectedComputerName` 必须是此时真实 hostname：

```powershell
$guardAccount = "$env:COMPUTERNAME\AivoFrpGuard"
$guardCredential = Get-Credential -UserName $guardAccount
& 'E:\AI-Video-Ops-Network\setup\install-frp-ip-guard.ps1' `
  -ExpectedComputerName $env:COMPUTERNAME `
  -UserName $guardAccount -TaskCredential $guardCredential `
  -RegionId cn-shanghai -SecurityGroupId sg-uf61unqey0n2ft005unq `
  -WinSWPath '<现有已验证的WinSW.exe绝对路径>'
$guardCredential = $null
```

有且只有一个 WinSW FRPC 服务时复用其名称/二进制/配置，不另建同类服务，`-WinSWPath` 可以省略。没有时需要已有 WinSW 二进制，并确认 `E:\AI-Video-Ops-Network\frpc.exe` 和 `frpc.toml` 已存在；才创建 `AIVO-FRPC`。不下载/升级 FRP，不生成 token。

服务设 Manual，禁用旧的 SCM/WinSW 自动重启策略，Guard 负责恢复；原 XML/服务安全描述有外部备份。只给专用 Windows 用户查询/启动/停止此服务的权限，不给修改服务配置权限。脚本和配置只读，独立日志/状态可写，CLI 凭证目录只对专用身份、SYSTEM、管理员开放。

任务 `AIVO-FRP-IP-Guard`：开机延迟 30 秒、每 10 分钟、IgnoreNew、最长 2 分钟。Password 登录类型支持用户未登录及网络访问；Windows 密码仅传给 Task Scheduler 注册，不写入文件。遇到域策略禁止“作为批处理作业登录”时，必须由 Windows 管理员为此用户处理该权限，不改成 SYSTEM/S4U 规避。

安装器不直接请求云 API，也不直接启动 FRPC；注册后的任务会开始周期执行。因此凭证未完成前只使用 `-PrepareOnly`，不要注册生产任务。安装完成先以同一专用账号执行只读检查，确认日志正常。

## Dry-run 与首次运行

以专用 Windows 用户运行；`-ServiceName` 填安装器报告的实际复用名称：

```powershell
& 'E:\AI-Video-Ops-Network\frp-ip-guard.ps1' -ServiceName AIVO-FRPC -DryRun
```

`-DryRun` / `-Preflight` 都只检测 IP、查询 SG、检查服务配置和 TCP；不添加/删除规则，不启动/重启服务，不写服务状态。仅记录安全日志/互斥锁。`DRY_RUN_ADD_REQUIRED` 是计划，不是生产连通 PASS。

首次正式执行可由任务调度器启动该任务，随后观察日志与上次结果：

```powershell
Start-ScheduledTask -TaskName 'AIVO-FRP-IP-Guard'
Get-ScheduledTaskInfo -TaskName 'AIVO-FRP-IP-Guard'
Get-Content 'E:\AI-Video-Ops-Logs\frp-ip-guard.log' -Tail 15
```

首次基线通过后，连续运行 10 次应不产生 SG 变更/FRPC 重启。任务启动后不要手工以第二个账号运行变更模式。

## 故障与边界

| 代码 | 处理 |
| --- | --- |
| `ALIYUN_CLI_MISSING` / `ALIYUN_ECS_PLUGIN_REQUIRED` | 在专用用户下安装官方 CLI/插件 |
| `ALIYUN_PROFILE_REQUIRED` / `ALIYUN_AUTH_FAILED` | 核对同一 Windows Profile 和最小 RAM 策略，不输出配置内容 |
| `GUARD_CONFIG_REQUIRED` | 填真实地域/安全组 ID，不猜测 |
| `UNMANAGED_7000_RULES_PRESENT` | 用户审核历史规则；脚本不清理它们 |
| `HIGH_RISK_FRPS_RULE_DETECTED` | 用户审核非自有公网全开放规则；脚本不擅自删除 |
| `NEW_RULE_VERIFICATION_FAILED` | 保留旧规则；可能遇到同 tuple 的手工规则，不把它静默认领 |
| `FRPS_7000_UNREACHABLE` | 保留旧规则；排查服务/防火墙，不放宽安全组 |
| `FRPC_HEALTH_FAILED` | 查看 FRPC/Console 的现有日志；不输出 token，也不以开放端口恢复 |

公网发生变化后，最多下一次 10 分钟巡检发现；开机首次巡检延迟 30 秒。Guard 不保证 ISP/NAT、云 FRPS 故障或 Console 停止时仍能恢复网站。真实 SG 调用、Windows 服务/任务、重启开机与公网 health 必须在 4090 配置凭证后验收。

## 离线回归

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\frp-ip-guard\tests.ps1
```

Mock 云接口和服务，不修改安全组/Production。涵盖顺序、失败保留、10 次幂等、归属隔离、IPv6 拒绝、CLI 契约、日志脱敏、任务 XML、Windows 5.1 原生命令转义/超时。
