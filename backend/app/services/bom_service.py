"""BOM 服务: 导入解析(Excel/CSV/JSON)、结构树构建、用量汇总、版本管理

导入列名支持中英文别名映射; 层级可显式给出或由父件-子件关系推导;
物料自动建档(导入中出现但物料表没有的编码); 每个产品维护版本快照链。
"""
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.db import (BomLine, BomProduct, BomVersion, Material, Session,
                    get_materials_by_code, get_session, _now)

# 导入列名别名映射(标准化 -> 别名列表)
COLUMN_ALIASES = {
    "material_code": ["物料编码", "物料代码", "子件编码", "子件代码", "编码", "code",
                      "material_code", "part_number", "part no", "component"],
    "parent_code": ["父件编码", "父件代码", "上层编码", "parent", "parent_code"],
    "qty_per": ["用量", "单台用量", "数量", "qty", "qty_per", "quantity", "用量(只)"],
    "level": ["层级", "层数", "层次", "level", "BOM层级"],
    "unit": ["单位", "unit"],
    "remark": ["备注", "位号", "remark", "designator", "说明"],
}


def _map_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """按别名映射标准化列名; 返回 (标准化后的 df, 警告列表)"""
    rename, warnings = {}, []
    norm_cols = {c: c for c in df.columns if c in COLUMN_ALIASES}
    for std, aliases in COLUMN_ALIASES.items():
        hit = None
        for a in aliases:
            if a in df.columns and a not in rename.values():
                hit = a
                break
        if hit:
            rename[hit] = std
        elif std == "material_code":
            raise ValueError("导入文件缺少物料编码列(支持列名: " + "/".join(
                COLUMN_ALIASES["material_code"]) + ")")
        else:
            warnings.append(f"未找到列「{std}」, 使用默认值")
    return df.rename(columns=rename), warnings


def _parse_rows(df: pd.DataFrame, product_code: str) -> tuple[list[dict], list[str]]:
    """标准化行数据: 层级推导 + 路径构建 + 数据校验"""
    warnings, rows = [], []
    for idx, raw in df.iterrows():
        code = str(raw.get("material_code", "")).strip()
        if not code or code == "nan":
            warnings.append(f"第 {idx + 2} 行物料编码为空, 已跳过")
            continue
        row = {
            "material_code": code,
            "parent_code": str(raw.get("parent_code", "") or "").strip() or product_code,
            "level": None,
            "unit": str(raw.get("unit", "") or "只").strip() or "只",
            "remark": str(raw.get("remark", "") or "").strip(),
        }
        try:
            q = float(raw.get("qty_per", 1))
            row["qty_per"] = q if q > 0 else 1.0
            if q <= 0:
                warnings.append(f"第 {idx + 2} 行用量非法({raw.get('qty_per')}), 已按 1 处理")
        except (TypeError, ValueError):
            row["qty_per"] = 1.0
            warnings.append(f"第 {idx + 2} 行用量无法解析, 已按 1 处理")
        lv = raw.get("level")
        if lv is not None and str(lv) != "nan":
            try:
                row["level"] = int(float(lv))
            except (TypeError, ValueError):
                row["level"] = None
        rows.append(row)

    # 层级推导: 显式层级优先; 有父件编码 -> 父层级+1; 否则 0
    code_to_level = {r["material_code"]: r["level"] for r in rows if r["level"] is not None}
    code_to_level[product_code] = 0
    changed = True
    while changed:
        changed = False
        for r in rows:
            if r["level"] is not None:
                continue
            if r["parent_code"] in code_to_level:
                r["level"] = code_to_level[r["parent_code"]] + 1
                code_to_level[r["material_code"]] = r["level"]
                changed = True
    for r in rows:
        if r["level"] is None:
            r["level"] = 0
            warnings.append(f"物料 {r['material_code']} 无法推导层级, 已按顶层处理")

    # 路径构建(按层级排序后逐级拼接)
    rows.sort(key=lambda r: (r["level"], r["material_code"]))
    code_to_path = {product_code: f"/{product_code}"}
    for r in rows:
        parent_path = code_to_path.get(r["parent_code"], f"/{product_code}")
        r["path"] = f"{parent_path}/{r['material_code']}"
        code_to_path.setdefault(r["material_code"], r["path"])
    return rows, warnings


