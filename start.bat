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

REM ---------- 4. 启动服务并自动打开浏览器 ----------
echo [4/4] 启动服务...
start "PHM预测系统服务" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000"
ping -n 6 127.0.0.1 >nul
start "" http://127.0.0.1:8000

echo.
echo 服务已启动，浏览器已自动打开。
echo 提示：黑色服务窗口请保留，关闭它即停止服务。
ping -n 3 127.0.0.1 >nul
exit /b 0
