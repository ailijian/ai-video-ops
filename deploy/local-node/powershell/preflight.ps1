param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$EnvironmentFile
)

$ErrorActionPreference = "Stop"
$resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
$resolvedEnv = (Resolve-Path -LiteralPath $EnvironmentFile).Path
$required = @(
    "$resolvedRepo\internal-console\.venv\Scripts\python.exe",
    "$resolvedRepo\ops-pipeline\.venv\Scripts\python.exe",
    "$resolvedRepo\internal-console\app\main.py"
)
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}

$envText = Get-Content -LiteralPath $resolvedEnv -Raw
foreach ($requiredKey in @("AIVO_CONSOLE_DB", "AIVO_PIPELINE_PYTHON", "AIVO_SECURE_COOKIES")) {
    if ($envText -notmatch "(?m)^$requiredKey=") {
        throw "Missing production setting: $requiredKey"
    }
}
if ($envText -notmatch "(?m)^AIVO_SECURE_COOKIES=1\s*$") {
    throw "Production environment must set AIVO_SECURE_COOKIES=1."
}

$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    if ($listener.LocalAddress -notin @("127.0.0.1", "::1")) {
        throw "Port 8000 is listening beyond loopback: $($listener.LocalAddress)"
    }
}

Write-Output "PASS: paths, environment contract, and loopback listener are safe."
Write-Output "INFO: this script does not install services or modify Windows settings."
