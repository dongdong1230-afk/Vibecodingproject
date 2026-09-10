"""替代推理与方案 API: 三算法编排(本体推理+CBR+FCE)/方案保存/应用"""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.db import get_session
from app.schemas import EvaluateRequest, InferRequest, PlanCreate
from app.services import substitution_service

router = APIRouter(prefix="/api/substitution", tags=["替代推理与方案"])


def _session():
    with get_session() as s:
        yield s


@router.post("/infer")
def infer(body: InferRequest, session=Depends(_session)):
    """风险物料 → 本体合规候选 + CBR 历史案例(业务闭环第 3 步)"""
    try:
        return substitution_service.infer_substitutes(
            session, body.product_id, body.material_code, body.risk_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/evaluate")
def evaluate(body: EvaluateRequest, session=Depends(_session)):
    """候选方案 FCE 五指标模糊综合评价与排序(业务闭环第 4 步)"""
    try:
        return substitution_service.evaluate_plans(
            session, body.product_id, body.bom_line_id, body.candidate_codes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/plans")
def save_plan(body: PlanCreate, session=Depends(_session)):
    try:
        return substitution_service.save_plan(session, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/plans")
def plans(product_id: int = 0, status: str = "", session=Depends(_session)):
    return substitution_service.list_plans(session, product_id, status)


@router.get("/plans/{plan_id}")
def plan_detail(plan_id: int, session=Depends(_session)):
    try:
        return substitution_service.plan_detail(session, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/plans/{plan_id}/apply")
def apply_plan(plan_id: int, session=Depends(_session)):
    """应用方案: 生成新 BOM 版本 + 更新 BOM 行 + 关闭风险(业务闭环第 5 步)"""
    try:
        return substitution_service.apply_plan(session, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