def parse_import(filename: str, content: bytes, product_code: str = "") -> tuple[list[dict], list[str]]:
    """解析导入文件 -> (BOM 行列表, 警告列表)"""
    lower = filename.lower()
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(content))
    elif lower.endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(content), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(content), encoding="gbk")
    elif lower.endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        lines = data.get("lines", data) if isinstance(data, dict) else data
        df = pd.DataFrame(lines)
    else:
        raise ValueError("仅支持 .xlsx / .csv / .json 格式")
    df, warnings = _map_columns(df)
    rows, more_warnings = _parse_rows(df, product_code)
    return rows, warnings + more_warnings


# ---------- 数据库操作 ----------
def create_product_from_rows(session, params: dict, rows: list[dict]) -> dict:
    """创建产品 + BOM 行 + 初始版本快照(导入/手工录入共用)"""
    prod = BomProduct(code=params["code"], name=params["name"],
                      category=params.get("category", ""),
                      description=params.get("description", ""),
                      condition_json=json.dumps(params.get("condition") or {},
                                                ensure_ascii=False),
                      source=params.get("source", "import"))
    session.add(prod)
    session.flush()
    _save_lines(session, prod.id, rows)
    _save_version(session, prod, change_summary=f"初始 BOM(导入, {len(rows)} 行)",
                  changed_lines=[], snapshot_rows=rows)
    session.commit()
    return {"product_id": prod.id, "line_count": len(rows)}


def _save_lines(session, product_id: int, rows: list[dict]):
    for i, r in enumerate(rows, 1):
        session.add(BomLine(
            product_id=product_id, line_no=i, parent_code=r["parent_code"],
            material_code=r["material_code"], qty_per=r.get("qty_per", 1.0),
            unit=r.get("unit", "只"), level=r.get("level", 0),
            path=r.get("path", ""), remark=r.get("remark", ""),
            source=r.get("source", "import")))


def _save_version(session, prod: BomProduct, change_summary: str,
                  changed_lines: list[dict], snapshot_rows: list[dict],
                  parent_version_id: int | None = None):
    session.flush()
    # 当前最新版本
    latest = session.execute(
        select(BomVersion).where(BomVersion.product_id == prod.id)
        .order_by(BomVersion.id.desc()).limit(1)).scalars().first()
    parent_id = parent_version_id if parent_version_id is not None else \
        (latest.id if latest else None)
    snap = [{"line_no": i + 1, "parent_code": r["parent_code"],
             "material_code": r["material_code"], "qty_per": r.get("qty_per", 1.0),
             "unit": r.get("unit", "只"), "level": r.get("level", 0),
             "path": r.get("path", ""), "remark": r.get("remark", "")}
            for i, r in enumerate(snapshot_rows)]
    ver = BomVersion(product_id=prod.id, version_no=prod.version_no,
                     parent_version_id=parent_id, change_summary=change_summary,
                     changed_lines_json=json.dumps(changed_lines, ensure_ascii=False),
                     snapshot_json=json.dumps(snap, ensure_ascii=False))
    session.add(ver)
    return ver


def auto_create_materials(session, codes: list[str]) -> list[str]:
    """物料自动建档: 返回新建的编码列表"""
    existing = get_materials_by_code(session)
    created = []
    for code in set(codes):
        if code in existing:
            continue
        session.add(Material(code=code, name=code, category_id="CAT_MOD_PCBA",
                             category_l1="组件与模块", category_l2="未分类",
                             category_l3="未分类", attrs_json="{}",
                             unit_price=0.0, lead_time_days=0, moq=1,
                             supplier="导入自动建档", lifecycle_status="active",
                             stock_qty=0, safety_stock=0, failure_rate_ppm=0.0))
        created.append(code)
    return created


