"""生成仿真历史 BOM 变更案例库 data/processed/cases.json

案例用于 CBR 案例推理: 旧物料、替换物料、产品工况、变更原因、变更后实际效果。
新物料保证是旧物料的"合规替代"(用与本体内 property_schema 同源的覆盖检查器验证,
与 ontology_service 的 L2 参数覆盖逻辑一致), 保证 CBR 推荐与本体推理不冲突。

效果分布: success 75% / partial 15% / failed 10%(failed 案例给出失败原因, 用于警示)。

运行: cd backend && py -3.13 scripts/generate_cases.py
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_FILE = ROOT / "knowledge" / "material_ontology.json"
MATERIALS_FILE = ROOT / "data" / "processed" / "materials.json"
OUT = ROOT / "data" / "processed" / "cases.json"

rng = random.Random(42)


# ---------- 参数覆盖 mini-checker(与 ontology_service L2 逻辑同源) ----------
def check_coverage(orig_attrs, cand_attrs, schema):
    """逐属性检查候选是否覆盖原件; 返回 (通过项, 未通过项)"""
    passed, failed = [], []
    for prop in schema:
        key = prop["key"]
        ov, cv = orig_attrs.get(key), cand_attrs.get(key)
        if ov is None or cv is None:
            continue
        if prop["type"] == "numeric":
            ok, rule = _check_numeric(ov, cv, prop)
        else:
            ok, rule = _check_categorical(ov, cv, prop)
        (passed if ok else failed).append(
            {"key": key, "name": prop["name"], "orig_val": ov, "cand_val": cv,
             "pass": ok, "rule": rule})
    return passed, failed


def _check_numeric(ov, cv, prop):
    cov, tol = prop["coverage"], prop.get("tolerance_pct", 0)
    if cov == "gte":
        return cv >= ov, f"{cv} ≥ {ov}"
    if cov == "lte":
        return cv <= ov, f"{cv} ≤ {ov}"
    # equal: 容差内视为相等
    return abs(cv - ov) <= ov * tol / 100.0, \
        f"|{cv}-{ov}| ≤ {ov}×{tol}%"


def _check_categorical(ov, cv, prop):
    allow = prop.get("allow_map") or {}
    if not allow:  # 无映射表 -> 必须相等
        return cv == ov, f"{cv} = {ov}"
    return cv in allow.get(str(ov), [str(ov)]), \
        f"{cv} ∈ {allow.get(str(ov), [str(ov)])}"


def find_alternatives(orig, by_cat, schema):
    """找旧物料的全部合规替代物料(同小类 active, 属性全覆盖)"""
    cands = []
    for m in by_cat.get(orig["category_id"], []):
        if m["code"] == orig["code"] or m["lifecycle_status"] != "active":
            continue
        passed, failed = check_coverage(orig["attrs"], m["attrs"], schema)
        if not failed:
            cands.append(m)
    return cands


# ---------- 案例生成 ----------
WORK_CONDS = [
    {"temp_grade": "普通", "voltage_grade": "DC24V", "env": "室内"},
    {"temp_grade": "普通", "voltage_grade": "AC220V", "env": "室内"},
    {"temp_grade": "高温", "voltage_grade": "AC220V", "env": "室内"},
    {"temp_grade": "普通", "voltage_grade": "DC24V", "env": "振动"},
    {"temp_grade": "低温", "voltage_grade": "DC24V", "env": "室内"},
    {"temp_grade": "普通", "voltage_grade": "DC24V", "env": "潮湿"},
]
PROD_CATS = ["智能电表", "变频器", "电机驱动", "工业网关", "伺服控制",
             "工业控制", "温度控制", "电力计量"]
EFFECT_POOL = ["success"] * 75 + ["partial"] * 15 + ["failed"] * 10

FAIL_DETAILS = [
    "替代物料耐压余量不足, 批量上电后出现失效", "封装升级后与结构件装配干涉, 返工",
    "低温环境下电容容量衰减超预期, 测量精度不达标", "达克罗表面处理缺失, 潮湿环境锈蚀",
    "含油轴承风机振动工况寿命不达标", "ESR 偏大导致电源纹波超标, 通信异常",
]
PARTIAL_DETAILS = [
    "功能满足但成本上升, 项目利润率下降", "性能达标但交期偏长, 需提前备货",
    "可用但装配工装需微调", "性能达标但 EMI 测试需加装磁环",
]
SUCCESS_DETAILS = [
    "替换后批量使用无异常, 成本下降", "替换后性能相当, 供货稳定",
    "替换后故障率下降, 效果良好", "替换后交期缩短, 生产连续性改善",
]


def main():
    ont = json.loads(ONTOLOGY_FILE.read_text(encoding="utf-8"))
    schema_by_cat = ont["property_schema"]
    mats = json.loads(MATERIALS_FILE.read_text(encoding="utf-8"))["materials"]
    by_cat = {}
    for m in mats:
        by_cat.setdefault(m["category_id"], []).append(m)

    # 案例对象: 从各小类中挑"有合规替代"的旧物料(优先风险物料: EOL/缺货/长交期)
    candidates_pool = []  # (orig, alts, reason)
    for cat_id, schema in schema_by_cat.items():
        for m in by_cat.get(cat_id, []):
            reason = None
            if m["lifecycle_status"] == "EOL":
                reason = "EOL"
            elif m["stock_qty"] < m["safety_stock"]:
                reason = "STOCKOUT"
            elif m["lead_time_days"] >= 30:
                reason = "LEAD_TIME"
            elif rng.random() < 0.4:
                reason = "COST"
            if reason is None:
                continue
            alts = find_alternatives(m, by_cat, schema)
            if alts:
                candidates_pool.append((m, alts, reason))

    # 优先为 BOM 中实际引用的风险物料生成案例(保证 CBR 演示检索命中)
    bom_codes = set()
    boms_file = ROOT / "data" / "processed" / "boms.json"
    if boms_file.exists():
        for p in json.loads(boms_file.read_text(encoding="utf-8"))["products"]:
            bom_codes.update(ln["material_code"] for ln in p["lines"])
    candidates_pool.sort(key=lambda x: 0 if x[0]["code"] in bom_codes else 1)
    rng.shuffle(candidates_pool)

    cases, case_no, pair_count = [], 0, {}
    for orig, alts, reason in candidates_pool:
        if len(cases) >= 100:
            break
        # 同一替代对至多 2 条案例(不同工况/原因), 保证多样性
        pair_opts = [(a, pair_count.get((orig["code"], a["code"]), 0)) for a in alts]
        pair_opts.sort(key=lambda x: x[1])
        alt = pair_opts[0][0]
        if pair_opts[0][1] >= 2:
            continue
        pair_count[(orig["code"], alt["code"])] = pair_count.get((orig["code"], alt["code"]), 0) + 1
        case_no += 1
        effect = rng.choice(EFFECT_POOL)
        cond = rng.choice(WORK_CONDS)
        prod_cat = rng.choice(PROD_CATS)
        # 效果指标: success 通常成本下降/故障率不升; failed 相反
        if effect == "success":
            cost_pct = round(rng.uniform(-0.30, 0.08), 2)
            fr = max(1, int(orig["failure_rate_ppm"] * rng.uniform(0.5, 1.0)))
            detail = rng.choice(SUCCESS_DETAILS)
            lt = max(1, min(alt["lead_time_days"], rng.choice([3, 5, 7, 15])))
        elif effect == "partial":
            cost_pct = round(rng.uniform(-0.10, 0.20), 2)
            fr = int(orig["failure_rate_ppm"] * rng.uniform(0.8, 1.5))
            detail = rng.choice(PARTIAL_DETAILS)
            lt = alt["lead_time_days"]
        else:
            cost_pct = round(rng.uniform(-0.15, 0.25), 2)
            fr = int(orig["failure_rate_ppm"] * rng.uniform(2.0, 5.0))
            detail = rng.choice(FAIL_DETAILS)
            lt = alt["lead_time_days"]
        adopted = date.today() - timedelta(days=rng.randint(30, 700))
        cases.append({
            "case_no": f"CB-{case_no:04d}",
            "product_category": prod_cat,
            "work_condition": cond,
            "old_material_code": orig["code"],
            "new_material_code": alt["code"],
            "material_category_l3": orig["category_id"],
            "change_reason": reason,
            "params_old": orig["attrs"],
            "params_new": alt["attrs"],
            "effect": effect,
            "effect_detail": detail,
            "failure_rate_after_ppm": fr,
            "cost_change_pct": cost_pct,
            "lead_time_after_days": lt,
            "adopted_at": adopted.isoformat(),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {"source": "仿真数据(scripts 生成, seed=42)",
                 "disclaimer": "非企业真实变更记录; 替代对经本体 property_schema 覆盖检查验证合规"},
        "cases": cases,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    eff_stat = {}
    for c in cases:
        eff_stat[c["effect"]] = eff_stat.get(c["effect"], 0) + 1
    print(f"生成 {OUT}: {len(cases)} 条案例, 效果分布 {eff_stat}")


if __name__ == "__main__":
    main()
