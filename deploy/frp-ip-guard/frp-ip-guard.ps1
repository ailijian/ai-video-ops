[CmdletBinding()]
param(
    [string]$ConfigPath = 'E:\AI-Video-Ops-Config\frp-ip-guard.json',
    [string]$LogPath = 'E:\AI-Video-Ops-Logs\frp-ip-guard.log',
    [string]$ServiceName = 'AIVO-FRPC',
    [switch]$DryRun,
    [switch]$Preflight
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:GuardDeadline = $null

function Get-GuardProperty {
    param($Object, [string]$Name, $Default = '')
    if ($null -ne $Object -and $null -ne $Object.PSObject.Properties[$Name]) {
        return $Object.PSObject.Properties[$Name].Value
    }
    return $Default
}

function ConvertTo-GuardPublicIPv4 {
    param([string]$Value)
    $valueTrimmed = $Value.Trim()
    $address = $null
    if ($valueTrimmed -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or
        -not [System.Net.IPAddress]::TryParse($valueTrimmed, [ref]$address) -or
        $address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'PUBLIC_IPV4_INVALID'
    }
    $octets = $address.GetAddressBytes()
    # Public detection must never authorize loopback, RFC1918, link-local or multicast.
    if ($octets[0] -in @(0, 10, 127) -or $octets[0] -ge 224 -or
        ($octets[0] -eq 169 -and $octets[1] -eq 254) -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168) -or
        ($octets[0] -eq 100 -and $octets[1] -ge 64 -and $octets[1] -le 127)) {
        throw 'PUBLIC_IPV4_INVALID'
    }
    return $address.ToString()
}

function Read-GuardConfig {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'GUARD_CONFIG_MISSING' }
    try { $config = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { throw 'GUARD_CONFIG_INVALID' }
    $allowed = @('regionId', 'securityGroupId', 'frpsHost', 'frpsPort', 'ruleDescription', 'aliyunProfile')
    if ($null -eq $config -or @($config.PSObject.Properties.Name).Count -ne $allowed.Count) { throw 'GUARD_CONFIG_INVALID' }
    foreach ($field in $config.PSObject.Properties.Name) {
        if ($field -cnotin $allowed) { throw 'GUARD_CONFIG_INVALID' }
    }
    if ([string](Get-GuardProperty $config 'regionId') -notmatch '^[a-z]{2}-[a-z0-9-]+$' -or
        [string](Get-GuardProperty $config 'securityGroupId') -notmatch '^sg-[a-z0-9]+$') { throw 'GUARD_CONFIG_REQUIRED' }
    if ($config.frpsHost -cne '47.116.109.155' -or [string]$config.frpsPort -cne '7000' -or
        $config.ruleDescription -cne 'AI Video Ops FRPS Control - RTX4090' -or
        $config.aliyunProfile -cne 'aivo-frp') { throw 'GUARD_CONFIG_INVALID' }
    return $config
}

function Assert-GuardBudget {
    param([int]$ReserveSeconds = 0)
    if ($null -ne $script:GuardDeadline -and [datetime]::UtcNow.AddSeconds($ReserveSeconds) -ge $script:GuardDeadline) {
        throw 'GUARD_TIME_BUDGET_EXCEEDED'
    }
}

function ConvertTo-GuardNativeArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgvW quoting, including JSON quotes and trailing backslashes.
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Invoke-GuardNative {
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds = 10)
    Assert-GuardBudget $TimeoutSeconds
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = ($Arguments | ForEach-Object { ConvertTo-GuardNativeArgument $_ }) -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.RedirectStandardInput = $true
    # Credentials must come from the explicit named profile, not inherited secret variables.
    foreach ($name in @($startInfo.EnvironmentVariables.Keys)) {
        if ($name -match '^(ALIBABA_CLOUD_|ALICLOUD_|ALIYUN_)') { $startInfo.EnvironmentVariables.Remove($name) }
    }
    $startInfo.EnvironmentVariables['ALIBABA_CLOUD_CLI_PLUGIN_AUTO_INSTALL'] = 'false'
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        $process.StandardInput.Close()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            # Kill the CLI plugin as well, so a timed-out mutation cannot run in the background.
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F 2>&1 | Out-Null
            throw 'GUARD_NATIVE_TIMEOUT'
        }
        return [pscustomobject]@{ ExitCode = $process.ExitCode; Stdout = $stdoutTask.Result; Stderr = $stderrTask.Result }
    } catch {
        if ($_.Exception.Message -eq 'GUARD_NATIVE_TIMEOUT') { throw 'GUARD_NATIVE_TIMEOUT' }
        throw 'GUARD_NATIVE_FAILED'
    } finally { $process.Dispose() }
}

