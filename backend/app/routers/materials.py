"""物料主数据 API: 分页查询 / 详情 / 手工录入"""
import json
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.db import Material, get_session
from app.schemas import MaterialIn

router = APIRouter(prefix="/api/materials", tags=["物料主数据"])


def _session():
    with get_session() as s:
        yield s


@router.get("")
def list_materials(keyword: str = "", category_id: str = "", status: str = "",
                   page: int = 1, size: int = 20, session=Depends(_session)):
    q = select(Material).order_by(Material.code)
    if keyword:
        q = q.where(Material.code.like(f"%{keyword}%") |
                    Material.name.like(f"%{keyword}%"))
    if category_id:
        q = q.where(Material.category_id == category_id)
    if status:
        q = q.where(Material.lifecycle_status == status)
    all_mats = session.execute(q).scalars().all()
    items = all_mats[(page - 1) * size:page * size]
    return {"total": len(all_mats), "items": [m.to_dict() for m in items]}


@router.get("/{code}")
def material_detail(code: str, session=Depends(_session)):
    m = session.execute(select(Material).where(
        Material.code == code)).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="物料不存在")
    return m.to_dict()


@router.post("")
def create_material(body: MaterialIn, session=Depends(_session)):
    if session.execute(select(Material).where(
            Material.code == body.code)).scalars().first():
        raise HTTPException(status_code=400, detail=f"物料编码 {body.code} 已存在")
    m = Material(code=body.code, name=body.name, category_id=body.category_id,
                 category_l1="", category_l2="", category_l3="",
                 attrs_json=json.dumps(body.attrs, ensure_ascii=False),
                 unit_price=body.unit_price, lead_time_days=body.lead_time_days,
                 moq=body.moq, supplier=body.supplier,
                 lifecycle_status=body.lifecycle_status,
                 stock_qty=body.stock_qty, safety_stock=body.safety_stock,
                 failure_rate_ppm=body.failure_rate_ppm)
    if body.category_id:
        from app.services.ontology_service import get_ontology
        cat = get_ontology().categories.get(body.category_id)
        if cat:
            m.category_l3 = cat["name"]
            parent = get_ontology().categories.get(cat["parent_id"])
            if parent:
                m.category_l2 = parent["name"]
                grand = get_ontology().categories.get(parent["parent_id"])
                m.category_l1 = grand["name"] if grand else parent["name"]
    session.add(m)
    session.commit()
    return m.to_dict()
