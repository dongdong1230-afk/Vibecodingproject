@echo off
REM BOM Substitution AI System - one-click start
cd /d "%~dp0backend"

REM If the system is already running, just open the browser
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo System is already running at http://localhost:8000
    start "" http://localhost:8000
    goto :end
)

echo ============================================
echo  BOM Intelligent Substitution System
echo  Web UI:   http://localhost:8000
echo  API Docs: http://localhost:8000/docs
echo ============================================
py -3.13 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
:end
pause
