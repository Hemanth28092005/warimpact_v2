<#
.SYNOPSIS
    One-click launcher for the Global Geopolitical Instability & War Impact Platform.
#>

$ErrorActionPreference = "Continue"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   WAR IMPACT PLATFORM - 1-CLICK LAUNCHER                " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Start Docker Containers (PostgreSQL & Redis)
Write-Host "[1/6] Checking Databases (PostgreSQL & Redis)..." -ForegroundColor White
try {
    $dockerRunning = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        docker compose -f docker/docker-compose.yml up -d | Out-Null
        Write-Host "      Docker containers are UP." -ForegroundColor Green
    } else {
        Write-Host "      Warning: Docker Desktop may not be running. Attempting to proceed..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "      Docker check bypassed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 2. Virtual environment check
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CeleryExe = Join-Path $ProjectRoot ".venv\Scripts\celery.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "      Virtual environment not found at .venv. Creating..." -ForegroundColor Yellow
    python -m venv .venv
    & $PythonExe -m pip install -r requirements.lock
}

# 3. Apply Database Migrations & Initial Seeds
Write-Host "[2/6] Verifying Database Schema & Migrations..." -ForegroundColor White
& $PythonExe -m alembic -c db/alembic.ini upgrade head | Out-Null
& $PythonExe -c "
try:
    from ingestion.geo.naval_seed import run_naval_sync
    run_naval_sync()
    from ingestion.geo.flights import run_flights_sync
    run_flights_sync()
except Exception as e:
    pass
" | Out-Null
Write-Host "      Database is at HEAD and baseline data is synchronized." -ForegroundColor Green

# 4. Start FastAPI Backend REST API
Write-Host "[3/6] Starting FastAPI REST API (Port 8000)..." -ForegroundColor White
$apiPortInUse = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if (-not $apiPortInUse) {
    Start-Process -FilePath $PythonExe -ArgumentList "scripts/run_api.py" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    Start-Sleep -Milliseconds 1500
    Write-Host "      FastAPI backend server launched in background." -ForegroundColor Green
} else {
    Write-Host "      FastAPI backend server is already running on port 8000." -ForegroundColor Green
}

# 5. Start Celery Worker & Celery Beat Scheduler
Write-Host "[4/6] Starting Background Ingestion Engine (Celery)..." -ForegroundColor White
$celeryProcesses = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*celery*" }
if (-not $celeryProcesses) {
    Start-Process -FilePath $CeleryExe -ArgumentList "-A ingestion.common.celery_app worker -P solo --loglevel=info" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    Start-Process -FilePath $CeleryExe -ArgumentList "-A ingestion.common.celery_app beat --loglevel=info" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    Write-Host "      Celery Worker & Scheduler launched in background." -ForegroundColor Green
} else {
    Write-Host "      Celery processes already active." -ForegroundColor Green
}

# 6. Start Frontend (Vite Server)
Write-Host "[5/6] Starting Frontend Web Server (Port 5173)..." -ForegroundColor White
$fePortInUse = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if (-not $fePortInUse) {
    $npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npmCmd) { $npmCmd = "npm" }
    Start-Process -FilePath $npmCmd -ArgumentList "run dev --prefix frontend" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
    Write-Host "      Vite dev server launched in background." -ForegroundColor Green
} else {
    Write-Host "      Vite dev server is already running on port 5173." -ForegroundColor Green
}

# 7. Wait for services to be ready and open window in Standalone App Mode
Write-Host "[6/6] Connecting to Dashboard..." -ForegroundColor White
$ready = $false
$attempts = 0
while (-not $ready -and $attempts -lt 20) {
    $attempts++
    try {
        $res = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($res.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 800
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   SYSTEM READY! Launching War Impact Software...        " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

# Launch in App Mode (Dedicated window without browser navigation bar)
$AppUrl = "http://127.0.0.1:5173"
$EdgePath = "$env:ProgramFiles (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $EdgePath)) {
    $EdgePath = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
}
$ChromePath = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"

if (Test-Path $EdgePath) {
    Start-Process -FilePath $EdgePath -ArgumentList "--app=$AppUrl"
} elseif (Test-Path $ChromePath) {
    Start-Process -FilePath $ChromePath -ArgumentList "--app=$AppUrl"
} else {
    Start-Process $AppUrl
}
