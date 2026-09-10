"""替代方案业务编排服务: 三算法模块协同的业务闭环枢纽

风险物料 → 本体推理(合规候选集) ∪ CBR(历史验证物料) → FCE(五指标排序)
        → 方案保存 → 应用(版本快照/行更新/风险关闭) → 历史回溯
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.db import (BomLine, BomProduct, Material, PlanScore, RiskRecord,
                    SubstitutionPlan, get_materials_by_code, get_session)
from app.services import bom_service, cbr_service, fce_service
from app.services.ontology_service import get_ontology


def _now():
    return datetime.now().replace(microsecond=0)


def _get_material_dict(session, code: str) -> dict | None:
    m = session.execute(select(Material).where(
        Material.code == code)).scalars().first()
    return m.to_dict() if m else None


def infer_substitutes(session, product_id: int, material_code: str,
                      risk_type: str = "") -> dict:
    """本体推理 + CBR 检索: 输出合规候选集与历史案例证据"""
    prod = session.get(BomProduct, product_id)
    if not prod:
        raise ValueError(f"产品 {product_id} 不存在")
    mat = _get_material_dict(session, material_code)
    if not mat:
        raise ValueError(f"物料 {material_code} 不存在")
    cond = json.loads(prod.condition_json or "{}")
    ont = get_ontology()

    ontology_result = ont.infer(mat, cond)
    cbr_result = cbr_service.retrieve(mat, prod.category, cond, risk_type)

    # 合并候选: 本体候选 + CBR 复用物料(去重, 仅保留物料库中存在且 active 的)
    # CBR 推荐的替换物料须通过本体硬约束过滤(三模块协同: CBR 给证据, 本体给硬约束)
    merged_codes, sources = {}, {}
    for cand in ontology_result["candidates"]:
        merged_codes[cand["code"]] = cand
        sources[cand["code"]] = "ontology"
    cbr_rejected = []
    for case in cbr_result["cases"]:
        code = case["new_material_code"]
        m = _get_material_dict(session, code)
        if not m or m["lifecycle_status"] != "active":
            continue
        if code in merged_codes:
            sources[code] = "both"
            continue
        passed, failed = ont.check_coverage(mat, m)
        fp = ont.forbidden_hit(mat["category_id"], m["category_id"])
        _, denies, _ = ont.eval_rules(mat, m, cond)
        if failed or fp or denies:
            cbr_rejected.append({"case_no": case["case_no"], "new_material_code": code,
                                 "reason": "本体硬约束过滤"})
            continue
        merged_codes[code] = m
        sources[code] = "cbr"
    merged = [dict(merged_codes[c], source=sources[c]) for c in merged_codes]
    return {
        "product_id": product_id, "product_name": prod.name,
        "material": mat, "condition": cond, "risk_type": risk_type,
        "ontology": {"candidate_count": ontology_result["candidate_count"],
                     "candidates": ontology_result["candidates"],
                     "reason": ontology_result.get("reason", "")},
        "cbr": {"cbr_hit": cbr_result["cbr_hit"],
                "cases": cbr_result["cases"],
                "warnings": cbr_result["warnings"],
                "rejected": cbr_rejected},
        "merged_candidates": merged,
    }


def _fce_item(mat: dict, orig: dict, ont) -> dict:
    """把物料转成 FCE 输入项(五指标原始值)"""
    soft = ont.soft_scores(orig, mat)
    return {"code": mat["code"], "name": mat["name"],
            "raw": {"cost": mat["unit_price"], "lead_time": mat["lead_time_days"],
                    "failure_rate": mat["failure_rate_ppm"],
                    "perf_match": soft["perf_match"],
                    "process_compat": soft["process_compat"]},
            "soft_scores": soft}


def evaluate_plans(session, product_id: int, bom_line_id: int,
                   candidate_codes: list[str]) -> dict:
    """FCE 模糊综合评价: 候选方案(含原物料基准)五指标打分排序 + 原/新对比"""
    line = session.get(BomLine, bom_line_id)
    if not line or line.product_id != product_id:
        raise ValueError(f"BOM 行 {bom_line_id} 不存在或不属于产品 {product_id}")
    orig = _get_material_dict(session, line.material_code)
    if not orig:
        raise ValueError(f"原物料 {line.material_code} 不存在")
    ont = get_ontology()
    # 原物料作为对比基准: 停产/即将停产物料不可再采购, 不参与排序;
    # 缺货/交期类风险的原物料仍可继续采购, 参与排序(替换未必优于等待)
    include_orig = orig["lifecycle_status"] not in ("EOL", "phaseout")
    items = [_fce_item(orig, orig, ont)] if include_orig else []
    for code in candidate_codes:
        m = _get_material_dict(session, code)
        if not m:
            continue
        items.append(_fce_item(m, orig, ont))
    result = fce_service.evaluate(items)
    # 原/新对比(成本/交期/故障率变化)
    orig_cost, orig_lt, orig_fr = orig["unit_price"], orig["lead_time_days"], \
        orig["failure_rate_ppm"]
    for r in result["ranked"]:
        is_orig = r["code"] == orig["code"]
        if is_orig:
            r["is_original"] = True
            r["compare_original"] = {"cost_delta": 0.0, "cost_pct": 0.0,
                                     "lead_time_delta": 0, "failure_rate_delta": 0.0}
            continue
        m = _get_material_dict(session, r["code"])
        r["is_original"] = False
        r["compare_original"] = {
            "cost_delta": round(m["unit_price"] - orig_cost, 4),
            "cost_pct": round((m["unit_price"] - orig_cost) / orig_cost * 100, 1)
                        if orig_cost else 0.0,
            "lead_time_delta": m["lead_time_days"] - orig_lt,
            "failure_rate_delta": round(m["failure_rate_ppm"] - orig_fr, 1),
        }
    return {"product_id": product_id, "bom_line_id": bom_line_id,
            "original": orig, "mode": result["mode"], "ahp_cr": result["ahp_cr"],
            "weights": result["weights"], "ranked": result["ranked"]}


def _next_plan_no(session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    seq = len(session.execute(select(SubstitutionPlan).where(
        SubstitutionPlan.plan_no.like(f"PL-{today}-%"))).scalars().all()) + 1
    return f"PL-{today}-{seq:03d}"


def save_plan(session, body) -> dict:
    """保存替代方案(含 FCE 评分明细)"""
    prod = session.get(BomProduct, body.product_id)
    line = session.get(BomLine, body.bom_line_id)
    if not prod or not line or line.product_id != body.product_id:
        raise ValueError("产品或 BOM 行不存在")
    plan = SubstitutionPlan(
        plan_no=_next_plan_no(session), product_id=body.product_id,
        bom_line_id=body.bom_line_id,
        old_material_code=line.material_code,
        new_material_code=body.new_material_code,
        trigger_type=body.trigger_type,
        candidate_source=body.candidate_source,
        ontology_rules_json=json.dumps(body.ontology_rules or [], ensure_ascii=False),
        cbr_case_id=body.cbr_case_id,
        fce_score=body.fce_score, fce_grade=body.fce_grade, status="saved")
    session.add(plan)
    session.flush()
    ev = body.evaluation or {}
    for ind in ev.get("indicators", []):
        session.add(PlanScore(
            plan_id=plan.id, indicator=ind["key"], raw_value=ind["raw"],
            norm_value=ind["norm"],
            membership_json=json.dumps(ind["membership"], ensure_ascii=False),
            weight=ind["weight"], weighted_score=sum(ind["weighted"])))
    session.commit()
    return plan.to_dict()


def list_plans(session, product_id: int = 0, status: str = "") -> dict:
    q = select(SubstitutionPlan).order_by(SubstitutionPlan.id.desc())
    if product_id:
        q = q.where(SubstitutionPlan.product_id == product_id)
    if status:
        q = q.where(SubstitutionPlan.status == status)
    plans = session.execute(q).scalars().all()
    mats = get_materials_by_code(session)
    prods = {p.id: p for p in session.execute(select(BomProduct)).scalars()}
    items = []
    for p in plans:
        d = p.to_dict()
        d["old_material_name"] = mats[p.old_material_code].name \
            if p.old_material_code in mats else p.old_material_code
        d["new_material_name"] = mats[p.new_material_code].name \
            if p.new_material_code in mats else p.new_material_code
        d["product_code"] = prods[p.product_id].code if p.product_id in prods else ""
        items.append(d)
    return {"total": len(items), "items": items}


def plan_detail(session, plan_id: int) -> dict:
    plan = session.get(SubstitutionPlan, plan_id)
    if not plan:
        raise ValueError(f"方案 {plan_id} 不存在")
    scores = session.execute(select(PlanScore).where(
        PlanScore.plan_id == plan_id).order_by(PlanScore.id)).scalars().all()
    mats = get_materials_by_code(session)
    return {"plan": plan.to_dict(),
            "scores": [s.to_dict() for s in scores],
            "old_material": mats[plan.old_material_code].to_dict()
                            if plan.old_material_code in mats else None,
            "new_material": mats[plan.new_material_code].to_dict()
                            if plan.new_material_code in mats else None}


def apply_plan(session, plan_id: int) -> dict:
    """应用方案: 版本快照 → BOM 行更新 → 风险关闭 → 方案置 applied"""
    plan = session.get(SubstitutionPlan, plan_id)
    if not plan:
        raise ValueError(f"方案 {plan_id} 不存在")
    if plan.status == "applied":
        raise ValueError("方案已应用, 不可重复应用")
    prod = session.get(BomProduct, plan.product_id)
    line = session.get(BomLine, plan.bom_line_id)
    if not line:
        raise ValueError("方案对应的 BOM 行已不存在")
    old_code = line.material_code
    # 1) 更新 BOM 行(新状态)
    line.material_code = plan.new_material_code
    # 2) 快照新状态为下一版本(版本链: v1=原始BOM -> v2=替换后BOM)
    prod.version_no += 1
    bom_service.snapshot_current(
        session, prod,
        change_summary=f"应用替代方案 {plan.plan_no}: {old_code} → {plan.new_material_code}",
        changed_lines=[{"type": "substitute", "line_no": line.line_no,
                        "old_code": old_code, "new_code": plan.new_material_code,
                        "plan_no": plan.plan_no}])
    # 3) 关闭该产品该旧物料的 open 风险
    closed = 0
    for rec in session.execute(select(RiskRecord).where(
            RiskRecord.product_id == plan.product_id,
            RiskRecord.material_code == old_code,
            RiskRecord.status == "open")).scalars():
        rec.status = "resolved"
        rec.resolved_at = _now()
        closed += 1
    plan.status = "applied"
    session.commit()
    return {"plan_id": plan_id, "plan_no": plan.plan_no,
            "product_id": prod.id, "version_no": prod.version_no,
            "bom_line_id": line.id, "old_material_code": old_code,
            "new_material_code": plan.new_material_code,
            "risk_closed": closed}
