"""FastAPI 主应用: 面向离散制造业产品BOM智能解析与物料替代方案推理B/S系统

启动: cd backend && py -3.13 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
文档: http://localhost:8000/docs
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from app.db import init_db
from app.routers import bom, cases, dashboard, materials, ontology, risk, substitution

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="面向离散制造业产品BOM智能解析与物料替代方案推理系统",
    description="业务闭环: BOM录入解析 → 风险物料识别 → 替代物料推理(本体推理+CBR) "
                "→ 模糊综合评价 → 方案保存与历史回溯",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- API 路由 ----------
app.include_router(bom.router)
app.include_router(risk.router)
app.include_router(ontology.router)
app.include_router(materials.router)
app.include_router(substitution.router)
app.include_router(cases.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bom-substitution-ai", "version": "1.0.0"}


@app.get("/api/meta")
def meta():
    """前端下拉框等静态元信息"""
    from app.services.ontology_service import get_ontology
    from app.services.risk_service import get_rules_view
    ont = get_ontology()
    return {
        "categories": sorted(ont.categories.values(),
                             key=lambda c: (c["level"], c["id"])),
        "risk": get_rules_view(),
    }


# ---------- 前端静态页面 ----------
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"),
              name="assets")
    app.mount("/libs", StaticFiles(directory=FRONTEND_DIR / "libs"), name="libs")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")
