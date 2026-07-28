@echo off
REM Start backend API + dashboard for local use.
cd /d "%~dp0.."
start "ValueBot API" cmd /k python -m uvicorn api.main:app --port 8000
start "ValueBot Web" cmd /k "cd dashboard && npm run dev"
echo API -> http://localhost:8000   Dashboard -> http://localhost:3000
