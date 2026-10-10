# Runs every test layer. Live API/DQ tests run only when the server/database is reachable.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "== Python: unit, ML evaluation, data quality, API" -ForegroundColor Cyan
if (Test-Path ".env") {
  $env_ = @{}
  Get-Content .env | Where-Object { $_ -match "=" -and $_ -notmatch "^#" } | ForEach-Object { $k, $v = $_ -split "=", 2; $env_[$k] = $v }
  $pick = { param($k) ($env_[$k] -split ",")[0] -replace "^.*:", "" }
  $env:GITPULSE_TEST_KEYS = ((& $pick "API_KEYS_VIEWER"), (& $pick "API_KEYS_ANALYST"), (& $pick "API_KEYS_ADMIN")) -join ","
}
if (-not $env:GITPULSE_DQ_LIVE) { $env:GITPULSE_DQ_LIVE = "1" }
& $VenvPy -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host "== Frontend: build and unit/component tests" -ForegroundColor Cyan
Push-Location frontend
npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
npx.cmd vitest run; if ($LASTEXITCODE -ne 0) { throw "vitest failed" }
Pop-Location
Write-Host "All selected test layers passed." -ForegroundColor Green
