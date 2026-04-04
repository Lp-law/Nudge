param(
    [switch]$SkipInstaller
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
