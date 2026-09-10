@echo off
REM Start backend and open browser automatically
cd /d "%~dp0backend"
start "" http://localhost:8000
py -3.13 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
