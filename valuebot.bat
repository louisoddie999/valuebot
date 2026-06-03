@echo off
title ValueBot
set SCOPE=%1
if "%SCOPE%"=="" set SCOPE=ahead
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0scripts\valuebot.ps1" -Scope "%SCOPE%"
pause