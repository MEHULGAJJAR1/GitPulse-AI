# Start a GitPulse service in the foreground.  Usage: .\scripts\run.ps1 api|web|pipeline
param([Parameter(Mandatory = $true)][ValidateSet("api", "web", "pipeline")][string]$Service)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
switch ($Service) {
  "api"      { Set-Location (Join-Path $Root "backend"); & $VenvPy -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload }
  "web"      { Set-Location (Join-Path $Root "frontend"); npm.cmd run dev }
  "pipeline" { Set-Location (Join-Path $Root "data_pipeline"); & $VenvPy -m gitpulse_elt run }
}
