#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$envFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "No .env found. Copy env.local.sample to .env and add your Azure keys:" -ForegroundColor Yellow
    Write-Host "  Copy-Item env.local.sample .env" -ForegroundColor Cyan
    exit 1
}

$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating backend venv and installing dependencies..."
    py -3 -m venv .venv
    & (Join-Path $RepoRoot ".venv\Scripts\pip.exe") install -r requirements.txt
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}

Write-Host "Starting backend at http://127.0.0.1:8000 (Ctrl+C to stop)" -ForegroundColor Green
& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
