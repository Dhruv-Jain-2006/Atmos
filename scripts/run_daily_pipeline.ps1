<#
.SYNOPSIS
    Runs the Atmos daily pipeline locally (sync + detect).

.DESCRIPTION
    Executes the same two-stage pipeline as the GitHub Actions workflow:
    1. workers.github.sync_metrics — incremental GitHub metrics ingestion
    2. workers.detection.compute_signals — signal computation + classification

    Use this to test the pipeline before relying on the scheduled workflow.

.PARAMETER SkipDetection
    Skip the detection step (useful for testing ingestion only).

.EXAMPLE
    .\scripts\run_daily_pipeline.ps1
    .\scripts\run_daily_pipeline.ps1 -SkipDetection
#>
param(
    [switch]$SkipDetection
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Atmos Daily Pipeline" -ForegroundColor Cyan
Write-Host " $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Verify environment
if (-not $env:DATABASE_URL_DIRECT -and -not $env:DATABASE_URL) {
    if (Test-Path "$RepoRoot\.env") {
        Write-Host "[INFO] Loading .env from $RepoRoot\.env" -ForegroundColor Yellow
        Get-Content "$RepoRoot\.env" | ForEach-Object {
            if ($_ -match "^\s*([^#][^=]+)=(.+)$") {
                $key = $Matches[1].Trim()
                $val = $Matches[2].Trim()
                if (-not (Get-Item "env:$key" -ErrorAction SilentlyContinue)) {
                    Set-Item "env:$key" $val
                }
            }
        }
    }
}

if (-not $env:GITHUB_TOKEN) {
    Write-Host "[ERROR] GITHUB_TOKEN not set" -ForegroundColor Red
    exit 1
}
if (-not $env:DATABASE_URL_DIRECT -and -not $env:DATABASE_URL) {
    Write-Host "[ERROR] DATABASE_URL_DIRECT not set" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[STEP 1] Syncing GitHub metrics..." -ForegroundColor Green
Push-Location $RepoRoot
try {
    & uv run python -m workers.github.sync_metrics --budget 800
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] sync_metrics failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

if ($SkipDetection) {
    Write-Host "[INFO] Skipping detection (--SkipDetection)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " Pipeline completed (sync only)" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    exit 0
}

Write-Host ""
Write-Host "[STEP 2] Computing signals..." -ForegroundColor Green
Push-Location $RepoRoot
try {
    & uv run python -m workers.detection.compute_signals
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] compute_signals failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Pipeline completed successfully" -ForegroundColor Green
Write-Host " $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
