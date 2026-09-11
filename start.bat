@echo off
chcp 65001 >nul
echo ============================================
echo  设备故障 PHM 预测系统 - 一键启动
echo ============================================

cd /d "%~dp0"

REM 1. 创建虚拟环境（首次运行）
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境...
    where python >nul 2>nul
    if errorlevel 1 (
        echo 未检测到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH
        pause
        exit /b 1
    )
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)

REM 2. 数据预处理（无训练样本时）
if not exist "data\processed\test_windows.npz" (
    echo [2/3] 数据预处理...
    .venv\Scripts\python scripts\preprocess.py
)

REM 3. 训练模型（无模型时）
if not exist "backend\models\lstm_fd001.pt" (
    echo [3/3] 训练 LSTM 与随机森林模型...
    .venv\Scripts\python scripts\train.py
)

echo.
echo 启动服务: http://127.0.0.1:8000
echo 按 Ctrl+C 停止服务
.venv\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
pause
