[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleasePath,
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedCommit,
    [string]$BackupParent = 'E:\AI-Video-Ops-Backup',
    [string]$ReceiptPath = 'E:\AI-Video-Ops-Config\creative-authority-installation.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
$resolvedRelease = (Resolve-Path -LiteralPath $ReleasePath).Path
$python = Join-Path $resolvedRepo 'ops-pipeline\.venv\Scripts\python.exe'
$tool = Join-Path $resolvedRepo 'deploy\creative-authority\verify_release.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-Path -LiteralPath $tool -PathType Leaf)) {
    throw 'Current checkout or ops-pipeline Python is missing.'
}
$listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    throw 'Internal Console still listens on port 8000. Stop it after checking active tasks.'
}
$pipeline = Join-Path $resolvedRepo 'ops-pipeline'
& $python $tool plan --release $resolvedRelease --pipeline-root $pipeline --repo-root $resolvedRepo
if ($LASTEXITCODE -ne 0) { throw 'Creative Authority release planning failed.' }
& $python $tool install --release $resolvedRelease --pipeline-root $pipeline --repo-root $resolvedRepo --expected-commit $ExpectedCommit --backup-parent $BackupParent --receipt $ReceiptPath
if ($LASTEXITCODE -ne 0) { throw 'Creative Authority installation failed.' }
