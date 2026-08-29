<#
.SYNOPSIS
    Clean shutdown script for the War Impact Platform background processes.
#>

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   STOPPING WAR IMPACT PLATFORM PROCESSES                " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Stop FastAPI Backend (Port 8000)
Write-Host "Stopping FastAPI API Server..." -ForegroundColor White
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*run_api*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# 2. Stop Vite Frontend Server (Port 5173)
Write-Host "Stopping Frontend Server..." -ForegroundColor White
Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*vite*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# 3. Stop Celery Workers & Schedulers
Write-Host "Stopping Celery Workers & Scheduler..." -ForegroundColor White
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*celery*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   ALL PLATFORM SERVICES STOPPED CLEANLY.                " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Start-Sleep -Seconds 1
