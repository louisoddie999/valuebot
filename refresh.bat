@echo off
cd /d "%~dp0"
set /p SCOPE=Scope to refresh [today/tomorrow/week/weekend or YYYY-MM-DD] (default weekend): 
if "%SCOPE%"=="" set SCOPE=weekend
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0scripts\refresh.ps1" -Scope "%SCOPE%"
pause