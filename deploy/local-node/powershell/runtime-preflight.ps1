[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,
    [Parameter(Mandatory = $true)]
    [string]$EnvironmentFile
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-CapturedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    $output = & $FilePath @ArgumentList 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)."
    }
    return ($output -join "`n").Trim()
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

$resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
$resolvedEnv = (Resolve-Path -LiteralPath $EnvironmentFile).Path
$git = Require-CommandPath "git.exe"
$node = Require-CommandPath "node.exe"
$npm = Require-CommandPath "npm.cmd"
$ollama = Require-CommandPath "ollama.exe"
$nvidiaSmi = Require-CommandPath "nvidia-smi.exe"
$consolePython = Join-Path $resolvedRepo "internal-console\.venv\Scripts\python.exe"
$pipelinePython = Join-Path $resolvedRepo "ops-pipeline\.venv\Scripts\python.exe"

foreach ($pythonPath in @($consolePython, $pipelinePython)) {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Missing runtime Python: $pythonPath"
    }
}

$head = Invoke-CapturedNative $git @("-C", $resolvedRepo, "rev-parse", "HEAD") "Git HEAD check failed"
$consoleVersion = Invoke-CapturedNative $consolePython @("-c", "import platform; print(platform.python_version())") "Internal Console Python check failed"
$pipelineVersion = Invoke-CapturedNative $pipelinePython @("-c", "import platform; print(platform.python_version())") "ops-pipeline Python check failed"
if ($consoleVersion -notmatch '^3\.12\.' -or $pipelineVersion -notmatch '^3\.12\.') {
    throw "Both runtime venvs must use Python 3.12."
}

Write-Output "INFO: Git HEAD=$head"
Write-Output "INFO: Internal Console Python=$consoleVersion ($consolePython)"
Write-Output "INFO: ops-pipeline Python=$pipelineVersion ($pipelinePython)"

foreach ($package in @("faster-whisper", "ctranslate2", "ollama", "openai", "opencv-python", "openpyxl", "scenedetect")) {
    $version = Invoke-CapturedNative $pipelinePython @(
        "-c",
        "import importlib.metadata as m; print(m.version('$package'))"
    ) "Missing critical ops-pipeline package: $package"
    Write-Output "INFO: ops-pipeline package $package=$version"
}

$nodeVersion = Invoke-CapturedNative $node @("--version") "Node check failed"
$npmVersion = Invoke-CapturedNative $npm @("--version") "npm check failed"
$ollamaVersion = Invoke-CapturedNative $ollama @("--version") "Ollama check failed"
$ollamaModels = Invoke-CapturedNative $ollama @("list") "Ollama model inventory failed"
if ($ollamaModels -notmatch '(?m)^qwen3-vl:4b-instruct\s') {
    throw "Required host model qwen3-vl:4b-instruct is not installed."
}
$gpu = Invoke-CapturedNative $nvidiaSmi @(
    "--query-gpu=name,driver_version,memory.total",
    "--format=csv,noheader"
) "NVIDIA GPU detection failed"

Write-Output "INFO: Node=$nodeVersion; npm=$npmVersion"
Write-Output "INFO: Ollama=$ollamaVersion"
Write-Output "PASS: qwen3-vl:4b-instruct is present (inventory only; no model call)."
Write-Output "INFO: GPU=$gpu"

$whisperModel = Get-EnvFileSetting $resolvedEnv "AIVO_WHISPER_MODEL"
$consoleDb = Get-EnvFileSetting $resolvedEnv "AIVO_CONSOLE_DB"
$configuredPipelinePython = Get-EnvFileSetting $resolvedEnv "AIVO_PIPELINE_PYTHON"
$secureCookies = Get-EnvFileSetting $resolvedEnv "AIVO_SECURE_COOKIES"

if ([string]::IsNullOrWhiteSpace($whisperModel)) {
    throw "Missing production setting: AIVO_WHISPER_MODEL"
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
    Write-Output "PASS: AIVO_WHISPER_MODEL=$whisperModel (required local files present)"
} else {
    Write-Output "INFO: AIVO_WHISPER_MODEL=$whisperModel (model name; local files not applicable)"
}

if ([string]::IsNullOrWhiteSpace($consoleDb) -or -not [System.IO.Path]::IsPathFullyQualified($consoleDb)) {
    throw "AIVO_CONSOLE_DB must be an absolute path."
}
if ([string]::IsNullOrWhiteSpace($configuredPipelinePython) -or -not (Test-Path -LiteralPath $configuredPipelinePython -PathType Leaf)) {
    throw "AIVO_PIPELINE_PYTHON must point to the ops-pipeline runtime Python."
}
if ($secureCookies -ne "1") {
    throw "AIVO_SECURE_COOKIES must be 1 for production."
}

Write-Output "INFO: Console DB=$consoleDb"
Write-Output "INFO: Pipeline Python=$configuredPipelinePython"
Write-Output "PASS: AIVO_SECURE_COOKIES=1"
Write-Output "PASS: runtime preflight completed without exposing secrets or calling a model."
