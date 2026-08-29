@echo off
title War Impact Platform Launcher
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_platform.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred while launching. Press any key to close.
    pause >nul
)
