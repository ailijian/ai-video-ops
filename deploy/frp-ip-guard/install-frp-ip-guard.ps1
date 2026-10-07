[CmdletBinding()]
param(
    [switch]$PrepareOnly,
    [string]$ExpectedComputerName = '',
    [string]$UserName = '',
    [System.Management.Automation.PSCredential]$TaskCredential,
    [string]$WinSWPath = '',
    [string]$RegionId = '',
    [string]$SecurityGroupId = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$networkDirectory = 'E:\AI-Video-Ops-Network'
$configDirectory = 'E:\AI-Video-Ops-Config'
$logDirectory = 'E:\AI-Video-Ops-Logs'
$configDestination = Join-Path $configDirectory 'frp-ip-guard.json'
$guardDestination = Join-Path $networkDirectory 'frp-ip-guard.ps1'

function ConvertTo-GuardXmlText {
    param([string]$Value)
    return [Security.SecurityElement]::Escape($Value)
}

function Resolve-GuardWindowsSid {
    param([string]$Identity)
    if ($Identity -match '^S-1-') { return (New-Object Security.Principal.SecurityIdentifier($Identity)).Value }
    return (New-Object Security.Principal.NTAccount($Identity)).Translate([Security.Principal.SecurityIdentifier]).Value
}

function New-GuardServiceXml {
    return @'
<service>
  <id>AIVO-FRPC</id>
  <name>AIVO FRPC</name>
  <description>FRPC started only after the AIVO public IPv4 guard passes.</description>
  <executable>E:\AI-Video-Ops-Network\frpc.exe</executable>
  <arguments>-c E:\AI-Video-Ops-Network\frpc.toml</arguments>
  <workingdirectory>E:\AI-Video-Ops-Network</workingdirectory>
  <startmode>Manual</startmode>
  <stoptimeout>10 sec</stoptimeout>
  <logpath>E:\AI-Video-Ops-Logs\frpc</logpath>
  <log mode="roll-by-size"><sizeThreshold>10240</sizeThreshold><keepFiles>5</keepFiles></log>
</service>
'@
}

function New-GuardTaskXml {
    param([string]$Principal, [string]$FrpcService)
    if ($FrpcService -notmatch '^[A-Za-z0-9_.-]+$') { throw 'FRPC_SERVICE_INVALID' }
    $escapedPrincipal = ConvertTo-GuardXmlText $Principal
    $start = (Get-Date).AddMinutes(2).ToString('yyyy-MM-ddTHH:mm:ss')
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>AIVO managed FRPS control IPv4 guard; no credentials in task arguments.</Description></RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled><Delay>PT30S</Delay></BootTrigger>
    <TimeTrigger><Repetition><Interval>PT10M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>$start</StartBoundary><Enabled>true</Enabled></TimeTrigger>
  </Triggers>
  <Principals><Principal id="Guard"><UserId>$escapedPrincipal</UserId><LogonType>Password</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit><Enabled>true</Enabled>
  </Settings>
  <Actions Context="Guard"><Exec>
    <Command>C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe</Command>
    <Arguments>-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File &quot;E:\AI-Video-Ops-Network\frp-ip-guard.ps1&quot; -ConfigPath &quot;E:\AI-Video-Ops-Config\frp-ip-guard.json&quot; -LogPath &quot;E:\AI-Video-Ops-Logs\frp-ip-guard.log&quot; -ServiceName &quot;$FrpcService&quot;</Arguments>
    <WorkingDirectory>E:\AI-Video-Ops-Network</WorkingDirectory>
  </Exec></Actions>
</Task>
"@
}

function Set-GuardFileAcl {
    param([string]$Path, [string]$Sid, [Security.AccessControl.FileSystemRights]$Rights, [switch]$Directory)
    $acl = if ($Directory) { New-Object Security.AccessControl.DirectorySecurity } else { New-Object Security.AccessControl.FileSecurity }
    $acl.SetAccessRuleProtection($true, $false)
    $inheritance = if ($Directory) { [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit' } else { [Security.AccessControl.InheritanceFlags]::None }
    foreach ($entry in @(@('S-1-5-18', 'FullControl'), @('S-1-5-32-544', 'FullControl'), @($Sid, [string]$Rights))) {
        $identity = New-Object Security.Principal.SecurityIdentifier($entry[0])
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, [Security.AccessControl.FileSystemRights]$entry[1], $inheritance,
            [Security.AccessControl.PropagationFlags]::None, [Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Grant-GuardServiceControl {
    param([string]$Name, [string]$Sid)
    $lines = & "$env:SystemRoot\System32\sc.exe" sdshow $Name
    if ($LASTEXITCODE -ne 0) { throw 'FRPC_SERVICE_ACL_READ_FAILED' }
    $sddl = @($lines | Where-Object { $_ -match '^[OGDS]:' }) -join ''
    if (-not $sddl) { throw 'FRPC_SERVICE_ACL_READ_FAILED' }
    $backupPath = Join-Path $configDirectory ($Name + '.pre-guard-service-sddl.txt')
    if (-not (Test-Path -LiteralPath $backupPath)) { [IO.File]::WriteAllText($backupPath, $sddl) }
    $descriptor = New-Object Security.AccessControl.RawSecurityDescriptor($sddl)
    $identity = New-Object Security.Principal.SecurityIdentifier($Sid)
    # Query config/status, start, stop, interrogate, read-control; NOT change config/delete.
    $mask = 0x200B5
    $present = @($descriptor.DiscretionaryAcl | Where-Object {
        $_ -is [Security.AccessControl.CommonAce] -and $_.SecurityIdentifier -eq $identity -and
        $_.AceQualifier -eq [Security.AccessControl.AceQualifier]::AccessAllowed -and ($_.AccessMask -band $mask) -eq $mask
    }).Count -gt 0
    if (-not $present) {
        $ace = New-Object Security.AccessControl.CommonAce([Security.AccessControl.AceFlags]::None,
            [Security.AccessControl.AceQualifier]::AccessAllowed, $mask, $identity, $false, $null)
        $descriptor.DiscretionaryAcl.InsertAce($descriptor.DiscretionaryAcl.Count, $ace)
        & "$env:SystemRoot\System32\sc.exe" sdset $Name $descriptor.GetSddlForm([Security.AccessControl.AccessControlSections]::All) | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'FRPC_SERVICE_ACL_WRITE_FAILED' }
    }
}

function Grant-GuardConfigMetadataRead {
    param([string]$Path, [string]$Sid)
    # Existence checks need attributes, not token/config contents. Preserve the existing ACL.
    $acl = Get-Acl -LiteralPath $Path
    $identity = New-Object Security.Principal.SecurityIdentifier($Sid)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity,
        [Security.AccessControl.FileSystemRights]::ReadAttributes, [Security.AccessControl.AccessControlType]::Allow)
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Find-GuardFrpcService {
    $found = @()
    foreach ($service in @(Get-CimInstance Win32_Service)) {
        $match = [regex]::Match($service.PathName, '^\s*(?:"([^"]+\.exe)"|([^"\s]+\.exe))', 'IgnoreCase')
        if (-not $match.Success) { continue }
        $wrapper = $match.Groups[1].Value
        if (-not $wrapper) { $wrapper = $match.Groups[2].Value }
        $xmlPath = [IO.Path]::ChangeExtension($wrapper, '.xml')
        if (-not (Test-Path -LiteralPath $xmlPath -PathType Leaf)) {
            if ($service.Name -match 'frpc' -or $service.DisplayName -match 'frpc') { throw 'EXISTING_FRPC_SERVICE_NOT_WINSW' }
            continue
        }
        try {
            $xml = New-Object Xml.XmlDocument
            $xml.XmlResolver = $null
            $xml.Load($xmlPath)
            if ($xml.DocumentType) { continue }
            if ([IO.Path]::GetFileName([string]$xml.service.executable) -ine 'frpc.exe') { continue }
            if ([string]$xml.service.id -cne $service.Name) { throw 'FRPC_SERVICE_BINDING_MISMATCH' }
            $found += [pscustomobject]@{ Service = $service; Xml = $xml; XmlPath = $xmlPath; Wrapper = $wrapper }
        } catch {
            if ($_.Exception.Message -eq 'FRPC_SERVICE_BINDING_MISMATCH') { throw }
            if ($service.Name -match 'frpc' -or $service.DisplayName -match 'frpc') { throw 'FRPC_WINSW_BINDING_INVALID' }
        }
    }
    if ($found.Count -gt 1) { throw 'MULTIPLE_FRPC_SERVICES_FOUND' }
    if ($found.Count -eq 1) { return $found[0] }
    return $null
}

function Install-AivoFrpGuard {
    . (Join-Path $PSScriptRoot 'frp-ip-guard.ps1')
    # No activation on the development node. Preparation writes only non-secret setup artifacts.
    if (-not $PrepareOnly) {
        if (-not $ExpectedComputerName -or $env:COMPUTERNAME -ine $ExpectedComputerName) { throw 'PRODUCTION_HOST_CONFIRMATION_REQUIRED' }
        $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'ADMINISTRATOR_REQUIRED' }
        if (-not $UserName) { throw 'DEDICATED_WINDOWS_IDENTITY_REQUIRED' }
        $sid = Resolve-GuardWindowsSid $UserName
        if ($sid -in @('S-1-5-18', 'S-1-5-19', 'S-1-5-20') -or $sid -match '-500$') { throw 'DEDICATED_WINDOWS_IDENTITY_REQUIRED' }
        $profile = Get-CimInstance Win32_UserProfile -Filter "SID='$sid'"
        if ($null -eq $profile -or -not $profile.LocalPath) { throw 'WINDOWS_USER_PROFILE_REQUIRED' }
        $cliDirectory = Join-Path $profile.LocalPath '.aliyun'
        $cliConfig = Join-Path $cliDirectory 'config.json'
        try { $metadata = Get-Content -LiteralPath $cliConfig -Raw | ConvertFrom-Json } catch { throw 'ALIYUN_PROFILE_REQUIRED' }
        $profiles = @((Get-GuardProperty $metadata 'profiles' @()) | Where-Object { (Get-GuardProperty $_ 'name') -ceq 'aivo-frp' })
        if ($profiles.Count -ne 1 -or (Get-GuardProperty $profiles[0] 'mode') -notin @('AK', 'RamRoleArn')) { throw 'ALIYUN_PROFILE_REQUIRED' }
        if ($null -eq $TaskCredential) { $TaskCredential = Get-Credential -UserName $UserName -Message 'Dedicated Windows task identity (not an Alibaba Cloud key)' }
        if ($null -eq $TaskCredential -or (Resolve-GuardWindowsSid $TaskCredential.UserName) -ne $sid) { throw 'TASK_IDENTITY_MISMATCH' }
        $existingTask = Get-ScheduledTask -TaskName 'AIVO-FRP-IP-Guard' -ErrorAction SilentlyContinue
        if ($null -ne $existingTask) {
            $taskSid = Resolve-GuardWindowsSid $existingTask.Principal.UserId
            if ($taskSid -ne $sid -or @($existingTask.Actions).Count -ne 1 -or $existingTask.Actions[0].Arguments -notmatch 'AI-Video-Ops-Network\\frp-ip-guard.ps1') { throw 'EXISTING_TASK_CONFLICT' }
            if ($existingTask.State -eq 'Running') { throw 'GUARD_TASK_RUNNING' }
        }
        $existing = Find-GuardFrpcService
        if ($null -ne $existing -and $existing.Service.State -ne 'Stopped') { throw 'STOP_EXISTING_FRPC_BEFORE_SETUP' }
        if ($null -ne $existing) { [void](Get-GuardFrpcBinding $existing.Service.Name -AllowUnprepared) }
        foreach ($otherTask in @(Get-ScheduledTask | Where-Object { $_.TaskName -ne 'AIVO-FRP-IP-Guard' -and $_.State -ne 'Disabled' })) {
            if (@($otherTask.Actions | Where-Object { ($_.Execute + ' ' + $_.Arguments) -match 'frpc\.exe|frpc\.ps1|Start-Service\s+.*frpc' }).Count -gt 0) {
                throw 'EXISTING_FRPC_AUTOSTART_TASK_REQUIRES_REVIEW'
            }
        }
        if (@(Get-CimInstance Win32_Process -Filter "Name='frpc.exe'").Count -gt 0) { throw 'STOP_MANUAL_FRPC_BEFORE_SETUP' }
        if ($null -eq $existing) {
            if (Get-Service -Name 'AIVO-FRPC' -ErrorAction SilentlyContinue) { throw 'FRPC_SERVICE_NAME_COLLISION' }
            foreach ($path in @($WinSWPath, (Join-Path $networkDirectory 'frpc.exe'), (Join-Path $networkDirectory 'frpc.toml'))) {
                if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'FRPC_OR_WINSW_BINARY_REQUIRED' }
            }
            $winswHelp = & $WinSWPath version 2>&1
            if ($LASTEXITCODE -ne 0 -or ($winswHelp -join '') -notmatch '\d+\.\d+') { throw 'WINSW_BINARY_INVALID' }
        }
    }
    foreach ($directory in @($networkDirectory, $configDirectory, $logDirectory)) {
        if (-not (Test-Path -LiteralPath $directory)) { [void](New-Item -ItemType Directory -Path $directory) }
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'frp-ip-guard.ps1') -Destination $guardDestination
    if (-not (Test-Path -LiteralPath $configDestination)) {
        $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'frp-ip-guard.json.example') -Raw | ConvertFrom-Json
        $config.regionId = $RegionId
        $config.securityGroupId = $SecurityGroupId
        [IO.File]::WriteAllText($configDestination, ($config | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    }
    if ($PrepareOnly) {
        $preparedStateDirectory = Join-Path $logDirectory 'frp-ip-guard-state'
        if (-not (Test-Path -LiteralPath $preparedStateDirectory)) { [void](New-Item -ItemType Directory -Path $preparedStateDirectory) }
        [IO.File]::WriteAllText((Join-Path $networkDirectory 'AIVO-FRPC.xml.example'), (New-GuardServiceXml), (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $networkDirectory 'AIVO-FRP-IP-Guard.task.xml.example'), (New-GuardTaskXml 'DEDICATED_WINDOWS_USER' 'AIVO-FRPC'), [Text.Encoding]::Unicode)
        Write-Output 'PREPARED_ONLY: no service, scheduled task, credential, or security-group mutation.'
        return
    }
    [void](Read-GuardConfig $configDestination)
    if ($null -eq $existing) {
        $wrapperDestination = Join-Path $networkDirectory 'AIVO-FRPC.exe'
        if (Test-Path -LiteralPath $wrapperDestination) {
            if ((Get-FileHash -LiteralPath $wrapperDestination).Hash -cne (Get-FileHash -LiteralPath $WinSWPath).Hash) { throw 'WINSW_BINARY_COLLISION' }
        } else { Copy-Item -LiteralPath $WinSWPath -Destination $wrapperDestination }
        $serviceXmlPath = Join-Path $networkDirectory 'AIVO-FRPC.xml'
        if (Test-Path -LiteralPath $serviceXmlPath) { throw 'WINSW_CONFIG_COLLISION' }
        [IO.File]::WriteAllText($serviceXmlPath, (New-GuardServiceXml), (New-Object Text.UTF8Encoding($false)))
        & $wrapperDestination install | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'FRPC_SERVICE_INSTALL_FAILED' }
        $existing = Find-GuardFrpcService
    } else {
        $backup = $existing.XmlPath + '.pre-ip-guard.bak'
        if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $existing.XmlPath -Destination $backup }
        $mode = $existing.Xml.SelectSingleNode('/service/startmode')
        if ($null -eq $mode) { $mode = $existing.Xml.CreateElement('startmode'); [void]$existing.Xml.service.AppendChild($mode) }
        $mode.InnerText = 'Manual'
        foreach ($node in @($existing.Xml.SelectNodes('/service/delayedAutoStart | /service/onfailure | /service/resetfailure'))) { [void]$node.ParentNode.RemoveChild($node) }
        $existing.Xml.Save($existing.XmlPath)
    }
    $serviceName = $existing.Service.Name
    Set-Service -Name $serviceName -StartupType Manual
    # The guard is the only recovery/start driver. Disable inherited SCM automatic restart.
    $recoveryResult = Invoke-GuardNative "$env:SystemRoot\System32\sc.exe" @('failure', $serviceName, 'reset=', '0', 'actions=', '')
    if ($recoveryResult.ExitCode -ne 0) { throw 'FRPC_SERVICE_RECOVERY_SETUP_FAILED' }
    $binding = Get-GuardFrpcBinding $serviceName
    Grant-GuardServiceControl $serviceName $sid
    foreach ($path in @($guardDestination, $configDestination, $binding.Wrapper, $binding.XmlPath, $binding.Executable)) {
        Set-GuardFileAcl $path $sid ([Security.AccessControl.FileSystemRights]::ReadAndExecute)
    }
    Grant-GuardConfigMetadataRead $binding.Config $sid
    # Separate writable state/logs; never grant this task write access to frpc.toml/token.
    $guardLogDirectory = Join-Path $logDirectory 'frp-ip-guard-state'
    if (-not (Test-Path -LiteralPath $guardLogDirectory)) { [void](New-Item -ItemType Directory -Path $guardLogDirectory) }
    $guardLogPath = Join-Path $logDirectory 'frp-ip-guard.log'
    if (-not (Test-Path -LiteralPath $guardLogPath)) { [IO.File]::WriteAllText($guardLogPath, '') }
    Set-GuardFileAcl $guardLogPath $sid ([Security.AccessControl.FileSystemRights]::Modify)
    # Atomic state replacement requires create/delete-child access in the guard state directory.
    # Use the dedicated directory for state/lock while keeping the public log at its frozen path.
    Set-GuardFileAcl $guardLogDirectory $sid ([Security.AccessControl.FileSystemRights]::Modify) -Directory
    Set-GuardFileAcl $cliDirectory $sid ([Security.AccessControl.FileSystemRights]::FullControl) -Directory
    foreach ($file in @(Get-ChildItem -LiteralPath $cliDirectory -Force -File -Recurse)) {
        Set-GuardFileAcl $file.FullName $sid ([Security.AccessControl.FileSystemRights]::FullControl)
    }
    $xml = New-GuardTaskXml $sid $serviceName
    try {
        $password = $TaskCredential.GetNetworkCredential().Password
        Register-ScheduledTask -TaskName 'AIVO-FRP-IP-Guard' -Xml $xml -User $UserName -Password $password -Force | Out-Null
    } finally { $password = $null; $TaskCredential = $null }
    $task = Get-ScheduledTask -TaskName 'AIVO-FRP-IP-Guard'
    if ($task.Principal.LogonType -ne 'Password' -or $task.Settings.MultipleInstances -ne 'IgnoreNew' -or
        $task.Settings.ExecutionTimeLimit -ne 'PT2M') { throw 'TASK_SETUP_VERIFICATION_FAILED' }
    Write-Output ('SETUP_PASS: service=' + $serviceName + '; startup=Manual; task=AIVO-FRP-IP-Guard; no cloud mutation performed by installer.')
}

if ($MyInvocation.InvocationName -ne '.') { Install-AivoFrpGuard }
