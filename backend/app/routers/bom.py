"""BOM 模块 API: 导入/产品/结构树/手工加行/版本/回滚"""
import json
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.db import BomLine, BomProduct, BomVersion, get_materials_by_code, get_session
from app.schemas import BomLineIn, ProductCreate
from app.services import bom_service

router = APIRouter(prefix="/api/bom", tags=["BOM 管理"])


def _session():
    with get_session() as s:
        yield s


def _lines_view(session, product_id: int):
    mats = get_materials_by_code(session)
    lines = session.execute(
        select(BomLine).where(BomLine.product_id == product_id)
        .order_by(BomLine.line_no)).scalars().all()
    return [ln.to_dict(mats.get(ln.material_code)) for ln in lines]


@router.post("/import")
async def import_bom(file: UploadFile = File(...),
                     product_code: str = Form(""),
                     product_name: str = Form(""),
                     category: str = Form(""),
                     condition: str = Form("{}"),
                     session=Depends(_session)):
    """导入 BOM 文件(Excel/CSV/JSON), 自动建档未知物料, 生成初始版本快照"""
    content = await file.read()
    try:
        cond = json.loads(condition or "{}")
    except json.JSONDecodeError:
        cond = {}
    code = product_code or Path(file.filename).stem
    try:
        rows, warnings = bom_service.parse_import(file.filename, content, code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rows:
        raise HTTPException(status_code=400, detail="导入文件无有效 BOM 行")
    created = bom_service.auto_create_materials(session, [r["material_code"] for r in rows])
    result = bom_service.create_product_from_rows(session, {
        "code": code, "name": product_name or code, "category": category,
        "condition": cond, "source": "import"}, rows)
    return {"product_id": result["product_id"], "line_count": result["line_count"],
            "warnings": warnings, "auto_created_materials": created}


@router.get("/products")
def list_products(keyword: str = "", page: int = 1, size: int = 20,
                  session=Depends(_session)):
    q = select(BomProduct).order_by(BomProduct.id.desc())
    if keyword:
        q = q.where(BomProduct.code.like(f"%{keyword}%") |
                    BomProduct.name.like(f"%{keyword}%"))
    all_prods = session.execute(q).scalars().all()
    total = len(all_prods)
    prods = all_prods[(page - 1) * size:page * size]
    out = []
    for p in prods:
        d = p.to_dict()
        d["line_count"] = session.execute(
            select(BomLine).where(BomLine.product_id == p.id)).scalars().all().__len__()
        out.append(d)
    return {"total": total, "items": out}


@router.post("/products")
def create_product(body: ProductCreate, session=Depends(_session)):
    if session.execute(select(BomProduct).where(
            BomProduct.code == body.code)).scalars().first():
        raise HTTPException(status_code=400, detail=f"产品编码 {body.code} 已存在")
    prod = BomProduct(code=body.code, name=body.name, category=body.category,
                      description=body.description,
                      condition_json=json.dumps(body.condition, ensure_ascii=False),
                      source="manual")
    session.add(prod)
    session.flush()
    bom_service._save_version(session, prod, change_summary="创建产品(空 BOM)",
                              changed_lines=[], snapshot_rows=[])
    session.commit()
    return prod.to_dict()


@router.get("/products/{product_id}")
def get_product(product_id: int, session=Depends(_session)):
    prod = session.get(BomProduct, product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="产品不存在")
    return {"product": prod.to_dict(), "lines": _lines_view(session, product_id)}


@router.get("/products/{product_id}/tree")
def get_tree(product_id: int, session=Depends(_session)):
    try:
        return bom_service.get_tree(session, product_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/products/{product_id}/lines")
def add_line(product_id: int, body: BomLineIn, session=Depends(_session)):
    prod = session.get(BomProduct, product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="产品不存在")
    bom_service.auto_create_materials(session, [body.material_code])
    max_no = session.execute(select(BomLine.line_no).where(
        BomLine.product_id == product_id).order_by(BomLine.line_no.desc())
        .limit(1)).scalars().first() or 0
    parent = body.parent_code or prod.code
    ln = BomLine(product_id=product_id, line_no=max_no + 1,
                 parent_code=parent, material_code=body.material_code,
                 qty_per=body.qty_per, unit=body.unit, level=body.level,
                 path=f"/{prod.code}/{body.material_code}", remark=body.remark,
                 source="manual")
    session.add(ln)
    session.commit()
    return ln.to_dict()


@router.delete("/products/{product_id}")
def delete_product(product_id: int, session=Depends(_session)):
    prod = session.get(BomProduct, product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="产品不存在")
    session.execute(delete(BomLine).where(BomLine.product_id == product_id))
    session.execute(delete(BomVersion).where(BomVersion.product_id == product_id))
    session.delete(prod)
    session.commit()
    return {"deleted": product_id}


@router.get("/products/{product_id}/versions")
def list_versions(product_id: int, session=Depends(_session)):
    vers = session.execute(
        select(BomVersion).where(BomVersion.product_id == product_id)
        .order_by(BomVersion.id.desc())).scalars().all()
    return {"items": [v.to_dict() for v in vers]}


@router.get("/versions/{version_id}")
def version_detail(version_id: int, session=Depends(_session)):
    try:
        return bom_service.get_version_diff(session, version_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/versions/{version_id}/rollback")
def rollback(version_id: int, session=Depends(_session)):
    ver = session.get(BomVersion, version_id)
    if not ver:
        raise HTTPException(status_code=404, detail="版本不存在")
    try:
        return bom_service.rollback_to(session, ver.product_id, version_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