function Initialize-GuardCli {
    $command = Get-Command aliyun.exe -ErrorAction SilentlyContinue
    if ($null -eq $command -and (Test-Path -LiteralPath 'C:\AliyunCLI\aliyun.exe')) {
        $script:GuardCliPath = 'C:\AliyunCLI\aliyun.exe'
    } elseif ($null -ne $command) { $script:GuardCliPath = $command.Source }
    else { throw 'ALIYUN_CLI_MISSING' }
    $profilePath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.aliyun\config.json'
    try { $profiles = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json } catch { throw 'ALIYUN_PROFILE_REQUIRED' }
    $matchingProfiles = @((Get-GuardProperty $profiles 'profiles' @()) | Where-Object { (Get-GuardProperty $_ 'name') -ceq 'aivo-frp' })
    if ($matchingProfiles.Count -ne 1) { throw 'ALIYUN_PROFILE_REQUIRED' }
    # Long-running Windows tasks use RAM AK or RAM role with a RAM source profile.
    if ((Get-GuardProperty $matchingProfiles[0] 'mode') -notin @('AK', 'RamRoleArn')) { throw 'ALIYUN_PROFILE_MODE_UNSUPPORTED' }
    $versionResult = Invoke-GuardNative $script:GuardCliPath @('version')
    if ($versionResult.ExitCode -ne 0 -or $versionResult.Stdout -notmatch '(\d+)\.(\d+)\.(\d+)') { throw 'ALIYUN_CLI_VERSION_UNSUPPORTED' }
    $script:GuardCliModern = ([version]$Matches[0] -ge [version]'3.3.0')
    if ($script:GuardCliModern) {
        $plugins = Invoke-GuardNative $script:GuardCliPath @('plugin', 'list')
        if ($plugins.ExitCode -ne 0 -or $plugins.Stdout -notmatch 'aliyun-cli-ecs') { throw 'ALIYUN_ECS_PLUGIN_REQUIRED' }
        $help = Invoke-GuardNative $script:GuardCliPath @('ecs', 'describe-security-group-attribute', '--help')
        if ($help.ExitCode -ne 0) { throw 'ALIYUN_CLI_CONTRACT_UNSUPPORTED' }
        if ($help.Stdout -match '--biz-region-id\b') { $script:GuardRegionFlag = '--biz-region-id' }
        elseif ($help.Stdout -match '--region-id\b') { $script:GuardRegionFlag = '--region-id' }
        else { throw 'ALIYUN_CLI_CONTRACT_UNSUPPORTED' }
        foreach ($contract in @(
            @{ Command = 'authorize-security-group'; Flags = @('--ip-protocol', '--port-range', '--source-cidr-ip', '--policy', '--priority', '--description') },
            @{ Command = 'revoke-security-group'; Flags = @('--security-group-rule-id') }
        )) {
            $operationHelp = Invoke-GuardNative $script:GuardCliPath @('ecs', $contract.Command, '--help')
            if ($operationHelp.ExitCode -ne 0) { throw 'ALIYUN_CLI_CONTRACT_UNSUPPORTED' }
            foreach ($flag in @($contract.Flags) + @($script:GuardRegionFlag, '--security-group-id')) {
                if ($operationHelp.Stdout -notmatch ([regex]::Escape($flag) + '\b')) { throw 'ALIYUN_CLI_CONTRACT_UNSUPPORTED' }
            }
        }
    } else { $script:GuardRegionFlag = '--RegionId' }
}

