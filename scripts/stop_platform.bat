@echo off
title Stop War Impact Platform
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_platform.ps1"
