[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (
    ($PSVersionTable.PSEdition -ne "Desktop") -or
    ($PSVersionTable.PSVersion.Major -ne 5) -or
    ($PSVersionTable.PSVersion.Minor -lt 1)
) {
    throw "This smoke test must run with Windows PowerShell 5.1 via powershell.exe."
}

$resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
$localNodeRoot = Join-Path $resolvedRepo "deploy\local-node"
$powershellRoot = Join-Path $localNodeRoot "powershell"
$helper = Join-Path $powershellRoot "path-compat.ps1"
. $helper

$accepted = @(
    "E:\ai-model-cache\faster-whisper-large-v3",
    "E:/ai-model-cache/faster-whisper-large-v3",
    "\\server\share\path"
)
foreach ($path in $accepted) {
    if (-not (Test-AbsoluteWindowsPath $path)) {
        throw "Expected an absolute Windows path: $path"
    }
}

$rejected = @(
    "relative\path",
    ".\path",
    "E:relative-path"
)
foreach ($path in $rejected) {
    if (Test-AbsoluteWindowsPath $path) {
        throw "Expected a non-absolute Windows path: $path"
    }
    if (-not (Test-WindowsPathLike $path)) {
        throw "Expected a path-like value for fail-closed validation: $path"
    }
}

if (Test-WindowsPathLike "large-v3") {
    throw "A plain Whisper model name must not be classified as a filesystem path."
}

$environmentTemplate = Join-Path $resolvedRepo "deploy\local-node\env.production.example"
$bootstrapOutput = & (Join-Path $powershellRoot "bootstrap-runtime.ps1") `
    -RepoRoot $resolvedRepo `
    -EnvironmentFile $environmentTemplate `
    -PathCompatibilitySmoke
if (($bootstrapOutput -join "`n") -notmatch 'PASS: bootstrap-runtime') {
    throw "bootstrap-runtime.ps1 compatibility smoke did not complete."
}
$preflightOutput = & (Join-Path $powershellRoot "runtime-preflight.ps1") `
    -RepoRoot $resolvedRepo `
    -EnvironmentFile $environmentTemplate `
    -PathCompatibilitySmoke
if (($preflightOutput -join "`n") -notmatch 'PASS: runtime-preflight') {
    throw "runtime-preflight.ps1 compatibility smoke did not complete."
}

$formalScripts = Get-ChildItem -LiteralPath $localNodeRoot -Filter "*.ps1" -File -Recurse
foreach ($script in $formalScripts) {
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $script.FullName,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if ($parseErrors.Count -gt 0) {
        $messages = ($parseErrors | ForEach-Object { $_.Message }) -join "; "
        throw "PowerShell 5.1 syntax failed for $($script.Name): $messages"
    }

    $source = Get-Content -LiteralPath $script.FullName -Raw
    $unsupportedMethod = "IsPath" + "FullyQualified"
    if ($source -match $unsupportedMethod) {
        throw "PowerShell 5.1-incompatible Path API remains in $($script.Name)."
    }
}

foreach ($entryPoint in @("bootstrap-runtime.ps1", "runtime-preflight.ps1")) {
    $source = Get-Content -LiteralPath (Join-Path $powershellRoot $entryPoint) -Raw
    if ($source -notmatch 'Test-AbsoluteWindowsPath') {
        throw "$entryPoint does not use the canonical Windows path helper."
    }
}

Write-Output "PASS: bootstrap/runtime-preflight path compatibility on Windows PowerShell 5.1."
