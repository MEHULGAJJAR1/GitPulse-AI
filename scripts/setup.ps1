# GitPulse setup for Windows PowerShell 5.1+ / PowerShell 7.
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 [-SeedDemo] [-SkipFrontend] [-RunTests]
# Requires: Python 3.11+ (py launcher), Node.js 20+, PostgreSQL 14+ reachable at DATABASE_URL.
param(
  [switch]$SeedDemo,
  [switch]$SkipFrontend,
  [switch]$RunTests
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Log($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Invoke-Checked($file, [string[]]$args_) {
  & $file @args_
  if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $file $($args_ -join ' ')" }
}

$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py", "-3" } else { "python" }
Invoke-Checked $py[0] @($py[1..($py.Length)] + @("-c", "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"))

Log "Creating virtualenv at .venv"
if (-not (Test-Path ".venv")) { Invoke-Checked $py[0] @($py[1..($py.Length)] + @("-m", "venv", ".venv")) }
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

Log "Installing Python dependencies (backend, ELT, ML, tests)"
Invoke-Checked $VenvPy @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $VenvPy @("-m", "pip", "install", "-r", "requirements-dev.txt")

if (-not (Test-Path ".env")) {
  Log "Creating .env with freshly generated API keys"
  $code = @'
import secrets, pathlib
tpl = pathlib.Path(".env.example").read_text()
for name in ["API_KEYS_VIEWER", "API_KEYS_ANALYST", "API_KEYS_ADMIN"]:
    tpl = tpl.replace(f"{name}=change-me-{name.split('_')[-1].lower()}-key", f"{name}={secrets.token_urlsafe(24)}")
tpl = tpl.replace("POSTGRES_PASSWORD=change-me-postgres", f"POSTGRES_PASSWORD={secrets.token_urlsafe(16)}")
pathlib.Path(".env").write_text(tpl)
'@
  Invoke-Checked $VenvPy @("-c", $code)
  Write-Host "Keys were written to .env (keep it private). Add GITHUB_TOKEN to .env for higher GitHub rate limits."
} else {
  Log ".env already exists; leaving it unchanged"
}

Log "Applying database migrations (alembic)"
Push-Location backend
Invoke-Checked (Join-Path $Root ".venv\Scripts\alembic.exe") @("upgrade", "head")
Pop-Location

if ($SeedDemo) {
  Log "Seeding LABELLED SYNTHETIC demo data (not GitHub data)"
  Push-Location data_pipeline
  Invoke-Checked $VenvPy @("-m", "gitpulse_elt", "run", "--mode", "synthetic_seed")
  Pop-Location
}

if (-not $SkipFrontend) {
  Log "Installing and building the frontend"
  Push-Location frontend
  Invoke-Checked "npm.cmd" @("ci")
  Invoke-Checked "npm.cmd" @("run", "build")
  Pop-Location
}

if ($RunTests) { & (Join-Path $PSScriptRoot "test.ps1") }

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  Start API:      .\scripts\run.ps1 api"
Write-Host "  Start web app:  .\scripts\run.ps1 web   (http://localhost:5173)"
Write-Host "  Sign in with the API_KEYS_ADMIN value from .env"
