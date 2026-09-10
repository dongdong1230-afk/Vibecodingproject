"""数据看板 API: 风险/方案/案例/成本统计(ECharts 数据源)"""
import json
import sys
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.config import RAW_DIR
from app.db import (BomChangeCase, BomProduct, Material, RiskRecord,
                    SubstitutionPlan, get_session)
from app.services import cbr_service

router = APIRouter(prefix="/api/dashboard", tags=["数据看板"])


def _session():
    with get_session() as s:
        yield s


@router.get("/overview")
def overview(session=Depends(_session)):
    risks = session.execute(select(RiskRecord)).scalars().all()
    plans = session.execute(select(SubstitutionPlan)).scalars().all()
    cases = [c.to_dict() for c in session.execute(
        select(BomChangeCase)).scalars().all()]
    mats = {m.code: m for m in session.execute(select(Material)).scalars()}

    risk_types = Counter(r.risk_type for r in risks)
    risk_levels = Counter(r.risk_level for r in risks)
    risk_status = Counter(r.status for r in risks)
    applied = [p for p in plans if p.status == "applied"]

    # 替换前后成本对比(已应用方案)
    cost_saved = 0.0
    for p in applied:
        if p.old_material_code in mats and p.new_material_code in mats:
            cost_saved += (mats[p.old_material_code].unit_price
                           - mats[p.new_material_code].unit_price)

    # FCE 得分分布(10 分箱)
    bins = {f"{i*10}-{i*10+10}": 0 for i in range(10)}
    for p in plans:
        idx = min(int(p.fce_score // 10), 9)
        bins[f"{idx*10}-{idx*10+10}"] += 1

    # 本体命中规则 Top5(方案保存的推理路径)
    rule_counter = Counter()
    for p in plans:
        for r in json.loads(p.ontology_rules_json or "[]"):
            if isinstance(r, str):
                rule_counter[r] += 1
    top_rules = [{"rule": k, "count": v} for k, v in rule_counter.most_common(5)]

    stats = cbr_service.get_case_stats(cases)
    products = session.execute(select(BomProduct)).scalars().all()
    return {
        "cards": {
            "product_count": len(products),
            "risk_count": len(risks),
            "open_risk_count": risk_status.get("open", 0),
            "plan_count": len(plans),
            "applied_plan_count": len(applied),
            "case_total": stats["total"],
            "case_success_rate": round(stats["effect"].get("success", 0)
                                       / stats["total"] * 100, 1)
                                       if stats["total"] else 0,
            "cost_saved": round(cost_saved, 2),
        },
        "charts": {
            "risk_types": [{"name": k, "value": v} for k, v in risk_types.items()],
            "risk_levels": [{"name": k, "value": v} for k, v in risk_levels.items()],
            "risk_status": [{"name": k, "value": v} for k, v in risk_status.items()],
            "case_effect": [{"name": k, "value": v} for k, v in stats["effect"].items()],
            "case_reason": [{"name": k, "value": v} for k, v in stats["reason"].items()],
            "fce_bins": [{"name": k, "value": v} for k, v in bins.items()],
            "top_rules": top_rules,
        },
        "recent_plans": [p.to_dict() for p in plans[:8]],
    }


@router.get("/template")
def bom_template():
    """BOM 导入模板下载"""
    f = RAW_DIR / "bom_template.xlsx"
    if not f.exists():
        return {"error": "模板不存在"}
    return FileResponse(f, filename="bom_template.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument"
                                   ".spreadsheetml.sheet")