# ---------- 结构树 ----------
def get_tree(session, product_id: int) -> dict:
    """多层物料结构树(节点含单台用量与汇总用量)"""
    prod = session.get(BomProduct, product_id)
    if not prod:
        raise ValueError(f"产品 {product_id} 不存在")
    lines = session.execute(
        select(BomLine).where(BomLine.product_id == product_id)
        .order_by(BomLine.line_no)).scalars().all()
    mats = get_materials_by_code(session)
    root = {"code": prod.code, "name": prod.name, "level": -1, "qty_per": 1.0,
            "total_qty": 1.0, "children": [], "is_root": True}
    nodes = {prod.code: root}
    orphan = []
    for ln in lines:
        node = {"code": ln.material_code,
                "name": mats[ln.material_code].name if ln.material_code in mats
                        else ln.material_code,
                "level": ln.level, "qty_per": ln.qty_per, "unit": ln.unit,
                "remark": ln.remark,
                "lifecycle_status": mats[ln.material_code].lifecycle_status
                                    if ln.material_code in mats else "active",
                "unit_price": mats[ln.material_code].unit_price
                              if ln.material_code in mats else 0.0,
                "children": []}
        parent = nodes.get(ln.parent_code)
        if parent is None:
            parent = root
            orphan.append(ln.material_code)
        node["total_qty"] = round(node["qty_per"] * parent["total_qty"], 4)
        parent["children"].append(node)
        # 同编码节点可能出现在多个父件下, 仅记录首个
        nodes.setdefault(ln.material_code, node)
    return {"product": prod.to_dict(), "tree": root, "orphan": orphan,
            "node_count": len(lines) + 1}


# ---------- 版本管理 ----------
def snapshot_current(session, prod: BomProduct, change_summary: str,
                     changed_lines: list[dict]):
    """把当前 BOM 行快照为 (新版本号) 版本记录; 版本号在调用前由调用方递增"""
    lines = session.execute(
        select(BomLine).where(BomLine.product_id == prod.id)
        .order_by(BomLine.line_no)).scalars().all()
    rows = [{"parent_code": l.parent_code, "material_code": l.material_code,
             "qty_per": l.qty_per, "unit": l.unit, "level": l.level,
             "path": l.path, "remark": l.remark} for l in lines]
    ver = _save_version(session, prod, change_summary, changed_lines, rows)
    session.flush()
    return ver


def get_version_diff(session, version_id: int) -> dict:
    """版本快照与父版本 diff(原 BOM vs 替换后 BOM 对比数据源)"""
    version = session.get(BomVersion, version_id)
    if version is None:
        raise ValueError(f"版本 {version_id} 不存在")
    if version.parent_version_id is None:
        return {"version": version.to_dict(with_snapshot=True), "diff": [],
                "parent": None}
    parent = session.get(BomVersion, version.parent_version_id)
    snap = json.loads(version.snapshot_json or "[]")
    psnap = json.loads(parent.snapshot_json or "[]") if parent else []
    snap_map = {s["material_code"]: s for s in snap}
    psnap_map = {s["material_code"]: s for s in psnap}
    diff = []
    for code in sorted(set(snap_map) | set(psnap_map)):
        a, b = psnap_map.get(code), snap_map.get(code)
        if a and b and a["material_code"] == b["material_code"]:
            continue
        diff.append({"material_code": code,
                     "old": {"parent_code": a["parent_code"], "qty_per": a["qty_per"]} if a else None,
                     "new": {"parent_code": b["parent_code"], "qty_per": b["qty_per"]} if b else None,
                     "change": "added" if not a else ("removed" if not b else "modified")})
    return {"version": version.to_dict(with_snapshot=True),
            "parent": parent.to_dict(with_snapshot=True) if parent else None,
            "diff": diff}


def rollback_to(session, product_id: int, version_id: int) -> dict:
    """回滚到指定版本: 重建 BOM 行 + 生成新版本快照"""
    prod = session.get(BomProduct, product_id)
    ver = session.get(BomVersion, version_id)
    if not prod or not ver or ver.product_id != product_id:
        raise ValueError("版本不存在或不属于该产品")
    snap = json.loads(ver.snapshot_json or "[]")
    session.execute(delete(BomLine).where(BomLine.product_id == product_id))
    _save_lines(session, product_id, snap)
    prod.version_no += 1
    snapshot_current(session, prod,
                     change_summary=f"回滚至版本 v{ver.version_no}",
                     changed_lines=[{"type": "rollback", "to_version": ver.version_no}])
    session.commit()
    return {"product_id": product_id, "version_no": prod.version_no,
            "restored_lines": len(snap)}
