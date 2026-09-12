#Requires -Version 5.1
<#
  Run once per machine. Safe to re-run: every step checks before acting.

  Assumes PostgreSQL is installed and the pgguru role/databases exist:

      psql -U postgres
      CREATE USER pgguru WITH PASSWORD 'pgguru' CREATEDB;
      CREATE DATABASE pgguru OWNER pgguru;
      CREATE DATABASE pgguru_test OWNER pgguru;
#>

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$VenvPy   = Join-Path $Backend '.venv\Scripts\python.exe'

function Step($n, $text) {
    Write-Host ''
    Write-Host "  [$n] $text" -ForegroundColor Cyan
}

function Fail($text) {
    Write-Host ''
    Write-Host "  FAILED: $text" -ForegroundColor Red
    Write-Host ''
    exit 1
}

Write-Host ''
Write-Host '  PGuru first-time setup' -ForegroundColor Cyan
Write-Host '  =======================' -ForegroundColor Cyan

# --- 1. python -------------------------------------------------------------
Step 1 'Checking Python'
try {
    $pyv = (python --version 2>&1) -replace 'Python ', ''
    Write-Host "      Python $pyv"
    if ($pyv -notmatch '^3\.(11|12|13)') {
        Write-Host '      Warning: 3.11 or 3.12 is what this project is tested on.' -ForegroundColor Yellow
    }
} catch { Fail 'python is not on PATH. Install 3.11 or 3.12 and tick "Add to PATH".' }

# --- 2. venv ---------------------------------------------------------------
Step 2 'Virtual environment'
if (Test-Path $VenvPy) {
    Write-Host '      Already exists, skipping.'
} else {
    Push-Location $Backend
    python -m venv .venv
    Pop-Location
    if (-not (Test-Path $VenvPy)) { Fail 'venv creation did not produce python.exe' }
    Write-Host '      Created backend\.venv'
}

# --- 3. dependencies -------------------------------------------------------
Step 3 'Installing backend dependencies'
Push-Location $Backend
& $VenvPy -m pip install --quiet --upgrade pip
& $VenvPy -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'pip install failed' }
Pop-Location
Write-Host '      Done.'

# --- 4. .env ---------------------------------------------------------------
Step 4 'Backend .env'
$envPath = Join-Path $Backend '.env'
if (Test-Path $envPath) {
    Write-Host '      Already exists, leaving it alone.'
} else {
    Copy-Item (Join-Path $Backend '.env.example') $envPath

    # A real random secret beats a placeholder nobody remembers to change.
    $bytes = New-Object 'System.Byte[]' 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes) -replace '[+/=]', ''

    (Get-Content $envPath) `
        -replace '^SECRET_KEY=.*', "SECRET_KEY=$secret" |
        Set-Content $envPath

    Write-Host '      Created backend\.env with a generated SECRET_KEY.'
}

# --- 5. CORS patch ---------------------------------------------------------
Step 5 'CORS header check'
$mainPath = Join-Path $Backend 'app\main.py'
$main     = Get-Content $mainPath -Raw
if ($main -match 'X-PGuru-Auth') {
    Write-Host '      allow_headers already includes X-PGuru-Auth.'
} else {
    $main = $main -replace `
        '(allow_headers=\[[^\]]*)"X-Request-ID"\]', `
        '$1"X-Request-ID", "X-PGuru-Auth"]'
    Set-Content $mainPath $main -NoNewline
    Write-Host '      Added X-PGuru-Auth to allow_headers.' -ForegroundColor Green
    Write-Host '      Without it the browser blocks every API call, including login.' -ForegroundColor DarkGray
}

# --- 6. migrations ---------------------------------------------------------
Step 6 'Running migrations'
Push-Location $Backend
& $VenvPy -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Fail 'alembic failed. Is PostgreSQL running, and does backend\.env match your pgguru password?'
}
Pop-Location

# --- 7. seed ---------------------------------------------------------------
Step 7 'Seeding demo data'
Push-Location $Backend
& $VenvPy seed.py
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'seed.py failed' }
Pop-Location

# --- 8. frontend -----------------------------------------------------------
Step 8 'Frontend dependencies'
Push-Location $Frontend
if (-not (Test-Path (Join-Path $Frontend '.env.local'))) {
    Copy-Item '.env.example' '.env.local'
    Write-Host '      Created frontend\.env.local'
}
npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'npm install failed' }
Pop-Location

Write-Host ''
Write-Host '  Setup complete.' -ForegroundColor Green
Write-Host '  Now press Ctrl+Shift+B, or Ctrl+Shift+P then "Tasks: Run Task" -> PGuru: Start All'
Write-Host ''