function Invoke-GuardAliyun {
    param($Config, [ValidateSet('Describe', 'Authorize', 'Revoke')][string]$Operation, [string]$Cidr = '', [string]$RuleId = '', [string]$NextToken = '')
    if ($Operation -eq 'Authorize') {
        if ($Cidr -notmatch '^(.+)/32$') { throw 'SG_AUTHORIZATION_SCOPE_INVALID' }
        if ((ConvertTo-GuardPublicIPv4 $Matches[1]) + '/32' -cne $Cidr) { throw 'SG_AUTHORIZATION_SCOPE_INVALID' }
    }
    if ($Operation -eq 'Revoke' -and $RuleId -notmatch '^sgr-[a-z0-9]+$') { throw 'SG_REVOCATION_SCOPE_INVALID' }
    if ($script:GuardCliModern) {
        $commands = @{ Describe = 'describe-security-group-attribute'; Authorize = 'authorize-security-group'; Revoke = 'revoke-security-group' }
        $arguments = @('ecs', $commands[$Operation], '--profile', $Config.aliyunProfile, '--region', $Config.regionId,
            $script:GuardRegionFlag, $Config.regionId, '--security-group-id', $Config.securityGroupId)
        switch ($Operation) {
            Describe {
                $arguments += @('--direction', 'ingress', '--max-results', '1000')
                if ($NextToken) { $arguments += @('--next-token', $NextToken) }
            }
            Authorize {
                # Top-level API fields remain supported; no unverified JSON object serialization.
                $arguments += @('--ip-protocol', 'TCP', '--port-range', '7000/7000', '--source-cidr-ip', $Cidr,
                    '--policy', 'Accept', '--priority', '1', '--description', $Config.ruleDescription)
            }
            Revoke { $arguments += @('--security-group-rule-id', $RuleId) }
        }
    } else {
        $commands = @{ Describe = 'DescribeSecurityGroupAttribute'; Authorize = 'AuthorizeSecurityGroup'; Revoke = 'RevokeSecurityGroup' }
        $arguments = @('ecs', $commands[$Operation], '--profile', $Config.aliyunProfile, '--region', $Config.regionId,
            '--RegionId', $Config.regionId, '--SecurityGroupId', $Config.securityGroupId)
        switch ($Operation) {
            Describe {
                $arguments += @('--Direction', 'ingress', '--MaxResults', '1000')
                if ($NextToken) { $arguments += @('--NextToken', $NextToken) }
            }
            Authorize { $arguments += @('--IpProtocol', 'TCP', '--PortRange', '7000/7000', '--SourceCidrIp', $Cidr,
                '--Policy', 'Accept', '--Priority', '1', '--Description', $Config.ruleDescription) }
            Revoke { $arguments += @('--SecurityGroupRuleId.1', $RuleId) }
        }
    }
    try { $result = Invoke-GuardNative $script:GuardCliPath $arguments } catch { throw 'ALIYUN_API_TIMEOUT_OR_FAILED' }
    if ($result.ExitCode -ne 0) {
        if (($result.Stderr + $result.Stdout) -match 'InvalidAccessKey|SignatureDoesNotMatch|Forbidden|Unauthorized|credential|AccessDenied') { throw 'ALIYUN_AUTH_FAILED' }
        throw 'ALIYUN_API_FAILED'
    }
    try { return ($result.Stdout | ConvertFrom-Json) } catch { throw 'ALIYUN_RESPONSE_INVALID' }
}

function Get-GuardRules {
    param($Config)
    $rules = @()
    $nextToken = ''
    $tokens = @()
    do {
        $response = Invoke-GuardAliyun $Config 'Describe' -NextToken $nextToken
        if ((Get-GuardProperty $response 'SecurityGroupId') -cne $Config.securityGroupId -or
            (Get-GuardProperty $response 'RegionId') -cne $Config.regionId -or
            $null -eq $response.PSObject.Properties['Permissions'] -or
            $null -eq $response.Permissions.PSObject.Properties['Permission']) { throw 'SG_RESPONSE_SCOPE_INVALID' }
        # The deployed ECS uses VPC. Classic-network targets require a separate reviewed setup.
        if ([string]::IsNullOrWhiteSpace([string](Get-GuardProperty $response 'VpcId'))) { throw 'SG_NETWORK_UNSUPPORTED' }
        $rules += @(Get-GuardProperty $response.Permissions 'Permission' @())
        $nextToken = [string](Get-GuardProperty $response 'NextToken')
        if ($nextToken) {
            if ($nextToken -in $tokens -or $tokens.Count -ge 9) { throw 'SG_PAGINATION_INVALID' }
            $tokens += $nextToken
        }
    } while ($nextToken)
    return ,$rules
}

