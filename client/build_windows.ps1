param(
    [switch]$SkipInstaller,
    [string]$ProductionBackendUrl = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Missing client venv. Create it first with: python -m venv .venv"
}

$versionInfoPath = Join-Path $root "release\version.json"
if (-not (Test-Path $versionInfoPath)) {
    throw "Missing version source-of-truth file: $versionInfoPath"
}
$versionInfo = Get-Content $versionInfoPath -Raw | ConvertFrom-Json
$appVersion = [string]$versionInfo.version
if ([string]::IsNullOrWhiteSpace($appVersion)) {
    throw "release/version.json must include a non-empty version"
}

$runtimePath = Join-Path $root "release\client_runtime.json"
if ($ProductionBackendUrl -and -not [string]::IsNullOrWhiteSpace($ProductionBackendUrl)) {
    $url = $ProductionBackendUrl.Trim().TrimEnd("/")
    $payload = @{ backend_base_url = $url } | ConvertTo-Json -Compress
    Set-Content -Path $runtimePath -Value $payload -Encoding utf8
    Write-Host "Wrote backend URL to release\client_runtime.json"
} else {
    Write-Warning "No -ProductionBackendUrl: using release\client_runtime.json as-is (null URL falls back to localhost unless users set NUDGE_BACKEND_BASE_URL)."
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-build.txt

& ".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "nudge.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

if ($SkipInstaller) {
    Write-Host "Build completed: client\dist\Nudge"
    exit 0
}

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $defaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $defaultIscc) {
        $iscc = Get-Item $defaultIscc
    }
}
if (-not $iscc) {
    $userIscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    if (Test-Path $userIscc) {
        $iscc = Get-Item $userIscc
    }
}

if (-not $iscc) {
    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or run with -SkipInstaller."
}

& $iscc.Path "/DMyAppVersion=$appVersion" "installer\NudgeSetup.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed."
}
Write-Host "Installer created under client\installer\Output"
