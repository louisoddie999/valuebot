@echo off
REM ValueBot — one-click local server + tunnel
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0scripts\run_local.ps1"
pause