function Test-GuardManagedRule {
    param($Rule, $Config)
    return (Get-GuardProperty $Rule 'Description') -ceq $Config.ruleDescription -and
        (Get-GuardProperty $Rule 'Direction') -ieq 'ingress' -and
        (Get-GuardProperty $Rule 'IpProtocol') -ieq 'tcp' -and
        (Get-GuardProperty $Rule 'PortRange') -ceq '7000/7000' -and
        (Get-GuardProperty $Rule 'Policy') -ieq 'Accept'
}

function Test-GuardCovers7000 {
    param($Rule)
    if ((Get-GuardProperty $Rule 'Direction') -ine 'ingress' -or
        (Get-GuardProperty $Rule 'Policy') -ine 'Accept') { return $false }
    if ((Get-GuardProperty $Rule 'IpProtocol') -ieq 'all') { return $true }
    if ((Get-GuardProperty $Rule 'IpProtocol') -ine 'tcp') { return $false }
    $range = [string](Get-GuardProperty $Rule 'PortRange')
    return ($range -match '^(\d{1,5})/(\d{1,5})$' -and [int]$Matches[1] -le 7000 -and [int]$Matches[2] -ge 7000)
}

function Get-GuardRuleProjection {
    param([object[]]$Rules, $Config)
    $managed = @()
    $unmanaged = $false
    $highRisk = $false
    $ids = @()
    foreach ($rule in $Rules) {
        if ($null -eq $rule) { throw 'SG_RULE_STATE_UNEXPECTED' }
        if (Test-GuardCovers7000 $rule) {
            if ((Get-GuardProperty $rule 'SourceCidrIp') -ceq '0.0.0.0/0') { $highRisk = $true }
            if (-not (Test-GuardManagedRule $rule $Config)) { $unmanaged = $true }
        }
        if ((Get-GuardProperty $rule 'Description') -cne $Config.ruleDescription) { continue }
        # Matching text alone cannot grant ownership of other ports/directions/protocols.
        if (-not (Test-GuardManagedRule $rule $Config)) { throw 'SG_RULE_STATE_UNEXPECTED' }
        $id = [string](Get-GuardProperty $rule 'SecurityGroupRuleId')
        if ($id -notmatch '^sgr-[a-z0-9]+$' -or $id -in $ids -or
            [string](Get-GuardProperty $rule 'Priority') -cne '1') { throw 'SG_RULE_STATE_UNEXPECTED' }
        $ids += $id
        foreach ($field in @('Ipv6SourceCidrIp', 'SourceGroupId', 'SourcePrefixListId', 'Ipv6DestCidrIp', 'DestGroupId', 'DestPrefixListId', 'PortRangeListId')) {
            if (Get-GuardProperty $rule $field) { throw 'SG_RULE_STATE_UNEXPECTED' }
        }
        if ((Get-GuardProperty $rule 'DestCidrIp') -notin @('', '0.0.0.0/0') -or
            (Get-GuardProperty $rule 'SourcePortRange') -notin @('', '-1/-1', '1/65535') -or
            (Get-GuardProperty $rule 'NicType') -ine 'intranet') { throw 'SG_RULE_STATE_UNEXPECTED' }
        $cidr = [string](Get-GuardProperty $rule 'SourceCidrIp')
        if ($cidr -ne '0.0.0.0/0') {
            if ($cidr -notmatch '^(.+)/32$') { throw 'SG_RULE_STATE_UNEXPECTED' }
            if ((ConvertTo-GuardPublicIPv4 $Matches[1]) + '/32' -cne $cidr) { throw 'SG_RULE_STATE_UNEXPECTED' }
        }
        $managed += $rule
    }
    return [pscustomobject]@{ Managed = $managed; Unmanaged = $unmanaged; HighRisk = $highRisk }
}

