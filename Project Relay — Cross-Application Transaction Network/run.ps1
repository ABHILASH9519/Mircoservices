[CmdletBinding()]
param([ValidateSet("Help","Init","Up","Down","Logs","Test")][string]$Action = "Help")
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    switch ($Action) {
        "Help" { Write-Output "Usage: run.ps1 -Action Init | Up | Down | Logs | Test" }
        "Init" { & python -m relay.init_env }
        "Up" { & docker compose up -d --build }
        "Down" { & docker compose down }
        "Logs" { & docker compose logs -f }
        "Test" { & python -m unittest discover -s tests }
    }
    if ($Action -ne "Help" -and $LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}
