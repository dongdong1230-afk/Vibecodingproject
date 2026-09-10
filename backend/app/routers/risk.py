"""风险识别 API: 扫描 BOM 风险物料 / 历史风险记录 / 规则查看"""
import json
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.db import BomLine, BomProduct, RiskRecord, get_materials_by_code, get_session
from app.services import risk_service

router = APIRouter(prefix="/api/risk", tags=["风险识别"])


def _session():
    with get_session() as s:
        yield s


@router.post("/scan/{product_id}")
def scan(product_id: int, session=Depends(_session)):
    """扫描产品全部 BOM 行的风险物料, 结果写入 risk_records(可解释明细)"""
    prod = session.get(BomProduct, product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="产品不存在")
    lines = session.execute(
        select(BomLine).where(BomLine.product_id == product_id)).scalars().all()
    mats = get_materials_by_code(session)
    cond = json.loads(prod.condition_json or "{}")
    results = risk_service.scan_bom(
        {code: m.to_dict() for code, m in mats.items()},
        [ln.to_dict() for ln in lines], cond)
    # 落库(每物料每风险一条记录)
    now = datetime.now().replace(microsecond=0)
    for item in results:
        for hit in item["risks"]:
            session.add(RiskRecord(
                product_id=product_id,
                bom_line_id=lines[0].id if lines else 0,
                material_code=item["material_code"],
                risk_type=hit["risk_type"], risk_level=hit["level"],
                detail_json=json.dumps(hit, ensure_ascii=False),
                status="open", detected_at=now))
    session.commit()
    return {"product_id": product_id, "product_name": prod.name,
            "risk_count": len(results), "items": results}


@router.get("/records")
def records(product_id: int = 0, status: str = "", page: int = 1, size: int = 50,
            session=Depends(_session)):
    q = select(RiskRecord).order_by(RiskRecord.id.desc())
    if product_id:
        q = q.where(RiskRecord.product_id == product_id)
    if status:
        q = q.where(RiskRecord.status == status)
    all_recs = session.execute(q).scalars().all()
    items = all_recs[(page - 1) * size:page * size]
    return {"total": len(all_recs),
            "items": [r.to_dict() for r in items]}


@router.get("/rules")
def rules():
    return risk_service.get_rules_view()