function Write-GuardLog {
    param([string]$Path, [string]$Result, [string]$PublicIp = '', [string[]]$OldManagedIps = @(), [string]$Reachability = '', [string]$FrpcState = '', [string]$HealthState = '')
    # Only allow structured fields produced by the guard, never native/HTTP/exception text.
    if ($Result -cnotmatch '^[A-Z_0-9]+$') { $Result = 'GUARD_INTERNAL_ERROR' }
    if ($PublicIp) { $PublicIp = ConvertTo-GuardPublicIPv4 $PublicIp }
    $safeOldIps = @($OldManagedIps | Where-Object { $_ -match '^\d{1,3}(\.\d{1,3}){3}/(32|0)$' })
    foreach ($value in @($Reachability, $FrpcState, $HealthState)) {
        if ($value -notmatch '^[A-Za-z_]*$') { throw 'GUARD_LOG_FIELD_INVALID' }
    }
    $row = [ordered]@{ timestamp = [datetime]::UtcNow.ToString('o'); publicIPv4 = $PublicIp;
        oldManagedIps = $safeOldIps; reconciliation = $Result; tcp7000 = $Reachability; frpc = $FrpcState; health = $HealthState }
    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) { throw 'GUARD_LOG_DIRECTORY_MISSING' }
    [IO.File]::AppendAllText($Path, ($row | ConvertTo-Json -Compress) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
}

function Get-GuardPublicIPv4 {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($null -eq $curl) { throw 'CURL_MISSING' }
    foreach ($url in @('https://api.ipify.org', 'https://ifconfig.me/ip')) {
        try {
            $result = Invoke-GuardNative $curl.Source @('-4', '--noproxy', '*', '-sS', '--fail', '--connect-timeout', '3', '--max-time', '6', $url) 7
            if ($result.ExitCode -eq 0) { return (ConvertTo-GuardPublicIPv4 $result.Stdout) }
        } catch { if ($_.Exception.Message -eq 'GUARD_TIME_BUDGET_EXCEEDED') { throw } }
    }
    throw 'PUBLIC_IPV4_DETECTION_FAILED'
}

function Test-GuardTcp7000 {
    param($Config)
    $powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $commandText = '$ProgressPreference="SilentlyContinue"; if (Test-NetConnection 47.116.109.155 -Port 7000 -InformationLevel Quiet -WarningAction SilentlyContinue) { [Console]::Write("true") } else { [Console]::Write("false") }'
    try { $result = Invoke-GuardNative $powershell @('-NoProfile', '-NonInteractive', '-Command', $commandText) 9 }
    catch { return $false }
    return $result.ExitCode -eq 0 -and $result.Stdout.Trim() -ceq 'true'
}

function Get-GuardFrpcBinding {
    param([string]$Name, [switch]$AllowUnprepared)
    if ($Name -notmatch '^[A-Za-z0-9_.-]+$') { throw 'FRPC_SERVICE_INVALID' }
    $service = Get-CimInstance Win32_Service -Filter "Name='$Name'"
    if ($null -eq $service) { throw 'FRPC_SERVICE_MISSING' }
    if (-not $AllowUnprepared -and $service.StartMode -cne 'Manual') { throw 'FRPC_SERVICE_MUST_BE_MANUAL' }
    $wrapper = [regex]::Match($service.PathName, '^\s*(?:"([^"]+\.exe)"|([^"\s]+\.exe))', 'IgnoreCase')
    if (-not $wrapper.Success) { throw 'FRPC_SERVICE_INVALID' }
    $wrapperPath = $wrapper.Groups[1].Value
    if (-not $wrapperPath) { $wrapperPath = $wrapper.Groups[2].Value }
    $xmlPath = [IO.Path]::ChangeExtension($wrapperPath, '.xml')
    try {
        $document = New-Object Xml.XmlDocument
        $document.XmlResolver = $null
        $document.Load($xmlPath)
        if ($document.DocumentType -or $document.service.id -cne $Name) { throw 'invalid' }
        if (-not $AllowUnprepared -and $document.SelectNodes('/service/onfailure').Count -gt 0) { throw 'invalid' }
        $executable = [string]$document.service.executable
        $arguments = [string]$document.service.arguments
        if (-not [IO.Path]::IsPathRooted($executable) -or [IO.Path]::GetFileName($executable) -ine 'frpc.exe' -or
            -not (Test-Path -LiteralPath $executable -PathType Leaf) -or $arguments -notmatch '^\s*-c\s+(?:"([^"]+)"|([^\s]+))\s*$') { throw 'invalid' }
        $config = $Matches[1]
        if (-not $config) { $config = $Matches[2] }
        if (-not [IO.Path]::IsPathRooted($config) -or -not (Test-Path -LiteralPath $config -PathType Leaf)) { throw 'invalid' }
    } catch { throw 'FRPC_WINSW_BINDING_INVALID' }
    return [pscustomobject]@{ Name = $Name; Executable = $executable; Config = $config; Wrapper = $wrapperPath; XmlPath = $xmlPath }
}

