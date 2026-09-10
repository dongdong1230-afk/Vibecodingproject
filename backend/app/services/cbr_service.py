"""案例推理 CBR 服务(技术模块 2): 检索历史 BOM 变更案例, 复用已验证替换方案

案例库: data/processed/cases.json(旧物料/替换物料/产品工况/变更原因/变更效果)
相似度计算(加权 kNN):
  sim_cat   类别层级相似度 = 本体类别树归一化 Wu-Palmer(同小类=1.0, 同中类=0.667,
            同大类=0.333, 无公共祖先=0)
  sim_param 参数相似度 = 旧物料属性逐项比较(数值型相对容差 1-min(1,|x-y|/(0.25|y|+ε)),
            类别型相等=1), 取共有属性均值
  sim_cond  工况相似度 = 0.4×产品大类相同 + 0.4×工况字段匹配(温度/电压等级相邻=0.5)
            + 0.2×变更原因相同
  总分      score = w_cat·sim_cat + w_param·sim_param + w_cond·sim_cond
  效果加权  score_eff = score × {success:1.0, partial:0.8, failed:0.5}

检索策略: 同中类(l2)案例预筛 -> score_eff >= 阈值(0.60) 且效果 success/partial 的
案例进入"可复用组"(top-K); 相似且 effect=failed 的案例输出警示; 空池返回 cbr_hit=false。
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.config import CASES_FILE
from app.services.ontology_service import get_ontology

# CBR 参数(与设计文档一致, 可调)
CBR_WEIGHTS = {"cat": 0.30, "param": 0.40, "cond": 0.30}
EFFECT_WEIGHTS = {"success": 1.0, "partial": 0.8, "failed": 0.5}
THRESHOLD = 0.60
TOP_K = 5
_EPS = 1e-6

# 工况字段的等级顺序(相邻等级匹配=0.5)
TEMP_ORDER = ["低温", "普通", "高温"]
VOLT_ORDER = ["DC5V", "DC12V", "DC24V", "AC220V"]


@lru_cache(maxsize=1)
def load_cases() -> list[dict]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]


def _sim_param(params_a: dict, params_b: dict) -> float:
    """属性逐项相似度(共有 key 均值)"""
    common = set(params_a) & set(params_b)
    if not common:
        return 0.0
    total = 0.0
    for k in common:
        a, b = params_a[k], params_b[k]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            total += 1 - min(1.0, abs(a - b) / (0.25 * abs(b) + _EPS))
        else:
            total += 1.0 if a == b else 0.0
    return total / len(common)


def _sim_cond(case: dict, product_category: str, work_condition: dict,
              change_reason: str | None) -> float:
    """工况相似度: 产品大类 + 工况字段 + 变更原因"""
    s1 = 1.0 if case.get("product_category") == product_category else 0.0
    cond = case.get("work_condition") or {}
    work = work_condition or {}
    s2, n = 0.0, 0
    for field in ("temp_grade", "voltage_grade", "env"):
        if field in cond and field in work:
            n += 1
            if cond[field] == work[field]:
                s2 += 1.0
            elif field == "temp_grade":
                s2 += _adjacent(TEMP_ORDER, cond[field], work[field])
            elif field == "voltage_grade":
                s2 += _adjacent(VOLT_ORDER, cond[field], work[field])
    s2 = s2 / n if n else 0.0
    s3 = 1.0 if change_reason and case.get("change_reason") == change_reason else 0.0
    return 0.4 * s1 + 0.4 * s2 + 0.2 * s3


def _adjacent(order: list, a, b) -> float:
    try:
        return 0.5 if abs(order.index(a) - order.index(b)) == 1 else 0.0
    except ValueError:
        return 0.0


def retrieve(query_material: dict, product_category: str,
             work_condition: dict | None = None,
             change_reason: str | None = None,
             cases: list[dict] | None = None,
             top_k: int = TOP_K, threshold: float = THRESHOLD) -> dict:
    """检索与风险物料最相似的历史变更案例

    Args:
        query_material: 风险物料 dict(含 category_id/attrs)
        product_category: 产品大类(如 "工业网关")
        work_condition: 产品工况 {"temp_grade","voltage_grade","env"}
        change_reason: 触发风险类型(EOL/STOCKOUT/LEAD_TIME/COST)
    Returns:
        {cbr_hit, cases: [可复用案例], warnings: [失败案例警示], query:{...}}
    """
    ont = get_ontology()
    pool = cases if cases is not None else load_cases()
    q_cat = query_material.get("category_id", "")
    # 同中类(l2)预筛: 案例旧物料类别与查询物料类别有公共祖先且非根
    pre = [c for c in pool if ont.category_sim(c.get("material_category_l3", ""), q_cat) > 0.33]
    scored = []
    for c in pre:
        sim_cat = ont.category_sim(c.get("material_category_l3", ""), q_cat)
        sim_param = _sim_param(c.get("params_old") or {}, query_material.get("attrs") or {})
        sim_cond = _sim_cond(c, product_category, work_condition, change_reason)
        score = (CBR_WEIGHTS["cat"] * sim_cat + CBR_WEIGHTS["param"] * sim_param
                 + CBR_WEIGHTS["cond"] * sim_cond)
        score_eff = score * EFFECT_WEIGHTS.get(c.get("effect"), 0.5)
        scored.append({"case": c, "sim_score": score, "score_eff": score_eff,
                       "sim_detail": {"sim_cat": round(sim_cat, 4),
                                      "sim_param": round(sim_param, 4),
                                      "sim_cond": round(sim_cond, 4)}})
    scored.sort(key=lambda x: -x["score_eff"])

    reusable, warnings = [], []
    for item in scored:
        c = item["case"]
        # 可复用组: 非失败案例且效果加权分 >= 阈值;
        # 警示组: 失败案例且原始相似度 >= 阈值(效果加权会使失败案例降权, 故用原始分)
        if c["effect"] == "failed":
            if item["sim_score"] < threshold:
                continue
        elif item["score_eff"] < threshold:
            continue
        entry = {
            "case_no": c["case_no"],
            "new_material_code": c["new_material_code"],
            "change_reason": c["change_reason"],
            "effect": c["effect"],
            "effect_detail": c["effect_detail"],
            "sim_score": round(item["sim_score"], 4),
            "score_eff": round(item["score_eff"], 4),
            "sim_detail": item["sim_detail"],
            "product_category": c["product_category"],
            "work_condition": c["work_condition"],
            "cost_change_pct": c["cost_change_pct"],
            "failure_rate_after_ppm": c["failure_rate_after_ppm"],
            "lead_time_after_days": c["lead_time_after_days"],
            "adopted_at": c["adopted_at"],
        }
        if c["effect"] == "failed":
            warnings.append(entry)
        else:
            reusable.append(entry)
    reusable = reusable[:top_k]
    return {
        "cbr_hit": bool(reusable or warnings),
        "cases": reusable,
        "warnings": warnings,
        "query": {"material_code": query_material["code"],
                  "category_id": q_cat,
                  "product_category": product_category,
                  "work_condition": work_condition,
                  "change_reason": change_reason},
    }


def get_case_stats(cases: list[dict] | None = None) -> dict:
    """案例库统计(效果分布/原因分布, 看板用)"""
    pool = cases if cases is not None else load_cases()
    effect, reason = {}, {}
    for c in pool:
        effect[c["effect"]] = effect.get(c["effect"], 0) + 1
        reason[c["change_reason"]] = reason.get(c["change_reason"], 0) + 1
    return {"total": len(pool), "effect": effect, "reason": reason}
