@echo off
title 设备故障 PHM 预测系统 - 一键启动
cd /d "%~dp0"

echo ============================================
echo   设备故障 PHM 预测系统 - 一键启动
echo ============================================
echo.

REM ---------- 0. 服务已在运行则直接打开浏览器 ----------
curl -s http://127.0.0.1:8000/health 2>nul | findstr "ok" >nul 2>&1
if not errorlevel 1 (
    echo 检测到服务已在运行，正在为你打开浏览器...
    start "" http://127.0.0.1:8000
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

REM ---------- 0.5 端口已被占用（服务正在启动中）则等待就绪后打开浏览器，不重复启动 ----------
netstat -ano 2>nul | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 goto port_busy

REM ---------- 1. 虚拟环境与依赖（首次运行自动搭建） ----------
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 首次运行：创建虚拟环境并安装依赖，请稍候...
    if exist "C:\Users\LENOVO\anaconda3\python.exe" (
        "C:\Users\LENOVO\anaconda3\python.exe" -m venv .venv
    ) else (
        python -m venv .venv
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

REM ---------- 2. 数据预处理（无产物时执行） ----------
if not exist "data\processed\test_windows.npz" (
    echo [2/4] 数据预处理...
    ".venv\Scripts\python.exe" scripts\preprocess.py
)

REM ---------- 3. 训练模型（无模型时执行，约 5 分钟） ----------
if not exist "backend\models\lstm_fd001.pt" (
    echo [3/4] 训练 LSTM 与随机森林模型（首次运行约 5 分钟）...
    ".venv\Scripts\python.exe" scripts\train.py
)

REM ---------- 4. 启动前再次兜底检测（防止极端情况重复启动） ----------
netstat -ano 2>nul | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 goto port_busy

REM ---------- 5. 启动服务并自动打开浏览器 ----------
echo [4/4] 启动服务...
start "PHM预测系统服务" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000"
ping -n 6 127.0.0.1 >nul
start "" http://127.0.0.1:8000

echo.
echo 服务已启动，浏览器已自动打开。
echo 提示：黑色服务窗口请保留，关闭它即停止服务。
ping -n 3 127.0.0.1 >nul
exit /b 0

REM ---------- 端口被占用：等待服务就绪后打开浏览器 ----------
:port_busy
echo 检测到 8000 端口已被占用（服务正在运行或启动中）...
echo 正在等待服务就绪并打开浏览器，请稍候...
set /a wait_count=0
:wait_loop
curl -s http://127.0.0.1:8000/health 2>nul | findstr "ok" >nul 2>&1
if not errorlevel 1 goto service_ready
set /a wait_count+=1
if %wait_count% geq 12 (
    echo.
    echo 服务未能在 24 秒内就绪，请关闭旧的黑色服务窗口后重新双击本脚本。
    ping -n 5 127.0.0.1 >nul
    exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto wait_loop
:service_ready
echo 服务已就绪，正在打开浏览器...
start "" http://127.0.0.1:8000
ping -n 3 127.0.0.1 >nul
exit /b 0