function Get-GuardFrpcState {
    param([string]$Name)
    return [string](Get-Service -Name $Name -ErrorAction Stop).Status
}

function Get-GuardFrpcProcessRunning {
    param($Binding)
    $service = Get-CimInstance Win32_Service -Filter "Name='$($Binding.Name)'"
    if ($service.State -ne 'Running' -or $service.ProcessId -le 0) { return $false }
    $processes = @(Get-CimInstance Win32_Process)
    $frpc = @($processes | Where-Object { $_.Name -ieq 'frpc.exe' })
    # Non-admin task identities cannot always read ExecutablePath of a SYSTEM process.
    # In that case the protected WinSW binding and service parent chain are the evidence.
    if ($frpc.Count -ne 1 -or ($frpc[0].ExecutablePath -and $frpc[0].ExecutablePath -ine $Binding.Executable)) { return $false }
    $parentId = $frpc[0].ParentProcessId
    for ($depth = 0; $depth -lt 5 -and $parentId -gt 0; $depth++) {
        if ($parentId -eq $service.ProcessId) { return $true }
        $parent = @($processes | Where-Object { $_.ProcessId -eq $parentId })
        if ($parent.Count -ne 1) { break }
        $parentId = $parent[0].ParentProcessId
    }
    return $false
}

function Invoke-GuardFrpcAction {
    param([string]$Name, [ValidateSet('Start', 'Restart')][string]$Action)
    Assert-GuardBudget 35
    # sc stop never cascades to dependent services. Poll under the shared 30-second deadline.
    if ($Action -eq 'Restart') {
        $result = Invoke-GuardNative "$env:SystemRoot\System32\sc.exe" @('stop', $Name)
        if ($result.ExitCode -ne 0) { throw 'FRPC_SERVICE_STOP_FAILED' }
    }
    else { (Get-Service -Name $Name).Start() }
}

function Test-GuardHealth {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    try {
        $result = Invoke-GuardNative $curl.Source @('-4', '--noproxy', '*', '-sS', '--fail', '--connect-timeout', '2', '--max-time', '4', 'https://ops.jingtang.cc/api/health') 5
        if ($result.ExitCode -ne 0) { return $false }
        $health = $result.Stdout | ConvertFrom-Json
        return (Get-GuardProperty $health 'status') -ceq 'ok'
    } catch { return $false }
}

function Wait-GuardFrpcHealth {
    param($Binding, [string]$Action)
    $deadline = [datetime]::UtcNow.AddSeconds(30)
    $startAfterStop = $Action -eq 'Restart'
    do {
        Assert-GuardBudget 6
        $state = Get-GuardFrpcState $Binding.Name
        if ($startAfterStop -and $state -eq 'Stopped') {
            (Get-Service -Name $Binding.Name).Start()
            $startAfterStop = $false
        }
        if (-not $startAfterStop -and (Get-GuardFrpcProcessRunning $Binding) -and (Test-GuardHealth)) { return $true }
        Start-Sleep -Seconds 1
    } while ([datetime]::UtcNow.AddSeconds(5) -lt $deadline)
    return $false
}

