#Requires -Version 5.1
<#
.SYNOPSIS
  Pulls Azure OpenAI + Document Intelligence endpoint/key from YOUR subscription (after az login)
  and prints environment lines to paste into Render Dashboard.

.DESCRIPTION
  This script cannot run inside Cursor on your behalf — you run it on your Windows machine.
  Prerequisite: Azure CLI installed, `az login` completed, access to the resource group.

.EXAMPLE
  .\scripts\Export-RenderEnvFromAzure.ps1 -ResourceGroup "my-rg" -OpenAIResourceName "my-openai" `
    -DocumentIntelligenceResourceName "my-doc-intel" -OpenAIDeployment "gpt-4o"

.EXAMPLE
  .\scripts\Export-RenderEnvFromAzure.ps1 -ResourceGroup "my-rg" -OpenAIResourceName "my-openai" -OpenAIDeployment "gpt-4"
  # Skips Document Intelligence lines if -DocumentIntelligenceResourceName omitted
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$OpenAIResourceName,

    [string]$DocumentIntelligenceResourceName = "",

    [string]$OpenAIDeployment = "",

    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

function Assert-AzCli {
    $az = Get-Command az -ErrorAction SilentlyContinue
    if (-not $az) {
        Write-Error "Install Azure CLI: https://learn.microsoft.com/cli/azure/install-azure-cli-windows"
    }
    az account show 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Run: az login"
    }
}

function Get-CsEndpoint {
    param([string]$Name)
    $raw = az cognitiveservices account show -g $ResourceGroup -n $Name --query "properties.endpoint" -o tsv 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return $raw.Trim().TrimEnd("/")
}

function Get-CsKey1 {
    param([string]$Name)
    $k = az cognitiveservices account keys list -g $ResourceGroup -n $Name --query "key1" -o tsv 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($k)) {
        return $null
    }
    return $k.Trim()
}

Assert-AzCli

$openaiEndpoint = Get-CsEndpoint -Name $OpenAIResourceName
$openaiKey = Get-CsKey1 -Name $OpenAIResourceName
if (-not $openaiEndpoint -or -not $openaiKey) {
    Write-Error "Could not read OpenAI resource '$OpenAIResourceName' in group '$ResourceGroup'. Check names and permissions."
}

if (-not $OpenAIDeployment) {
    $names = az cognitiveservices account deployment list -g $ResourceGroup -n $OpenAIResourceName --query "[].name" -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and $names) {
        $first = ($names -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
        if ($first) {
            Write-Warning "Using first deployment name '$first'. Pass -OpenAIDeployment to override."
            $OpenAIDeployment = $first
        }
    }
    if (-not $OpenAIDeployment) {
        Write-Error "Could not list deployments. Pass -OpenAIDeployment explicitly (name in Azure OpenAI → Deployments)."
    }
}

$lines = @()
$lines += "# --- Paste each KEY and VALUE into Render → Environment ---"
$lines += "AZURE_OPENAI_API_KEY=$openaiKey"
$lines += "AZURE_OPENAI_ENDPOINT=$openaiEndpoint"
$lines += "AZURE_OPENAI_API_VERSION=2024-02-15-preview"
$lines += "AZURE_OPENAI_DEPLOYMENT=$OpenAIDeployment"

if ($DocumentIntelligenceResourceName) {
    $docEp = Get-CsEndpoint -Name $DocumentIntelligenceResourceName
    $docKey = Get-CsKey1 -Name $DocumentIntelligenceResourceName
    if (-not $docEp -or -not $docKey) {
        Write-Error "Could not read Document Intelligence resource '$DocumentIntelligenceResourceName'."
    }
    $lines += "AZURE_DOC_INTELLIGENCE_ENDPOINT=$docEp"
    $lines += "AZURE_DOC_INTELLIGENCE_API_KEY=$docKey"
    $lines += "AZURE_DOC_INTELLIGENCE_API_VERSION=2024-11-30"
} else {
    $lines += "# AZURE_DOC_INTELLIGENCE_* — add a second resource name with -DocumentIntelligenceResourceName, or paste manually."
}

$lines += "# OCR_POLL_TIMEOUT_SECONDS=25   # optional; render.yaml already sets this"
$lines += "# --- Still add in Render (not from Azure CLI): NUDGE_TRIAL_LICENSE_KEYS, NUDGE_CUSTOMER_LICENSE_KEYS, etc. ---"

$text = ($lines -join "`n")
Write-Host $text

if ($OutFile) {
    $dir = Split-Path -Parent $OutFile
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Set-Content -Path $OutFile -Value $text -Encoding utf8
    Write-Host "`nWrote: $OutFile" -ForegroundColor Green
}

Write-Host "`nSecurity: do not commit this output to git. Delete the file after pasting into Render." -ForegroundColor Yellow
