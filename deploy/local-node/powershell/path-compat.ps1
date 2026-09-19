function Test-AbsoluteWindowsPath {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }

    return [bool](
        ($Path -match '^[A-Za-z]:[\\/]') -or
        ($Path -match '^\\\\[^\\/]+[\\/][^\\/]+')
    )
}

function Test-WindowsPathLike {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }

    return [bool](
        ($Path -match '[\\/]') -or
        ($Path -match '^[A-Za-z]:')
    )
}

function Assert-WindowsPathCompatibility {
    [CmdletBinding()]
    param()

    foreach ($path in @(
        "E:\ai-model-cache\faster-whisper-large-v3",
        "E:/ai-model-cache/faster-whisper-large-v3",
        "\\server\share\path"
    )) {
        if (-not (Test-AbsoluteWindowsPath $path)) {
            throw "Absolute Windows path compatibility failed: $path"
        }
    }

    foreach ($path in @("relative\path", ".\path", "E:relative-path")) {
        if (Test-AbsoluteWindowsPath $path) {
            throw "Relative Windows path was accepted: $path"
        }
        if (-not (Test-WindowsPathLike $path)) {
            throw "Relative path-like value was not classified for rejection: $path"
        }
    }

    if (Test-WindowsPathLike "large-v3") {
        throw "A plain Whisper model name was classified as a filesystem path."
    }
}
