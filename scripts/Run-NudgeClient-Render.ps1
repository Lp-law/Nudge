#Requires -Version 5.1
param(
    # Override with your Render URL, or set env NUDGE_RENDER_BACKEND_URL once (system / user).
    [string]$BackendUrl = $env:NUDGE_RENDER_BACKEND_URL
)

$ErrorActionPreference = "Stop"
if (-not $BackendUrl) {
    $BackendUrl = "https://nudge-mvp-backend.onrender.com"
}
$BackendUrl = $BackendUrl.TrimEnd("/")

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ClientDir = Join-Path $RepoRoot "client"
Set-Location $ClientDir

$env:NUDGE_BACKEND_BASE_URL = $BackendUrl
Remove-Item Env:\NUDGE_BACKEND_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\NUDGE_BACKEND_ACCESS_TOKEN -ErrorAction SilentlyContinue

$venvPython = Join-Path $ClientDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating client venv and installing dependencies..."
    py -3 -m venv .venv
    & (Join-Path $ClientDir ".venv\Scripts\pip.exe") install -r requirements.txt
    $venvPython = Join-Path $ClientDir ".venv\Scripts\python.exe"
}

Write-Host "Starting Nudge client (tray). Backend: $env:NUDGE_BACKEND_BASE_URL" -ForegroundColor Green
Write-Host "If prompted, enter trial key from server .env (NUDGE_TRIAL_LICENSE_KEYS)." -ForegroundColor DarkGray
& $venvPython -m app.main
