"""FastAPI 应用：B/S 架构的后端服务层。

提供 REST API：预测、历史记录、单元信息、健康检查，并托管前端静态页面。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import database

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

app = FastAPI(title="设备故障 PHM 预测系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.on_event("startup")
def _startup():
    database.init_db()


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "phm-predictor"}


@app.post("/api/predict")
async def predict(
    file: UploadFile = File(...),
    unit_id: str | None = Form(None),
):
    """上传传感器数据文件，返回 RUL 预测与健康评估结果。"""
    raw = await file.read()
    if not raw:
        return JSONResponse(status_code=400, content={"detail": "上传文件为空"})
    try:
        from backend.services.predictor import predict_from_upload

        result = predict_from_upload(raw, unit_id=unit_id)
        return result
    except FileNotFoundError as e:
        return JSONResponse(
            status_code=503,
            content={"detail": f"模型未就绪：{e}。请先运行 scripts/train.py 训练模型。"},
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"detail": f"预测失败：{e}"})


@app.get("/api/history")
def history(limit: int = 50):
    return database.list_predictions(limit=limit)


@app.get("/api/units")
def units(limit: int = 20):
    return database.list_units(limit=limit)
