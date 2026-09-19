[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$EnvironmentFile,
    [switch]$IncludeTestDependencies
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)."
    }
}

function Get-EnvFileSetting {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)\s*$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

function Require-CommandPath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Missing host prerequisite: $Name"
    }
    return $command.Source
}

function Assert-Python312 {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    $version = (& $PythonPath -c "import platform; print(platform.python_version())").Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^3\.12\.') {
        throw "Python 3.12 is required; found '$version' at $PythonPath."
    }
    return $version
}

$resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
$resolvedEnv = (Resolve-Path -LiteralPath $EnvironmentFile).Path
$consoleRoot = Join-Path $resolvedRepo "internal-console"
$pipelineRoot = Join-Path $resolvedRepo "ops-pipeline"
$pipelineRequirements = Join-Path $pipelineRoot "requirements.txt"
$pipelineDevRequirements = Join-Path $pipelineRoot "requirements-dev.txt"

foreach ($requiredPath in @(
    (Join-Path $consoleRoot "pyproject.toml"),
    $pipelineRequirements,
    $pipelineDevRequirements
)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Missing repository dependency contract: $requiredPath"
    }
}

$git = Require-CommandPath "git.exe"
$node = Require-CommandPath "node.exe"
$npm = Require-CommandPath "npm.cmd"
$ollama = Require-CommandPath "ollama.exe"

$launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
if ($null -ne $launcher) {
    $basePython = (& $launcher.Source -3.12 -c "import sys; print(sys.executable)").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "The Python launcher could not resolve Python 3.12."
    }
} else {
    $basePython = Require-CommandPath "python.exe"
}
$baseVersion = Assert-Python312 $basePython

Invoke-CheckedNative $git @("--version") "Git check failed"
Invoke-CheckedNative $node @("--version") "Node check failed"
Invoke-CheckedNative $npm @("--version") "npm check failed"
Invoke-CheckedNative $ollama @("--version") "Ollama check failed"

$ollamaModels = & $ollama list 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Ollama is installed but its local service is unavailable."
}
if (($ollamaModels -join "`n") -notmatch '(?m)^qwen3-vl:4b-instruct\s') {
    throw "Required host model qwen3-vl:4b-instruct is not installed."
}

$whisperModel = Get-EnvFileSetting $resolvedEnv "AIVO_WHISPER_MODEL"
if ([string]::IsNullOrWhiteSpace($whisperModel)) {
    throw "Production environment must set AIVO_WHISPER_MODEL."
}
if ([System.IO.Path]::IsPathFullyQualified($whisperModel)) {
    if (-not (Test-Path -LiteralPath $whisperModel -PathType Container)) {
        throw "AIVO_WHISPER_MODEL absolute directory does not exist: $whisperModel"
    }
    foreach ($requiredModelFile in @(
        "config.json",
        "model.bin",
        "preprocessor_config.json",
        "tokenizer.json",
        "vocabulary.json"
    )) {
        $modelFile = Join-Path $whisperModel $requiredModelFile
        if (-not (Test-Path -LiteralPath $modelFile -PathType Leaf)) {
            throw "Whisper model directory is incomplete; missing $requiredModelFile."
        }
    }
    Write-Output "PASS: local Whisper directory exists: $whisperModel"
} else {
    Write-Output "PASS: Whisper model name is configured: $whisperModel"
}

$consoleVenv = Join-Path $consoleRoot ".venv"
$pipelineVenv = Join-Path $pipelineRoot ".venv"
$consolePython = Join-Path $consoleVenv "Scripts\python.exe"
$pipelinePython = Join-Path $pipelineVenv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $consolePython -PathType Leaf)) {
    Invoke-CheckedNative $basePython @("-m", "venv", $consoleVenv) "Internal Console venv creation failed"
}
if (-not (Test-Path -LiteralPath $pipelinePython -PathType Leaf)) {
    Invoke-CheckedNative $basePython @("-m", "venv", $pipelineVenv) "ops-pipeline venv creation failed"
}

$consoleVenvVersion = Assert-Python312 $consolePython
$pipelineVenvVersion = Assert-Python312 $pipelinePython

$consoleInstall = $consoleRoot
$pipelineInstall = $pipelineRequirements
if ($IncludeTestDependencies) {
    $consoleInstall = "${consoleRoot}[dev]"
    $pipelineInstall = $pipelineDevRequirements
}

Invoke-CheckedNative $consolePython @("-m", "pip", "install", "-e", $consoleInstall) "Internal Console dependency install failed"
Invoke-CheckedNative $pipelinePython @("-m", "pip", "install", "-r", $pipelineInstall) "ops-pipeline dependency install failed"
Invoke-CheckedNative $consolePython @("-m", "pip", "check") "Internal Console pip check failed"
Invoke-CheckedNative $pipelinePython @("-m", "pip", "check") "ops-pipeline pip check failed"

Write-Output "PASS: reproducible runtime dependencies are installed."
Write-Output "INFO: base Python=$baseVersion; Console Python=$consoleVenvVersion; Pipeline Python=$pipelineVenvVersion"
Write-Output "INFO: no model was run or downloaded, no production data was migrated, and no system setting was changed."
