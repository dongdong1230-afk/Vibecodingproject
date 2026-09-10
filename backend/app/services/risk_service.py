"""风险物料识别服务: 按 risk_rules.json 规则库判定 BOM 中物料的
缺货(STOCKOUT)/停产(EOL)/交期超期(LEAD_TIME) 风险, 输出可解释的判定明细。

本模块与数据库解耦: 输入为物料 dict 与 BOM 行 dict, 由 router 层从 DB 装配。
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.config import RISK_RULES_FILE
from app.services.rule_engine import eval_expr, resolve_path


@lru_cache(maxsize=1)
def load_rules() -> dict:
    return json.loads(RISK_RULES_FILE.read_text(encoding="utf-8"))


LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}


def _fmt_msg(msg_tpl: str, fields: dict) -> str:
    """把消息模板中 {actual}/{threshold}/{pct} 等占位符替换为实际值"""
    out = msg_tpl
    for key, val in fields.items():
        if isinstance(val, float):
            val = round(val, 2)
        out = out.replace("{" + key + "}", str(val))
    return out


def evaluate_material(mat: dict, condition: dict | None = None) -> list[dict]:
    """判定单个物料的风险: 返回命中规则列表(按级别降序)"""
    rules_doc = load_rules()
    data = {
        "mat": mat,
        "cond": condition or {},
        "cfg": {"lead_time_threshold_days": rules_doc["lead_time_threshold_days"]},
    }
    hits = []
    for rule in rules_doc["rules"]:
        if not eval_expr(rule["condition"], data):
            continue
        # 级别划分: 依次求值 levels 中带 condition 的级别, 兜底取最后一个(condition=null)
        level_info = rule["levels"][-1]
        for lv in rule["levels"]:
            if lv["condition"] is None:
                level_info = lv
                break
            if eval_expr(lv["condition"], data):
                level_info = lv
                break
        # 判定明细(可解释): 实际值/阈值
        fields = {}
        for key, path in (rule.get("fields") or {}).items():
            val = resolve_path(data, path)
            if val is not None:
                fields[key] = val
        if "pct" not in fields and "actual" in fields and "threshold" in fields \
                and fields["threshold"]:
            fields["pct"] = int(fields["actual"] / fields["threshold"] * 100)
        hits.append({
            "rule_id": rule["rule_id"],
            "risk_type": rule["risk_type"],
            "risk_type_name": rule["risk_type_name"],
            "rule_name": rule["name"],
            "level": level_info["level"],
            "level_label": level_info["label"],
            "msg": _fmt_msg(level_info["msg"], fields),
            "detail": {k: v for k, v in fields.items()},
        })
    hits.sort(key=lambda h: LEVEL_ORDER.get(h["level"], 9))
    return hits


def scan_bom(materials_by_code: dict, bom_lines: list[dict],
             condition: dict | None = None) -> list[dict]:
    """扫描产品 BOM: 对去重后的物料逐条判定风险, 返回按最高级别排序的风险列表"""
    results, seen = [], set()
    for ln in bom_lines:
        code = ln["material_code"]
        if code in seen:
            continue
        seen.add(code)
        mat = materials_by_code.get(code)
        if not mat:
            continue
        hits = evaluate_material(mat, condition)
        if not hits:
            continue
        # 该物料在 BOM 中的出现行(可能多行)
        line_nos = [l["line_no"] for l in bom_lines if l["material_code"] == code]
        results.append({
            "material_code": code,
            "material_name": mat["name"],
            "category": f'{mat["category_l1"]}/{mat["category_l2"]}/{mat["category_l3"]}',
            "supplier": mat["supplier"],
            "line_nos": line_nos,
            "level": hits[0]["level"],           # 最高级别
            "risks": hits,
        })
    results.sort(key=lambda x: (LEVEL_ORDER.get(x["level"], 9), x["material_code"]))
    return results


def get_rules_view() -> dict:
    """规则库展示视图(前端风险规则页/阈值展示)"""
    rules_doc = load_rules()
    return {
        "lead_time_threshold_days": rules_doc["lead_time_threshold_days"],
        "level_labels": rules_doc["level_labels"],
        "rules": [
            {"rule_id": r["rule_id"], "risk_type": r["risk_type"],
             "risk_type_name": r["risk_type_name"], "name": r["name"],
             "levels": [{"level": lv["level"], "label": lv["label"]}
                        for lv in r["levels"]]}
            for r in rules_doc["rules"]
        ],
    }
