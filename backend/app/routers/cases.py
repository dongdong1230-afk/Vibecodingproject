"""历史变更案例 API: 分页查询 / 统计 / 新案例录入(实际替换效果反哺案例库)"""
import json
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.db import BomChangeCase, get_session
from app.schemas import CaseIn
from app.services import cbr_service

router = APIRouter(prefix="/api/cases", tags=["案例推理 CBR"])


def _session():
    with get_session() as s:
        yield s


@router.get("")
def list_cases(keyword: str = "", reason: str = "", effect: str = "",
               page: int = 1, size: int = 20, session=Depends(_session)):
    q = select(BomChangeCase).order_by(BomChangeCase.id.desc())
    if keyword:
        q = q.where(BomChangeCase.old_material_code.like(f"%{keyword}%") |
                    BomChangeCase.new_material_code.like(f"%{keyword}%") |
                    BomChangeCase.case_no.like(f"%{keyword}%"))
    if reason:
        q = q.where(BomChangeCase.change_reason == reason)
    if effect:
        q = q.where(BomChangeCase.effect == effect)
    all_cases = session.execute(q).scalars().all()
    items = all_cases[(page - 1) * size:page * size]
    return {"total": len(all_cases), "items": [c.to_dict() for c in items]}


@router.get("/stats")
def stats(session=Depends(_session)):
    cases = [c.to_dict() for c in session.execute(
        select(BomChangeCase)).scalars().all()]
    return cbr_service.get_case_stats(
        [{k: v for k, v in c.items()} for c in cases])


@router.post("")
def create_case(body: CaseIn, session=Depends(_session)):
    """录入新案例(方案实际应用效果回写, 形成知识闭环)"""
    seq = len(session.execute(select(BomChangeCase)).scalars().all()) + 1
    case = BomChangeCase(
        case_no=f"CB-{seq:04d}",
        product_category=body.product_category,
        work_condition_json=json.dumps(body.work_condition, ensure_ascii=False),
        old_material_code=body.old_material_code,
        new_material_code=body.new_material_code,
        material_category_l3="",
        change_reason=body.change_reason,
        params_old_json="{}", params_new_json="{}",
        effect=body.effect, effect_detail=body.effect_detail,
        failure_rate_after_ppm=body.failure_rate_after_ppm,
        cost_change_pct=body.cost_change_pct,
        lead_time_after_days=body.lead_time_after_days,
        adopted_at="")
    # 从物料库补全类别与参数快照
    from app.db import Material
    old = session.execute(select(Material).where(
        Material.code == body.old_material_code)).scalars().first()
    new = session.execute(select(Material).where(
        Material.code == body.new_material_code)).scalars().first()
    if old:
        case.material_category_l3 = old.category_id
        case.params_old_json = old.attrs_json
    if new:
        case.params_new_json = new.attrs_json
    session.add(case)
    session.commit()
    return case.to_dict()
