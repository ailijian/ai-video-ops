[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'frp-ip-guard.ps1')
. (Join-Path $PSScriptRoot 'install-frp-ip-guard.ps1')
$script:OriginalAliyun = ${function:Invoke-GuardAliyun}
$script:OriginalRules = ${function:Get-GuardRules}
$script:OriginalIp = ${function:Get-GuardPublicIPv4}
$script:OriginalNative = ${function:Invoke-GuardNative}
$script:OriginalProcess = ${function:Get-GuardFrpcProcessRunning}
$script:OriginalBinding = ${function:Get-GuardFrpcBinding}
$script:OriginalAction = ${function:Invoke-GuardFrpcAction}
$script:TestRoot = Join-Path ([IO.Path]::GetTempPath()) ('aivo-frp-guard-tests-' + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $script:TestRoot)
$script:Passed = 0
$script:Config = [pscustomobject]@{
    regionId = 'cn-shanghai'; securityGroupId = 'sg-testonly'; frpsHost = '47.116.109.155'; frpsPort = 7000
    ruleDescription = 'AI Video Ops FRPS Control - RTX4090'; aliyunProfile = 'aivo-frp'
}

function Assert-GuardTest {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw ('ASSERTION_FAILED: ' + $Message) }
}
function Assert-GuardThrows {
    param([scriptblock]$Action, [string]$Code)
    $caught = ''
    try { & $Action | Out-Null } catch { $caught = $_.Exception.Message }
    Assert-GuardTest ($caught -ceq $Code) ('expected ' + $Code + ', got ' + $caught)
}
function Invoke-GuardTest {
    param([string]$Name, [scriptblock]$Body)
    & $Body
    $script:Passed++
    Write-Output ('PASS: ' + $Name)
}
function New-Rule {
    param([string]$Ip = '203.0.113.20/32', [string]$Id = 'sgr-current', [string]$Description = $script:Config.ruleDescription)
    return [pscustomobject]@{ Direction = 'ingress'; IpProtocol = 'tcp'; PortRange = '7000/7000'; Policy = 'Accept'; Priority = 1
        SourceCidrIp = $Ip; SecurityGroupRuleId = $Id; Description = $Description; NicType = 'intranet' }
}
function Reset-GuardMock {
    param([object[]]$Rules = @((New-Rule)), [string]$PreviousIp = '203.0.113.20', [string]$Service = 'Running')
    $directory = Join-Path $script:TestRoot ([guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $directory)
    [void](New-Item -ItemType Directory -Path (Join-Path $directory 'frp-ip-guard-state'))
    $script:Mock = @{ Rules = @($Rules); Ip = '203.0.113.20'; Service = $Service; Tcp = $true; Health = $true; Process = $true
        AuthorizeFailure = $false; VerifyFailure = $false; QueryFailure = $false; ServiceFailure = $false; CleanupFailure = $false
        Calls = (New-Object 'System.Collections.Generic.List[string]'); Log = (Join-Path $directory 'guard.log')
        NativeCalls = (New-Object 'System.Collections.Generic.List[object]'); NativeExit = 0; NativeOutput = '{}'; NativeError = ''; NativeTimeout = $false }
    if ($PreviousIp) { Save-GuardState (Join-Path $directory 'frp-ip-guard-state\frp-ip-guard.state.json') $PreviousIp }
    $script:GuardDeadline = $null
}
function Get-GuardPublicIPv4 { return (ConvertTo-GuardPublicIPv4 $script:Mock.Ip) }
function Get-GuardRules {
    param($Config)
    $script:Mock.Calls.Add('Describe')
    if ($script:Mock.QueryFailure) { throw 'ALIYUN_API_FAILED' }
    return ,$script:Mock.Rules
}
function Invoke-GuardAliyun {
    param($Config, $Operation, $Cidr = '', $RuleId = '', $NextToken = '')
    $script:Mock.Calls.Add($Operation)
    if ($Operation -eq 'Authorize') {
        if ($script:Mock.AuthorizeFailure) { throw 'ALIYUN_API_FAILED' }
        if (-not $script:Mock.VerifyFailure -and @($script:Mock.Rules | Where-Object { $_.SourceCidrIp -eq $Cidr }).Count -eq 0) {
            $script:Mock.Rules += New-Rule $Cidr 'sgr-new'
        }
    } elseif ($Operation -eq 'Revoke') {
        if ($script:Mock.CleanupFailure) { throw 'ALIYUN_API_FAILED' }
        $script:Mock.Rules = @($script:Mock.Rules | Where-Object { $_.SecurityGroupRuleId -cne $RuleId })
    }
    return [pscustomobject]@{ RequestId = 'test' }
}
function Test-GuardTcp7000 { param($Config); $script:Mock.Calls.Add('TCP'); return $script:Mock.Tcp }
function Get-GuardFrpcBinding { param($Name); return [pscustomobject]@{ Name = $Name; Executable = 'E:\frpc.exe' } }
function Get-GuardFrpcState { param($Name); return $script:Mock.Service }
function Get-GuardFrpcProcessRunning { param($Binding); return $script:Mock.Process }
function Invoke-GuardFrpcAction {
    param($Name, $Action)
    $script:Mock.Calls.Add($Action)
    if ($script:Mock.ServiceFailure) { throw 'FRPC_SERVICE_STATE_UNEXPECTED' }
    $script:Mock.Service = 'Running'
}
function Wait-GuardFrpcHealth { param($Binding, $Action); $script:Mock.Calls.Add('Health'); return $script:Mock.Health }
function Start-Sleep { param($Seconds) }
function Invoke-GuardNative {
    param($FilePath, $Arguments, $TimeoutSeconds = 10)
    $script:Mock.NativeCalls.Add(@($Arguments))
    if ($script:Mock.NativeTimeout) { throw 'GUARD_NATIVE_TIMEOUT' }
    return [pscustomobject]@{ ExitCode = $script:Mock.NativeExit; Stdout = $script:Mock.NativeOutput; Stderr = $script:Mock.NativeError }
}
function Run-Guard { return (Invoke-AivoFrpGuard $script:Config $script:Mock.Log 'AIVO-FRPC') }
function Test-NoRemovalOrService {
    Assert-GuardTest (-not ($script:Mock.Calls -contains 'Revoke')) 'old rule must be preserved'
    Assert-GuardTest (-not ($script:Mock.Calls -contains 'Start') -and -not ($script:Mock.Calls -contains 'Restart')) 'no service action before safe SG/TCP result'
}

Invoke-GuardTest 'same IP x10: zero security-group mutations and zero restarts' {
    Reset-GuardMock
    1..10 | ForEach-Object { Assert-GuardTest ((Run-Guard).frpcAction -ceq 'None') 'unchanged service not restarted' }
    Assert-GuardTest (-not ($script:Mock.Calls -contains 'Authorize') -and -not ($script:Mock.Calls -contains 'Revoke')) 'no SG mutation'
    Assert-GuardTest ($script:Mock.Rules.Count -eq 1) 'no rule accumulation'
}
Invoke-GuardTest 'changed IP: add -> requery -> TCP -> cleanup -> restart; second run idempotent' {
    Reset-GuardMock @((New-Rule '203.0.113.10/32' 'sgr-old')) '203.0.113.10'
    Assert-GuardTest ((Run-Guard).frpcAction -ceq 'Restart') 'IP change restarts'
    $calls = $script:Mock.Calls.ToArray()
    Assert-GuardTest (($calls -join ',') -match 'Describe,Authorize,Describe,TCP,Describe,Revoke,Describe,Restart,Health') 'strict safe ordering'
    $mutations = @($calls | Where-Object { $_ -in @('Authorize', 'Revoke', 'Restart') }).Count
    Assert-GuardTest ((Run-Guard).frpcAction -ceq 'None') 'second run no restart'
    Assert-GuardTest (@($script:Mock.Calls | Where-Object { $_ -in @('Authorize', 'Revoke', 'Restart') }).Count -eq $mutations) 'second run no mutation'
}
Invoke-GuardTest 'authorize fails: old rule preserved' {
    Reset-GuardMock @((New-Rule '203.0.113.10/32' 'sgr-old'))
    $script:Mock.AuthorizeFailure = $true
    Assert-GuardThrows { Run-Guard } 'ALIYUN_API_FAILED'; Test-NoRemovalOrService
    Assert-GuardTest ($script:Mock.Rules[0].SecurityGroupRuleId -ceq 'sgr-old') 'old still exists'
}
Invoke-GuardTest 'new-rule verification fails: old preserved' {
    Reset-GuardMock @((New-Rule '203.0.113.10/32' 'sgr-old'))
    $script:Mock.VerifyFailure = $true
    Assert-GuardThrows { Run-Guard } 'NEW_RULE_VERIFICATION_FAILED'; Test-NoRemovalOrService
}
Invoke-GuardTest '7000 unreachable: old preserved, no service start' {
    Reset-GuardMock @((New-Rule '203.0.113.10/32' 'sgr-old'))
    $script:Mock.Tcp = $false
    Assert-GuardThrows { Run-Guard } 'FRPS_7000_UNREACHABLE'; Test-NoRemovalOrService
    Assert-GuardTest ($script:Mock.Rules.Count -eq 2) 'new and old retained for retry'
}
Invoke-GuardTest 'two stale managed rules cleaned only after verification' {
    Reset-GuardMock @((New-Rule), (New-Rule '203.0.113.10/32' 'sgr-olda'), (New-Rule '203.0.113.11/32' 'sgr-oldb'))
    [void](Run-Guard)
    Assert-GuardTest (@($script:Mock.Calls | Where-Object { $_ -eq 'Revoke' }).Count -eq 2) 'both stale removed'
    Assert-GuardTest ($script:Mock.Calls.IndexOf('TCP') -lt $script:Mock.Calls.IndexOf('Revoke')) 'verified before cleanup'
}
Invoke-GuardTest 'unmanaged 7000 and unrelated ports untouched' {
    $otherPort = New-Rule '203.0.113.90/32' 'sgr-ssh' 'SSH'; $otherPort.PortRange = '22/22'
    Reset-GuardMock @((New-Rule), (New-Rule '203.0.113.90/32' 'sgr-other' 'Other FRP Client'), $otherPort)
    [void](Run-Guard)
    Assert-GuardTest ($script:Mock.Rules.Count -eq 3 -and -not ($script:Mock.Calls -contains 'Revoke')) 'unowned retained'
    Assert-GuardTest ((Get-Content $script:Mock.Log -Raw) -match 'UNMANAGED_7000_RULES_PRESENT') 'warning recorded'
}
Invoke-GuardTest 'unmanaged same tuple is not silently adopted' {
    Reset-GuardMock @((New-Rule '203.0.113.20/32' 'sgr-other' 'Historical manual rule'))
    Assert-GuardThrows { Run-Guard } 'NEW_RULE_VERIFICATION_FAILED'; Test-NoRemovalOrService
}
Invoke-GuardTest 'unmanaged 0.0.0.0/0: warn but untouched' {
    Reset-GuardMock @((New-Rule), (New-Rule '0.0.0.0/0' 'sgr-world' 'Historical'))
    [void](Run-Guard)
    Assert-GuardTest ($script:Mock.Rules.Count -eq 2) 'unmanaged world not changed'
    Assert-GuardTest ((Get-Content $script:Mock.Log -Raw) -match 'HIGH_RISK_FRPS_RULE_DETECTED') 'high risk warning'
}
Invoke-GuardTest 'managed world rule removed only after new /32 verified and connected' {
    Reset-GuardMock @((New-Rule '0.0.0.0/0' 'sgr-world')) ''
    [void](Run-Guard)
    Assert-GuardTest ($script:Mock.Rules.Count -eq 1 -and $script:Mock.Rules[0].SourceCidrIp -ceq '203.0.113.20/32') 'narrow /32 remains'
    Assert-GuardTest ($script:Mock.Calls.IndexOf('TCP') -lt $script:Mock.Calls.IndexOf('Revoke')) 'safe replacement'
}
Invoke-GuardTest 'IPv6/private IP/HTML rejected, no cloud mutation' {
    foreach ($ip in @('2001:db8::1', '127.0.0.1', '10.1.2.3', '192.168.1.2', '100.64.0.1', '224.0.0.1', '<html>error</html>')) {
        Reset-GuardMock; $script:Mock.Ip = $ip
        Assert-GuardThrows { Run-Guard } 'PUBLIC_IPV4_INVALID'
        Assert-GuardTest ($script:Mock.Calls.Count -eq 0) 'invalid IP before query'
    }
}
Invoke-GuardTest 'unexpected owned rule shape fails closed' {
    foreach ($change in @(@('Priority', 2), @('NicType', 'internet'), @('PortRange', '18000/18000'), @('Direction', 'egress'), @('SourceCidrIp', '203.0.113.0/24'))) {
        $rule = New-Rule; $rule.($change[0]) = $change[1]
        Reset-GuardMock @($rule)
        Assert-GuardThrows { Run-Guard } 'SG_RULE_STATE_UNEXPECTED'; Test-NoRemovalOrService
    }
    $rule = New-Rule; Add-Member -InputObject $rule -NotePropertyName SourceGroupId -NotePropertyValue 'sg-other'
    Reset-GuardMock @($rule); Assert-GuardThrows { Run-Guard } 'SG_RULE_STATE_UNEXPECTED'
}
Invoke-GuardTest 'query failure fails closed' {
    Reset-GuardMock; $script:Mock.QueryFailure = $true
    Assert-GuardThrows { Run-Guard } 'ALIYUN_API_FAILED'; Test-NoRemovalOrService
}
Invoke-GuardTest 'stopped service starts only after SG/TCP; running unchanged never restarts' {
    Reset-GuardMock -Service 'Stopped'
    Assert-GuardTest ((Run-Guard).frpcAction -ceq 'Start') 'service started'
    Assert-GuardTest ($script:Mock.Calls.IndexOf('TCP') -lt $script:Mock.Calls.IndexOf('Start')) 'connectivity precedes start'
}
Invoke-GuardTest 'interrupted first restart keeps pending intent after stale cleanup' {
    Reset-GuardMock @((New-Rule '203.0.113.10/32' 'sgr-old')) ''
    $script:Mock.ServiceFailure = $true
    Assert-GuardThrows { Run-Guard } 'FRPC_SERVICE_STATE_UNEXPECTED'
    $script:Mock.ServiceFailure = $false
    Assert-GuardTest ((Run-Guard).frpcAction -ceq 'Restart') 'retry recovers pending restart even with current SG'
}
Invoke-GuardTest 'health failure does not widen SG or endlessly restart unchanged process' {
    Reset-GuardMock @((New-Rule '203.0.113.10/32' 'sgr-old')) ''
    $script:Mock.Health = $false
    Assert-GuardThrows { Run-Guard } 'FRPC_HEALTH_FAILED'
    Assert-GuardThrows { Run-Guard } 'FRPC_HEALTH_FAILED'
    Assert-GuardTest (@($script:Mock.Calls | Where-Object { $_ -eq 'Restart' }).Count -eq 1) 'only initial IP-change restart'
    Assert-GuardTest ($script:Mock.Rules.Count -eq 1 -and $script:Mock.Rules[0].SourceCidrIp -notmatch '/0$') 'no broadening'
}
Invoke-GuardTest 'dry-run: zero mutation, cleanup, service, state write' {
    Reset-GuardMock @((New-Rule '203.0.113.10/32' 'sgr-old')) ''
    $result = Invoke-AivoFrpGuard $script:Config $script:Mock.Log 'AIVO-FRPC' -ReadOnly
    Assert-GuardTest ($result.addRequired -and $result.securityGroupMutations -eq 0 -and $result.frpcRestarts -eq 0) 'safe plan'
    Test-NoRemovalOrService
    Assert-GuardTest (-not ($script:Mock.Calls -contains 'Authorize')) 'dry run no add'
    Assert-GuardTest (-not (Test-Path (Join-Path (Split-Path $script:Mock.Log) 'frp-ip-guard-state\frp-ip-guard.state.json'))) 'state not written'
}
Invoke-GuardTest 'CLI old/new API contracts use explicit profile, region, rule IDs and exact description' {
    foreach ($modern in @($false, $true)) {
        Reset-GuardMock
        $script:GuardCliModern = $modern; $script:GuardCliPath = 'fake.exe'; $script:GuardRegionFlag = '--biz-region-id'
        & $script:OriginalAliyun $script:Config 'Authorize' -Cidr '203.0.113.20/32' | Out-Null
        & $script:OriginalAliyun $script:Config 'Revoke' -RuleId 'sgr-old' | Out-Null
        $authorize = $script:Mock.NativeCalls[0]; $revoke = $script:Mock.NativeCalls[1]
        Assert-GuardTest ($authorize -contains 'aivo-frp' -and $authorize -contains 'cn-shanghai' -and $authorize -contains 'sg-testonly') 'scope/profile explicit'
        Assert-GuardTest ($authorize -contains '7000/7000' -and $authorize -contains '203.0.113.20/32' -and $authorize -contains $script:Config.ruleDescription) 'exact authorized scope'
        Assert-GuardTest ($revoke -contains 'sgr-old' -and -not ($revoke -contains '203.0.113.20/32')) 'revoke by ID only'
        Assert-GuardTest ($revoke -contains $(if ($modern) { '--security-group-rule-id' } else { '--SecurityGroupRuleId.1' })) 'proper array flag'
    }
}
Invoke-GuardTest 'API timeout/auth errors redacted; old rule preserved' {
    Reset-GuardMock; $script:GuardCliModern = $false; $script:GuardCliPath = 'fake.exe'
    $script:Mock.NativeTimeout = $true
    Assert-GuardThrows { & $script:OriginalAliyun $script:Config 'Describe' } 'ALIYUN_API_TIMEOUT_OR_FAILED'
    $script:Mock.NativeTimeout = $false; $script:Mock.NativeExit = 1; $script:Mock.NativeError = 'InvalidAccessKey Secret=SENTINEL_DO_NOT_LOG'
    Assert-GuardThrows { & $script:OriginalAliyun $script:Config 'Describe' } 'ALIYUN_AUTH_FAILED'
    Write-GuardLog $script:Mock.Log 'ALIYUN_AUTH_FAILED'
    Assert-GuardTest ((Get-Content $script:Mock.Log -Raw) -notmatch 'SENTINEL|Secret|InvalidAccessKey') 'no sensitive native text in log'
}
Invoke-GuardTest 'public IPv4 fallback is IPv4/direct-only and bounded' {
    Reset-GuardMock; $script:Mock.NativeOutput = '203.0.113.20'
    Assert-GuardTest ((& $script:OriginalIp) -ceq '203.0.113.20') 'IPv4 normalized'
    $arguments = $script:Mock.NativeCalls[0]
    Assert-GuardTest ($arguments -contains '-4' -and $arguments -contains '--noproxy' -and $arguments -contains '*' -and $arguments -contains '--max-time') 'no proxy + bounded request'
    $script:Mock.NativeOutput = '2001:db8::1'; $script:Mock.NativeCalls.Clear()
    Assert-GuardThrows { & $script:OriginalIp } 'PUBLIC_IPV4_DETECTION_FAILED'
    Assert-GuardTest ($script:Mock.NativeCalls.Count -eq 2 -and $script:Mock.NativeCalls[1] -contains 'https://ifconfig.me/ip') 'IPv6 first response uses fallback, both fail closed'
}
Invoke-GuardTest 'full SG pagination, mismatched scope and classic network rejected' {
    Reset-GuardMock
    $script:GuardCliModern = $false; $script:GuardCliPath = 'fake.exe'
    $script:Mock.NativeOutput = '{"SecurityGroupId":"sg-testonly","RegionId":"cn-shanghai","VpcId":"vpc-test","Permissions":{"Permission":[]}}'
    # Use real adapters together for JSON parsing and API scope checks.
    $mockAliyun = ${function:Invoke-GuardAliyun}
    try {
        Set-Item Function:Invoke-GuardAliyun $script:OriginalAliyun
        $emptyRules = & $script:OriginalRules $script:Config
        Assert-GuardTest ($emptyRules.Count -eq 0) 'empty VPC SG accepted'
        $script:Mock.NativeOutput = '{"SecurityGroupId":"sg-wrong","RegionId":"cn-shanghai","VpcId":"vpc-test","Permissions":{"Permission":[]}}'
        Assert-GuardThrows { & $script:OriginalRules $script:Config } 'SG_RESPONSE_SCOPE_INVALID'
        $script:Mock.NativeOutput = '{"SecurityGroupId":"sg-testonly","RegionId":"cn-shanghai","Permissions":{"Permission":[]}}'
        Assert-GuardThrows { & $script:OriginalRules $script:Config } 'SG_NETWORK_UNSUPPORTED'
        $script:Mock.NativeOutput = '{"SecurityGroupId":"sg-testonly","RegionId":"cn-shanghai","VpcId":"vpc-test","NextToken":"repeat","Permissions":{"Permission":[]}}'
        Assert-GuardThrows { & $script:OriginalRules $script:Config } 'SG_PAGINATION_INVALID'
        Assert-GuardTest ($script:Mock.NativeCalls[-1] -contains '--NextToken') 'pagination token supplied'
    } finally { Set-Item Function:Invoke-GuardAliyun $mockAliyun }
}
Invoke-GuardTest 'config has no secret fields, blank IDs fail closed' {
    $template = Join-Path $PSScriptRoot 'frp-ip-guard.json.example'
    Assert-GuardThrows { Read-GuardConfig $template } 'GUARD_CONFIG_REQUIRED'
    $configCopy = $script:Config | ConvertTo-Json | ConvertFrom-Json
    Add-Member -InputObject $configCopy -NotePropertyName AccessKeySecret -NotePropertyValue 'SENTINEL_DO_NOT_LOG'
    $configPath = Join-Path $script:TestRoot 'bad-config.json'
    [IO.File]::WriteAllText($configPath, ($configCopy | ConvertTo-Json))
    Assert-GuardThrows { Read-GuardConfig $configPath } 'GUARD_CONFIG_INVALID'
}
Invoke-GuardTest 'task/service contracts: boot delay, 10 minutes, Password logon, IgnoreNew, two-minute timeout, Manual' {
    [xml]$task = New-GuardTaskXml 'S-1-5-21-1-2-3-1001' 'Existing-Frpc'
    Assert-GuardTest ($task.Task.Triggers.BootTrigger.Delay -ceq 'PT30S') 'startup delay'
    Assert-GuardTest ($task.Task.Triggers.TimeTrigger.Repetition.Interval -ceq 'PT10M') 'repeat'
    Assert-GuardTest ($task.Task.Principals.Principal.LogonType -ceq 'Password' -and $task.Task.Principals.Principal.RunLevel -ceq 'LeastPrivilege') 'logged-out network-capable identity'
    Assert-GuardTest ($task.Task.Settings.MultipleInstancesPolicy -ceq 'IgnoreNew' -and $task.Task.Settings.ExecutionTimeLimit -ceq 'PT2M') 'bounded and single instance'
    Assert-GuardTest ($task.Task.Actions.Exec.Arguments -match 'Existing-Frpc' -and $task.Task.Actions.Exec.Arguments -notmatch 'password|AccessKey|token') 'actual reused service and no secret arguments'
    [xml]$service = New-GuardServiceXml
    Assert-GuardTest ($service.service.startmode -ceq 'Manual' -and $service.service.executable -ceq 'E:\AI-Video-Ops-Network\frpc.exe') 'manual fixed binding'
    Assert-GuardTest ($service.service.arguments -ceq '-c E:\AI-Video-Ops-Network\frpc.toml') 'existing config untouched'
}
Invoke-GuardTest 'log whitelist blocks exception text and arbitrary secret fields' {
    Reset-GuardMock
    Write-GuardLog $script:Mock.Log 'Secret=SENTINEL_DO_NOT_LOG'
    Assert-GuardTest ((Get-Content $script:Mock.Log -Raw) -notmatch 'Secret|SENTINEL') 'bad result replaced'
    Assert-GuardThrows { Write-GuardLog $script:Mock.Log 'TEST' -FrpcState 'SECRET=do_not_log' } 'GUARD_LOG_FIELD_INVALID'
}
Invoke-GuardTest 'WinSW binding, manual startup, service parent lineage and non-admin process visibility' {
    $directory = Join-Path $script:TestRoot 'binding'
    [void](New-Item -ItemType Directory -Path $directory)
    $fakeExecutable = Join-Path $directory 'frpc.exe'
    $fakeConfig = Join-Path $directory 'frpc.toml'
    $fakeWrapper = Join-Path $directory 'AIVO-FRPC.exe'
    foreach ($path in @($fakeExecutable, $fakeConfig, $fakeWrapper)) { [IO.File]::WriteAllText($path, 'OFFLINE_TEST_ONLY') }
    [xml]$document = New-GuardServiceXml
    $document.service.executable = [string]$fakeExecutable
    $document.service.arguments = '-c "' + $fakeConfig + '"'
    $xmlPath = [IO.Path]::ChangeExtension($fakeWrapper, '.xml')
    $document.Save($xmlPath)
    $script:ServiceFixture = [pscustomobject]@{ Name = 'AIVO-FRPC'; DisplayName = 'AIVO FRPC'; State = 'Running'; StartMode = 'Manual'; PathName = '"' + $fakeWrapper + '"'; ProcessId = 101 }
    $script:ProcessFixture = @([pscustomobject]@{ Name = 'frpc.exe'; ExecutablePath = $null; ParentProcessId = 101; ProcessId = 102 })
    try {
        function Get-CimInstance {
            param($ClassName, $Filter)
            if ($ClassName -ceq 'Win32_Service') { return $script:ServiceFixture }
            return $script:ProcessFixture
        }
        $binding = & $script:OriginalBinding 'AIVO-FRPC'
        Assert-GuardTest ($binding.Executable -ceq $fakeExecutable -and $binding.Config -ceq $fakeConfig) 'exact existing binding, no config rewrite'
        Assert-GuardTest ((& $script:OriginalProcess $binding)) 'non-admin process path hidden, protected service parent still verified'
        $script:ProcessFixture[0].ParentProcessId = 999
        Assert-GuardTest (-not (& $script:OriginalProcess $binding)) 'unrelated frpc not accepted'
        $script:ProcessFixture[0].ParentProcessId = 101; $script:ProcessFixture[0].ExecutablePath = 'E:\wrong\frpc.exe'
        Assert-GuardTest (-not (& $script:OriginalProcess $binding)) 'visible wrong executable rejected'
        $script:ServiceFixture.StartMode = 'Auto'
        Assert-GuardThrows { & $script:OriginalBinding 'AIVO-FRPC' } 'FRPC_SERVICE_MUST_BE_MANUAL'
        [void](& $script:OriginalBinding 'AIVO-FRPC' -AllowUnprepared)
        $found = Find-GuardFrpcService
        Assert-GuardTest ($found.Service.Name -ceq 'AIVO-FRPC') 'installer finds/reuses current WinSW service'
        $script:ServiceFixture = @($script:ServiceFixture, $script:ServiceFixture)
        Assert-GuardThrows { Find-GuardFrpcService } 'MULTIPLE_FRPC_SERVICES_FOUND'
    } finally { Remove-Item Function:Get-CimInstance -ErrorAction SilentlyContinue }
}
Invoke-GuardTest 'installer account/SID resolution and isolated ACL application' {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    Assert-GuardTest ((Resolve-GuardWindowsSid $identity.Name) -ceq $identity.User.Value) 'account resolved'
    Assert-GuardTest ((Resolve-GuardWindowsSid $identity.User.Value) -ceq $identity.User.Value) 'existing task SID resolves idempotently'
    $path = Join-Path $script:TestRoot 'acl-test.txt'
    [IO.File]::WriteAllText($path, 'OFFLINE_TEST_ONLY')
    Set-GuardFileAcl $path $identity.User.Value ([Security.AccessControl.FileSystemRights]::FullControl)
    $acl = Get-Acl -LiteralPath $path
    Assert-GuardTest ($acl.AreAccessRulesProtected) 'file does not inherit broad access'
    $allowed = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Allow' })
    Assert-GuardTest ($allowed.Count -eq 3) 'only SYSTEM, Administrators and dedicated identity'
    $aclDirectory = Join-Path $script:TestRoot 'acl-dir'
    [void](New-Item -ItemType Directory -Path $aclDirectory)
    Set-GuardFileAcl $aclDirectory $identity.User.Value ([Security.AccessControl.FileSystemRights]::Modify) -Directory
    Assert-GuardTest ((Get-Acl $aclDirectory).AreAccessRulesProtected) 'state directory protected'
}
Invoke-GuardTest 'restart stops only named service, never cascades to other services' {
    Reset-GuardMock
    & $script:OriginalAction 'AIVO-FRPC' 'Restart'
    Assert-GuardTest (($script:Mock.NativeCalls[0] -join ',') -ceq 'stop,AIVO-FRPC') 'single explicit sc stop'
    $script:Mock.NativeExit = 1
    Assert-GuardThrows { & $script:OriginalAction 'AIVO-FRPC' 'Restart' } 'FRPC_SERVICE_STOP_FAILED'
}
Invoke-GuardTest 'metadata checks do not grant FRP token read/write or replace prior ACL' {
    $path = Join-Path $script:TestRoot 'config-attributes-only.toml'
    [IO.File]::WriteAllText($path, 'OFFLINE_TEST_ONLY')
    $testSid = 'S-1-5-21-11-22-33-1001'
    $before = (Get-Acl $path).Sddl
    Grant-GuardConfigMetadataRead $path $testSid
    $acl = Get-Acl $path
    $rules = @($acl.Access | Where-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ceq $testSid })
    # FileSystemAccessRule automatically adds Synchronize to an Allow ACE.
    $allowedMask = [int][Security.AccessControl.FileSystemRights]::ReadAttributes -bor [int][Security.AccessControl.FileSystemRights]::Synchronize
    Assert-GuardTest ($rules.Count -eq 1 -and ([int]$rules[0].FileSystemRights -band (-bnot $allowedMask)) -eq 0 -and
        ([int]$rules[0].FileSystemRights -band [int][Security.AccessControl.FileSystemRights]::ReadAttributes) -ne 0) 'attributes only, no token data read/write'
    Assert-GuardTest ($acl.Sddl -ne $before -and $acl.Access.Count -gt 1) 'existing ACL preserved'
}
Invoke-GuardTest 'PowerShell parser and no business/config/token writes' {
    foreach ($sourcePath in @(Get-ChildItem $PSScriptRoot -Filter '*.ps1')) {
        $tokens = $null; $errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile($sourcePath.FullName, [ref]$tokens, [ref]$errors)
        Assert-GuardTest ($errors.Count -eq 0) ('parser ' + $sourcePath.Name)
    }
    Reset-GuardMock
    Assert-GuardThrows { & $script:OriginalAliyun $script:Config 'Authorize' -Cidr '0.0.0.0/0' } 'SG_AUTHORIZATION_SCOPE_INVALID'
    Assert-GuardThrows { & $script:OriginalAliyun $script:Config 'Revoke' -RuleId 'invalid' } 'SG_REVOCATION_SCOPE_INVALID'
    Assert-GuardTest ($script:Mock.NativeCalls.Count -eq 0) 'unsafe grant/revoke never reaches CLI'
    $policy = Get-Content (Join-Path $PSScriptRoot 'ram-policy.json.example') -Raw | ConvertFrom-Json
    Assert-GuardTest ($policy.Statement[0].Action.Count -eq 3 -and $policy.Statement[0].Resource -match 'securitygroup/') 'minimal RAM actions and scoped SG'
}
Invoke-GuardTest 'native argument quoting preserves literal quotes/spaces/backslashes and has a hard timeout' {
    $script:GuardDeadline = $null
    $powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $command = '[Console]::Write(''quoted "value" C:\path with spaces\'')'
    $result = & $script:OriginalNative $powershell @('-NoProfile', '-NonInteractive', '-Command', $command) 5
    Assert-GuardTest ($result.ExitCode -eq 0 -and $result.Stdout -ceq 'quoted "value" C:\path with spaces\') 'native literal roundtrip'
    Assert-GuardThrows { & $script:OriginalNative $powershell @('-NoProfile', '-NonInteractive', '-Command', 'Start-Sleep -Seconds 20') 1 } 'GUARD_NATIVE_TIMEOUT'
}

Write-Output ('FRP_GUARD_TESTS_PASS: ' + $script:Passed + '; external cloud/service mutations=0; evidence=' + $script:TestRoot)
