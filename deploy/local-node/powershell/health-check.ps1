$ErrorActionPreference = "Stop"
$healthUri = "http://127.0.0.1:8000/api/health"
$response = Invoke-RestMethod -Uri $healthUri -Method Get -TimeoutSec 5
if ($response.status -ne "ok") {
    throw "Internal Console health check returned an unexpected status."
}
Write-Output "PASS: Internal Console is healthy on 127.0.0.1:8000."