function Read-GuardState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return [pscustomobject]@{ LastIp = ''; PendingIp = '' } }
    try {
        $state = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        if ((Get-GuardProperty $state 'schema_version') -cne 'aivo_frp_ip_guard_state_v1') { throw 'invalid' }
        $lastIp = [string](Get-GuardProperty $state 'lastServicePublicIPv4')
        $pendingIp = [string](Get-GuardProperty $state 'pendingServicePublicIPv4')
        if ($lastIp) { $lastIp = ConvertTo-GuardPublicIPv4 $lastIp }
        if ($pendingIp) { $pendingIp = ConvertTo-GuardPublicIPv4 $pendingIp }
        return [pscustomobject]@{ LastIp = $lastIp; PendingIp = $pendingIp }
    } catch { throw 'GUARD_STATE_INVALID' }
}

function Save-GuardState {
    param([string]$Path, [string]$PublicIp, [string]$PendingIp = '')
    $state = @{ schema_version = 'aivo_frp_ip_guard_state_v1'; lastServicePublicIPv4 = $PublicIp; pendingServicePublicIPv4 = $PendingIp }
    $tempPath = $Path + '.tmp'
    [IO.File]::WriteAllText($tempPath, ($state | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($tempPath, $Path, ($Path + '.previous')) }
    else { [IO.File]::Move($tempPath, $Path) }
}

function Invoke-AivoFrpGuard {
    param($Config, [string]$Path, [string]$Name, [switch]$ReadOnly)
    $publicIp = Get-GuardPublicIPv4
    $cidr = $publicIp + '/32'
    $projection = Get-GuardRuleProjection (Get-GuardRules $Config) $Config
    $oldIps = @($projection.Managed | ForEach-Object { $_.SourceCidrIp } | Select-Object -Unique)
    if ($projection.Unmanaged) { Write-GuardLog $Path 'UNMANAGED_7000_RULES_PRESENT' $publicIp $oldIps }
    if ($projection.HighRisk) { Write-GuardLog $Path 'HIGH_RISK_FRPS_RULE_DETECTED' $publicIp $oldIps }
    $binding = Get-GuardFrpcBinding $Name
    $statePath = Join-Path (Join-Path (Split-Path -Parent $Path) 'frp-ip-guard-state') 'frp-ip-guard.state.json'
    $previous = Read-GuardState $statePath
    $current = @($projection.Managed | Where-Object { $_.SourceCidrIp -ceq $cidr })
    $stale = @($projection.Managed | Where-Object { $_.SourceCidrIp -cne $cidr })
    if ($current.Count -gt 1) { throw 'SG_RULE_STATE_UNEXPECTED' }
    if ($ReadOnly) {
        $reachable = Test-GuardTcp7000 $Config
        $result = if ($current.Count -eq 1) { 'DRY_RUN_CURRENT_RULE_PRESENT' } else { 'DRY_RUN_ADD_REQUIRED' }
        Write-GuardLog $Path $result $publicIp $oldIps ([string]$reachable) (Get-GuardFrpcState $Name) 'NOT_CHECKED'
        return [pscustomobject]@{ status = $result; publicIPv4 = $publicIp; addRequired = ($current.Count -eq 0);
            staleManagedRuleCount = $stale.Count; tcp7000 = $reachable; securityGroupMutations = 0; frpcRestarts = 0 }
    }
    $added = $false
    if ($current.Count -eq 0) {
        [void](Invoke-GuardAliyun $Config 'Authorize' -Cidr $cidr)
        $added = $true
        Write-GuardLog $Path 'NEW_RULE_ADDED' $publicIp $oldIps
        # Eventual consistency: only the subsequent Describe result is proof of ownership.
        $verified = $false
        for ($attempt = 0; $attempt -lt 3; $attempt++) {
            $projection = Get-GuardRuleProjection (Get-GuardRules $Config) $Config
            $current = @($projection.Managed | Where-Object { $_.SourceCidrIp -ceq $cidr })
            if ($current.Count -eq 1) { $verified = $true; break }
            if ($current.Count -gt 1) { throw 'SG_RULE_STATE_UNEXPECTED' }
            if ($attempt -lt 2) { Start-Sleep -Seconds 1 }
        }
        if (-not $verified) { throw 'NEW_RULE_VERIFICATION_FAILED' }
    }
    Write-GuardLog $Path 'CURRENT_RULE_VERIFIED' $publicIp $oldIps
    if (-not (Test-GuardTcp7000 $Config)) { throw 'FRPS_7000_UNREACHABLE' }
    Write-GuardLog $Path 'TCP_7000_REACHABLE' $publicIp $oldIps 'True'
    $ipChanged = if ($previous.LastIp) { $previous.LastIp -cne $publicIp } else { $added -or $stale.Count -gt 0 }
    $ipChanged = $ipChanged -or ($previous.PendingIp -ceq $publicIp)
    # Preserve restart intent before cleanup: an interrupted first run must still recover.
    if ($ipChanged) { Save-GuardState $statePath $previous.LastIp $publicIp }
    # Refresh immediately before deletion. A concurrently edited rule cannot retain ownership by ID alone.
    $projection = Get-GuardRuleProjection (Get-GuardRules $Config) $Config
    if (@($projection.Managed | Where-Object { $_.SourceCidrIp -ceq $cidr }).Count -ne 1) { throw 'CURRENT_RULE_LOST' }
    foreach ($rule in @($projection.Managed | Where-Object { $_.SourceCidrIp -cne $cidr })) {
        Assert-GuardBudget 40
        [void](Invoke-GuardAliyun $Config 'Revoke' -RuleId $rule.SecurityGroupRuleId)
        Write-GuardLog $Path 'OLD_MANAGED_RULE_REMOVED' $publicIp @($rule.SourceCidrIp) 'True'
    }
    if (@($projection.Managed | Where-Object { $_.SourceCidrIp -cne $cidr }).Count -gt 0) {
        $after = Get-GuardRuleProjection (Get-GuardRules $Config) $Config
        if ($after.Managed.Count -ne 1 -or $after.Managed[0].SourceCidrIp -cne $cidr) { throw 'RULE_CLEANUP_VERIFICATION_FAILED' }
    }
    $serviceState = Get-GuardFrpcState $Name
    $action = 'None'
    if ($serviceState -eq 'Stopped') { $action = 'Start' }
    elseif ($serviceState -eq 'Running' -and $ipChanged) { $action = 'Restart' }
    elseif ($serviceState -ne 'Running') { throw 'FRPC_SERVICE_STATE_UNEXPECTED' }
    if ($action -ne 'None') { Invoke-GuardFrpcAction $Name $action }
    $healthy = Wait-GuardFrpcHealth $binding $action
    if (-not $healthy) {
        # A health failure must not cause repeated service restarts on an unchanged IP.
        if (Get-GuardFrpcProcessRunning $binding) { Save-GuardState $statePath $publicIp }
        Write-GuardLog $Path 'FRPC_HEALTH_FAILED' $publicIp $oldIps 'True' (Get-GuardFrpcState $Name) 'FAIL'
        throw 'FRPC_HEALTH_FAILED'
    }
    Save-GuardState $statePath $publicIp
    Write-GuardLog $Path 'GUARD_PASS' $publicIp $oldIps 'True' 'Running' 'OK'
    return [pscustomobject]@{ status = 'GUARD_PASS'; publicIPv4 = $publicIp; frpcAction = $action; health = 'ok' }
}

if ($MyInvocation.InvocationName -ne '.') {
    $script:GuardDeadline = [datetime]::UtcNow.AddSeconds(105)
    $lock = $null
    try {
        # Cross-process lock also covers manual runs. Scheduler independently uses IgnoreNew.
        $lockPath = Join-Path (Join-Path (Split-Path -Parent $LogPath) 'frp-ip-guard-state') 'frp-ip-guard.lock'
        try { $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
        catch { throw 'GUARD_LOCK_BUSY_OR_UNAVAILABLE' }
        $config = Read-GuardConfig $ConfigPath
        Initialize-GuardCli
        Invoke-AivoFrpGuard $config $LogPath $ServiceName -ReadOnly:($DryRun -or $Preflight) | ConvertTo-Json -Compress
    } catch {
        $code = $_.Exception.Message
        if ($code -cnotmatch '^[A-Z_0-9]{1,80}$') { $code = 'GUARD_INTERNAL_ERROR' }
        try { Write-GuardLog $LogPath $code } catch {}
        Write-Output ('{"status":"FAIL_CLOSED","code":"' + $code + '"}')
        exit 1
    } finally { if ($null -ne $lock) { $lock.Dispose() } }
}
