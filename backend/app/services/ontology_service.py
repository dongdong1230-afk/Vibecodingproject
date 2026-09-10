"""本体与知识推理服务(技术模块 1): 推理"哪些物料可以替代"风险物料

本体数据: knowledge/material_ontology.json(类别层级/属性 schema/禁止替代对/替代适配规则)
推理流程(三级过滤, 每步记录命中规则, 输出可解释推理路径):
  L1 类别约束: 同小类物料为候选集(倒排索引 O(1) 取集合), 记录 R-CAT-01
  L2 参数覆盖: 逐属性按 property_schema 检查(gte/lte/equal 容差/allow_map 封装升级),
               任一硬属性不满足即剔除
  L3 显式规则: 替代适配规则(rule_engine 求值) + 禁止替代对 + 工况约束,
               deny 剔除 / warn 记录警示
支持导出 ontology.cypher(Neo4j 兼容), 见 export_cypher()。

与标准本体语言的对应关系见本体 meta.owl_mapping_note(OWL 类公理/DataProperty/SWRL)。
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.config import MATERIALS_FILE, ONTOLOGY_FILE, PROCESSED_DIR
from app.services.rule_engine import eval_expr

WU_PALMER = True  # CBR 用类别层级相似度时复用本模块的类别树接口


class OntologyService:
    """物料替代本体: 加载/索引/推理"""

    def __init__(self):
        doc = json.loads(ONTOLOGY_FILE.read_text(encoding="utf-8"))
        self.meta = doc["meta"]
        self.categories = {c["id"]: c for c in doc["categories"]}
        self.property_schema = doc["property_schema"]
        self.forbidden_pairs = doc["forbidden_pairs"]
        self.rules = doc["rules"]
        # 小类 -> 物料倒排索引
        self._materials = None
        self._by_category = None

    # ---------- 数据加载 ----------
    def load_materials(self, materials: list[dict] | None = None):
        if materials is not None:
            self._materials = materials
        elif self._materials is None:
            self._materials = json.loads(
                MATERIALS_FILE.read_text(encoding="utf-8"))["materials"]
        self._by_category = {}
        for m in self._materials:
            self._by_category.setdefault(m["category_id"], []).append(m)
        return self._materials

    # ---------- 类别树接口 ----------
    def parent_id(self, cat_id: str) -> str | None:
        return self.categories[cat_id]["parent_id"]

    def ancestors(self, cat_id: str) -> list[str]:
        """自下而上祖先链(含自身)"""
        chain, cur = [], cat_id
        while cur is not None and cur in self.categories:
            chain.append(cur)
            cur = self.categories[cur]["parent_id"]
        return chain

    def lca_depth(self, cat_a: str, cat_b: str) -> int:
        """两类别最近公共祖先的深度(0=大类), 用于 CBR 类别相似度"""
        anc_a = set(self.ancestors(cat_a))
        depth = 0
        for cid in self.ancestors(cat_b):
            if cid in anc_a:
                depth = max(depth, self.categories[cid]["level"])
        return depth

    def category_sim(self, cat_a: str, cat_b: str) -> float:
        """类别层级相似度(归一化 Wu-Palmer 变体):
        同小类=1.0, 同中类=0.667, 同大类=0.333, 无公共祖先=0"""
        anc_a = set(self.ancestors(cat_a))
        lca = None
        for cid in self.ancestors(cat_b):
            if cid in anc_a:
                if lca is None or self.categories[cid]["level"] > self.categories[lca]["level"]:
                    lca = cid
        if lca is None:
            return 0.0
        depth = self.categories[lca]["level"]
        max_depth = max(self.categories[cat_a]["level"], self.categories[cat_b]["level"])
        return (depth + 1) / (max_depth + 1)

    # ---------- L2: 参数覆盖 ----------
    def check_property(self, prop: dict, orig_val, cand_val) -> tuple[bool, str]:
        """单属性覆盖检查: 返回 (是否通过, 说明文本)"""
        key, name = prop["key"], prop["name"]
        if orig_val is None or cand_val is None:
            return True, f"{name} 缺失跳过"
        if prop["type"] == "numeric":
            cov, tol = prop["coverage"], prop.get("tolerance_pct", 0)
            if cov == "gte":
                ok = cand_val >= orig_val
                return ok, f"{name} {cand_val} ≥ {orig_val}"
            if cov == "lte":
                ok = cand_val <= orig_val
                return ok, f"{name} {cand_val} ≤ {orig_val}"
            ok = abs(cand_val - orig_val) <= orig_val * tol / 100.0
            return ok, f"{name} |{cand_val}-{orig_val}| ≤ {orig_val}×{tol}%"
        # categorical: 相等或 allow_map 向上兼容
        allow = prop.get("allow_map") or {}
        allowed = allow.get(str(orig_val), [str(orig_val)])
        if cand_val in allowed:
            return True, f"{name} {cand_val} ∈ {allowed}"
        return False, f"{name} {cand_val} ∉ {allowed}"

    def check_coverage(self, orig: dict, cand: dict) -> tuple[list, list]:
        """L2 参数覆盖: 返回 (通过明细, 未通过明细)"""
        cat_id = orig.get("category_id")
        schema = self.property_schema.get(cat_id, [])
        passed, failed = [], []
        for prop in schema:
            ok, text = self.check_property(
                prop, orig["attrs"].get(prop["key"]), cand["attrs"].get(prop["key"]))
            item = {"key": prop["key"], "name": prop["name"],
                    "orig_val": orig["attrs"].get(prop["key"]),
                    "cand_val": cand["attrs"].get(prop["key"]),
                    "pass": ok, "rule_id": f"R-PARAM-{prop['key']}", "text": text}
            (passed if ok else failed).append(item)
        return passed, failed

    # ---------- L3: 显式规则与禁止对 ----------
    def forbidden_hit(self, orig_cat: str, cand_cat: str) -> dict | None:
        """禁止替代对命中检查(双向)"""
        for fp in self.forbidden_pairs:
            if {orig_cat, cand_cat} == set(fp["pair"]):
                return fp
        return None

    def eval_rules(self, orig: dict, cand: dict, cond: dict | None = None) -> tuple[list, list]:
        """L3 显式规则求值: 返回 (fired allow 规则, deny/warn 命中)"""
        data = {"orig": orig, "cand": cand, "cond": cond or {}}
        fired, denies, warns = [], [], []
        for rule in self.rules:
            scope = rule.get("scope", "*")
            if scope != "*" and scope != orig.get("category_id"):
                continue
            if not eval_expr(rule["if"], data):
                continue
            if rule.get("then") == "deny":
                denies.append(rule)
            elif rule.get("then") == "warn":
                warns.append(rule)
            else:
                fired.append(rule)
        return fired, denies, warns

    # ---------- 推理入口 ----------
    def infer(self, orig: dict, condition: dict | None = None,
              materials: list[dict] | None = None) -> dict:
        """对风险物料 orig 推理合规替代集合

        Args:
            orig: 物料 dict(含 category_id/attrs/...)
            condition: 产品工况 dict(如 {"temp_grade": "高温", ...})
            materials: 物料池(默认 data/processed/materials.json)
        Returns:
            {material_code, candidates: [{code,name,...,match_detail,fired_rules,
             trace_text,warnings}], candidate_count}
        """
        self.load_materials(materials)
        cat_id = orig.get("category_id")
        candidates = []
        if cat_id not in self.property_schema:
            return {"material_code": orig["code"], "candidates": [], "candidate_count": 0,
                    "reason": "组件/无替代schema类别, 不参与物料级替代推理"}

        for cand in self._by_category.get(cat_id, []):
            if cand["code"] == orig["code"] or cand["lifecycle_status"] != "active":
                continue
            match_detail, fired_rules, warnings = [], [], []
            # L1 同小类(倒排索引保证) + L2 参数覆盖 + L3 显式规则
            fired_rules.append("R-CAT-01")
            passed, failed = self.check_coverage(orig, cand)
            match_detail = passed + failed
            if failed:
                continue  # 硬属性不满足 -> 剔除
            fp = self.forbidden_hit(cat_id, cand["category_id"])
            if fp:
                continue  # 禁止替代对 -> 剔除(记录于 trace 前的集合不展示, 直接过滤)
            fired, denies, warns = self.eval_rules(orig, cand, condition)
            if denies:
                continue
            fired_rules += [r["rule_id"] for r in fired]
            warnings = [{"rule_id": r["rule_id"], "name": r["name"],
                         "reason": r.get("reason", "")} for r in warns]
            trace = self._build_trace(passed, fired, warns, fp=None)
            candidates.append({
                "code": cand["code"], "name": cand["name"],
                "category": f'{cand["category_l1"]}/{cand["category_l2"]}/{cand["category_l3"]}',
                "unit_price": cand["unit_price"], "lead_time_days": cand["lead_time_days"],
                "supplier": cand["supplier"], "failure_rate_ppm": cand["failure_rate_ppm"],
                "lifecycle_status": cand["lifecycle_status"],
                "attrs": cand["attrs"],
                "match_detail": match_detail,
                "fired_rules": fired_rules,
                "trace_text": trace,
                "warnings": warnings,
            })
        candidates.sort(key=lambda c: c["code"])
        return {"material_code": orig["code"], "candidates": candidates,
                "candidate_count": len(candidates)}

    def soft_scores(self, orig: dict, cand: dict) -> dict:
        """FCE 输入软评分: 硬约束通过后量化性能裕度与工艺匹配(区分候选优劣)

        perf_match     性能匹配度: 数值属性裕度(gte/lte 超出越多裕度越足, equal 越接近原件
                       越好) + 类别属性映射距离(相同=1, 允许映射=0.8/0.6)的均值
        process_compat 工艺兼容性: 类别属性(封装/密封/表面处理等)相同=1, 允许映射升级=0.75;
                       无数值类别属性时取默认 0.9(数值参数不改变装配工艺)
        """
        cat_id = orig.get("category_id")
        schema = self.property_schema.get(cat_id, [])
        perf_parts, proc_parts = [], []
        for prop in schema:
            ov, cv = orig["attrs"].get(prop["key"]), cand["attrs"].get(prop["key"])
            if ov is None or cv is None:
                continue
            if prop["type"] == "numeric":
                if prop["coverage"] == "gte":
                    perf_parts.append(min(1.5, cv / ov) / 1.5 if ov else 1.0)
                elif prop["coverage"] == "lte":
                    perf_parts.append(min(1.5, ov / cv) / 1.5 if cv else 1.0)
                else:  # equal 容差内: 偏差越小越好(2 倍容差处为 0)
                    tol = max(prop.get("tolerance_pct", 0) / 100.0, 1e-6)
                    dev = abs(cv - ov) / ov if ov else 0.0
                    perf_parts.append(1 - min(1.0, dev / (2 * tol)))
            else:  # categorical: 相同=1, 允许映射升级按距离递减
                allow = prop.get("allow_map") or {}
                allowed = [str(x) for x in allow.get(str(ov), [str(ov)])]
                idx = allowed.index(str(cv)) if str(cv) in allowed else len(allowed)
                perf_parts.append({0: 1.0, 1: 0.8, 2: 0.6}.get(idx, 0.5))
                proc_parts.append(1.0 if cv == ov else 0.75)
        perf = sum(perf_parts) / len(perf_parts) if perf_parts else 1.0
        proc = sum(proc_parts) / len(proc_parts) if proc_parts else 0.9
        return {"perf_match": round(perf, 4), "process_compat": round(proc, 4)}

    def _build_trace(self, passed, fired_rules, warns, fp) -> str:
        parts = ["同小类[R-CAT-01]✓"]
        for p in passed:
            parts.append(f"{p['text']}[{p['rule_id']}]✓")
        for r in fired_rules:
            parts.append(f"规则命中[{r}]✓")
        for w in warns:
            parts.append(f"警示[{w['rule_id']}]")
        return " → ".join(parts)

    # ---------- Neo4j 兼容导出 ----------
    def export_cypher(self, materials: list[dict] | None = None) -> str:
        """生成 ontology.cypher: 类别/属性/规则/物料节点与
        SUBCLASS_OF/HAS_PROPERTY/APPLIES_TO/INSTANCE_OF/CAN_SUBSTITUTE 边"""
        self.load_materials(materials)
        lines = [
            "// 离散制造物料替代本体 Cypher 导出(由 ontology_service.export_cypher 生成)",
            "// 节点: Category/Property/Rule/Material; 边: SUBCLASS_OF/HAS_PROPERTY/",
            "// APPLIES_TO/INSTANCE_OF/CAN_SUBSTITUTE/FORBID_SUBSTITUTE",
            "",
        ]
        # 类别节点 + SUBCLASS_OF
        for c in self.categories.values():
            lines.append(f'CREATE (c_{c["id"]}:Category '
                         f'{{id: "{c["id"]}", name: "{c["name"]}", level: {c["level"]}}})')
        for c in self.categories.values():
            if c["parent_id"]:
                lines.append(f'CREATE (c_{c["id"]})-[:SUBCLASS_OF]->(c_{c["parent_id"]})')
        # 属性 schema 节点 + HAS_PROPERTY
        for cat_id, props in self.property_schema.items():
            for p in props:
                pid = f'{cat_id}__{p["key"]}'
                lines.append(f'CREATE (p_{pid}:Property '
                             f'{{key: "{p["key"]}", name: "{p["name"]}", '
                             f'coverage: "{p["coverage"]}"}})')
                lines.append(f'CREATE (c_{cat_id})-[:HAS_PROPERTY]->(p_{pid})')
        # 规则节点 + APPLIES_TO
        for r in self.rules:
            scope = r.get("scope", "*")
            lines.append(f'CREATE (r_{r["rule_id"]}:Rule '
                         f'{{rule_id: "{r["rule_id"]}", name: "{r["name"]}", '
                         f'then: "{r["then"]}", swrl: "{r.get("swrl", "")}"}})')
            if scope != "*" and scope in self.categories:
                lines.append(f'CREATE (r_{r["rule_id"]})-[:APPLIES_TO]->(c_{scope})')
        for fp in self.forbidden_pairs:
            a, b = fp["pair"]
            lines.append(f'CREATE (c_{a})-[:FORBID_SUBSTITUTE {{rule_id: '
                         f'"{fp["rule_id"]}"}}]->(c_{b})')
        # 物料实例 + INSTANCE_OF + CAN_SUBSTITUTE(同小类全对覆盖计算)
        for m in self._materials:
            if m["category_id"] not in self.categories:
                continue
            code = m["code"].replace("'", "\\'")
            lines.append(f'CREATE (m_{m["code"]}:Material '
                         f'{{code: "{code}", name: "{m["name"]}"}})')
            lines.append(f'CREATE (m_{m["code"]})-[:INSTANCE_OF]->(c_{m["category_id"]})')
        for cat_id in self.property_schema:
            items = self._by_category.get(cat_id, [])
            for a in items:
                for b in items:
                    if a["code"] == b["code"]:
                        continue
                    if b["lifecycle_status"] != "active":
                        continue
                    if not self.check_coverage(a, b)[1] and \
                            not self.forbidden_hit(cat_id, cat_id):
                        lines.append(f'CREATE (m_{a["code"]})-[:CAN_SUBSTITUTE]->'
                                     f'(m_{b["code"]})')
        text = ";\n".join(lines) + ";\n"
        out = PROCESSED_DIR / "ontology.cypher"
        out.write_text(text, encoding="utf-8")
        return str(out)


@lru_cache(maxsize=1)
def get_ontology() -> OntologyService:
    return OntologyService()
