#Requires -Version 5.1
param(
    # Skip API key so the app shows the Hebrew activation dialog (use trial key from .env).
    [switch]$UseActivation
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ClientDir = Join-Path $RepoRoot "client"
Set-Location $ClientDir

$env:NUDGE_BACKEND_BASE_URL = "http://127.0.0.1:8000"
if (-not $UseActivation) {
    $env:NUDGE_BACKEND_API_KEY = "local-dev-shared-api-key-change-me"
} else {
    Remove-Item Env:\NUDGE_BACKEND_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\NUDGE_BACKEND_ACCESS_TOKEN -ErrorAction SilentlyContinue
}

$venvPython = Join-Path $ClientDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating client venv and installing dependencies..."
    py -3 -m venv .venv
    & (Join-Path $ClientDir ".venv\Scripts\pip.exe") install -r requirements.txt
    $venvPython = Join-Path $ClientDir ".venv\Scripts\python.exe"
}

Write-Host "Starting Nudge client (tray). Backend: $env:NUDGE_BACKEND_BASE_URL" -ForegroundColor Green
if ($UseActivation) {
    Write-Host "Activation mode: enter trial key from NUDGE_TRIAL_LICENSE_KEYS in .env" -ForegroundColor Yellow
}
& $venvPython -m app.main
