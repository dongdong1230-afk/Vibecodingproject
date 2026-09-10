"""SQLAlchemy 数据层: 8 张业务表 + 初始化 + 会话 + JSON 数据入库

表: materials / bom_products / bom_lines / risk_records / bom_change_cases
    / substitution_plans / plan_scores / bom_versions
DB_URL 在 config.py 可切 PostgreSQL; JSON 字段以 Text 存储, 服务层 json 序列化。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, create_engine, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from app.config import BOMS_FILE, CASES_FILE, DB_URL, MATERIALS_FILE

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.now().replace(microsecond=0)


class Material(Base):
    """物料主数据(本体的个体断言 ABox)"""
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    category_id: Mapped[str] = mapped_column(String(30))
    category_l1: Mapped[str] = mapped_column(String(50))
    category_l2: Mapped[str] = mapped_column(String(50))
    category_l3: Mapped[str] = mapped_column(String(50))
    attrs_json: Mapped[str] = mapped_column(Text, default="{}")
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    moq: Mapped[int] = mapped_column(Integer, default=1)
    supplier: Mapped[str] = mapped_column(String(100), default="")
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="active")
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0)
    failure_rate_ppm: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name,
                "category_id": self.category_id, "category_l1": self.category_l1,
                "category_l2": self.category_l2, "category_l3": self.category_l3,
                "attrs": json.loads(self.attrs_json or "{}"),
                "unit_price": self.unit_price, "lead_time_days": self.lead_time_days,
                "moq": self.moq, "supplier": self.supplier,
                "lifecycle_status": self.lifecycle_status,
                "stock_qty": self.stock_qty, "safety_stock": self.safety_stock,
                "failure_rate_ppm": self.failure_rate_ppm}


class BomProduct(Base):
    """产品(BOM 根)"""
    __tablename__ = "bom_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50), default="")
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(String(300), default="")
    condition_json: Mapped[str] = mapped_column(Text, default="{}")   # 产品工况(CBR 用)
    source: Mapped[str] = mapped_column(String(20), default="import")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name,
                "category": self.category, "version_no": self.version_no,
                "description": self.description,
                "condition": json.loads(self.condition_json or "{}"),
                "source": self.source,
                "created_at": self.created_at.isoformat() if self.created_at else None}


class BomLine(Base):
    """BOM 行(父件-子件-用量)"""
    __tablename__ = "bom_lines"
    __table_args__ = (Index("ix_bom_lines_product", "product_id"),
                      Index("ix_bom_lines_material", "material_code"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("bom_products.id"))
    line_no: Mapped[int] = mapped_column(Integer)
    parent_code: Mapped[str] = mapped_column(String(40))
    material_code: Mapped[str] = mapped_column(String(40))
    qty_per: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str] = mapped_column(String(20), default="只")
    level: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(300), default="")
    remark: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(20), default="import")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self, material=None):
        d = {"id": self.id, "product_id": self.product_id, "line_no": self.line_no,
             "parent_code": self.parent_code, "material_code": self.material_code,
             "qty_per": self.qty_per, "unit": self.unit, "level": self.level,
             "path": self.path, "remark": self.remark, "source": self.source}
        if material is not None:
            d["material_name"] = material.name
            d["unit_price"] = material.unit_price
            d["lifecycle_status"] = material.lifecycle_status
            d["lead_time_days"] = material.lead_time_days
        return d


class RiskRecord(Base):
    """风险识别记录"""
    __tablename__ = "risk_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("bom_products.id"), index=True)
    bom_line_id: Mapped[int] = mapped_column(Integer, default=0)
    material_code: Mapped[str] = mapped_column(String(40), index=True)
    risk_type: Mapped[str] = mapped_column(String(20))
    risk_level: Mapped[str] = mapped_column(String(10))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/resolved
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    def to_dict(self):
        return {"id": self.id, "product_id": self.product_id,
                "bom_line_id": self.bom_line_id, "material_code": self.material_code,
                "risk_type": self.risk_type, "risk_level": self.risk_level,
                "detail": json.loads(self.detail_json or "{}"),
                "status": self.status,
                "detected_at": self.detected_at.isoformat() if self.detected_at else None}


class BomChangeCase(Base):
    """历史 BOM 变更案例库(CBR 案例)"""
    __tablename__ = "bom_change_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_no: Mapped[str] = mapped_column(String(30), unique=True)
    product_category: Mapped[str] = mapped_column(String(50))
    work_condition_json: Mapped[str] = mapped_column(Text, default="{}")
    old_material_code: Mapped[str] = mapped_column(String(40), index=True)
    new_material_code: Mapped[str] = mapped_column(String(40))
    material_category_l3: Mapped[str] = mapped_column(String(30), index=True)
    change_reason: Mapped[str] = mapped_column(String(20))
    params_old_json: Mapped[str] = mapped_column(Text, default="{}")
    params_new_json: Mapped[str] = mapped_column(Text, default="{}")
    effect: Mapped[str] = mapped_column(String(20))       # success/partial/failed
    effect_detail: Mapped[str] = mapped_column(String(200), default="")
    failure_rate_after_ppm: Mapped[float] = mapped_column(Float, default=0.0)
    cost_change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    lead_time_after_days: Mapped[int] = mapped_column(Integer, default=0)
    adopted_at: Mapped[str] = mapped_column(String(20), default="")

    def to_dict(self):
        return {"id": self.id, "case_no": self.case_no,
                "product_category": self.product_category,
                "work_condition": json.loads(self.work_condition_json or "{}"),
                "old_material_code": self.old_material_code,
                "new_material_code": self.new_material_code,
                "material_category_l3": self.material_category_l3,
                "change_reason": self.change_reason,
                "params_old": json.loads(self.params_old_json or "{}"),
                "params_new": json.loads(self.params_new_json or "{}"),
                "effect": self.effect, "effect_detail": self.effect_detail,
                "failure_rate_after_ppm": self.failure_rate_after_ppm,
                "cost_change_pct": self.cost_change_pct,
                "lead_time_after_days": self.lead_time_after_days,
                "adopted_at": self.adopted_at}


class SubstitutionPlan(Base):
    """替代方案"""
    __tablename__ = "substitution_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_no: Mapped[str] = mapped_column(String(30), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("bom_products.id"), index=True)
    bom_line_id: Mapped[int] = mapped_column(Integer, default=0)
    old_material_code: Mapped[str] = mapped_column(String(40))
    new_material_code: Mapped[str] = mapped_column(String(40))
    trigger_type: Mapped[str] = mapped_column(String(20), default="")
    candidate_source: Mapped[str] = mapped_column(String(30), default="")  # ontology/cbr/both
    ontology_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    cbr_case_id: Mapped[int] = mapped_column(Integer, nullable=True)
    fce_score: Mapped[float] = mapped_column(Float, default=0.0)
    fce_grade: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="saved")  # draft/saved/applied
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self):
        return {"id": self.id, "plan_no": self.plan_no, "product_id": self.product_id,
                "bom_line_id": self.bom_line_id,
                "old_material_code": self.old_material_code,
                "new_material_code": self.new_material_code,
                "trigger_type": self.trigger_type,
                "candidate_source": self.candidate_source,
                "ontology_rules": json.loads(self.ontology_rules_json or "[]"),
                "cbr_case_id": self.cbr_case_id,
                "fce_score": self.fce_score, "fce_grade": self.fce_grade,
                "status": self.status,
                "created_at": self.created_at.isoformat() if self.created_at else None}


class PlanScore(Base):
    """FCE 评估明细(每指标一行)"""
    __tablename__ = "plan_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("substitution_plans.id"), index=True)
    indicator: Mapped[str] = mapped_column(String(20))
    raw_value: Mapped[float] = mapped_column(Float, default=0.0)
    norm_value: Mapped[float] = mapped_column(Float, default=0.0)
    membership_json: Mapped[str] = mapped_column(Text, default="[]")
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    weighted_score: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self):
        return {"id": self.id, "plan_id": self.plan_id, "indicator": self.indicator,
                "raw_value": self.raw_value, "norm_value": self.norm_value,
                "membership": json.loads(self.membership_json or "[]"),
                "weight": self.weight, "weighted_score": self.weighted_score}


class BomVersion(Base):
    """BOM 版本快照(方案应用/回滚的历史回溯数据源)"""
    __tablename__ = "bom_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("bom_products.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[int] = mapped_column(Integer, nullable=True)
    change_summary: Mapped[str] = mapped_column(String(300), default="")
    changed_lines_json: Mapped[str] = mapped_column(Text, default="[]")
    snapshot_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[str] = mapped_column(String(50), default="BOM工程师")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self, with_snapshot=False):
        d = {"id": self.id, "product_id": self.product_id,
             "version_no": self.version_no, "parent_version_id": self.parent_version_id,
             "change_summary": self.change_summary,
             "changed_lines": json.loads(self.changed_lines_json or "[]"),
             "created_by": self.created_by,
             "created_at": self.created_at.isoformat() if self.created_at else None}
        if with_snapshot:
            d["snapshot"] = json.loads(self.snapshot_json or "[]")
        return d


# ---------- 初始化与会话 ----------
def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def reset_db():
    """重建全部表(seed_all 用)"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


# ---------- 仿真数据入库 ----------
def seed_database():
    """把 data/processed/*.json 写入 SQLite(由 seed_all.py 调用)"""
    reset_db()
    materials = json.loads(MATERIALS_FILE.read_text(encoding="utf-8"))["materials"]
    boms = json.loads(BOMS_FILE.read_text(encoding="utf-8"))["products"]
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]
    with Session(engine) as s:
        for m in materials:
            s.add(Material(
                code=m["code"], name=m["name"], category_id=m["category_id"],
                category_l1=m["category_l1"], category_l2=m["category_l2"],
                category_l3=m["category_l3"], attrs_json=json.dumps(m["attrs"],
                                                                    ensure_ascii=False),
                unit_price=m["unit_price"], lead_time_days=m["lead_time_days"],
                moq=m["moq"], supplier=m["supplier"],
                lifecycle_status=m["lifecycle_status"],
                stock_qty=m["stock_qty"], safety_stock=m["safety_stock"],
                failure_rate_ppm=m["failure_rate_ppm"]))
        for p in boms:
            prod = BomProduct(code=p["code"], name=p["name"], category=p["category"],
                              version_no=1,
                              condition_json=json.dumps(p["condition"], ensure_ascii=False),
                              source="import")
            s.add(prod)
            s.flush()
            for ln in p["lines"]:
                s.add(BomLine(product_id=prod.id, line_no=ln["line_no"],
                              parent_code=ln["parent_code"],
                              material_code=ln["material_code"],
                              qty_per=ln["qty_per"], unit=ln.get("unit", "只"),
                              level=ln["level"], path=ln["path"],
                              remark=ln.get("remark", ""), source="import"))
            # 初始版本快照(版本回溯基线)
            s.flush()
            snap = [{"line_no": ln["line_no"], "parent_code": ln["parent_code"],
                     "material_code": ln["material_code"], "qty_per": ln["qty_per"],
                     "level": ln["level"], "remark": ln.get("remark", "")}
                    for ln in p["lines"]]
            ver = BomVersion(product_id=prod.id, version_no=1, parent_version_id=None,
                             change_summary=f"初始 BOM(导入, {len(p['lines'])} 行)",
                             changed_lines_json="[]",
                             snapshot_json=json.dumps(snap, ensure_ascii=False))
            s.add(ver)
        for c in cases:
            s.add(BomChangeCase(
                case_no=c["case_no"], product_category=c["product_category"],
                work_condition_json=json.dumps(c["work_condition"], ensure_ascii=False),
                old_material_code=c["old_material_code"],
                new_material_code=c["new_material_code"],
                material_category_l3=c["material_category_l3"],
                change_reason=c["change_reason"],
                params_old_json=json.dumps(c["params_old"], ensure_ascii=False),
                params_new_json=json.dumps(c["params_new"], ensure_ascii=False),
                effect=c["effect"], effect_detail=c["effect_detail"],
                failure_rate_after_ppm=c["failure_rate_after_ppm"],
                cost_change_pct=c["cost_change_pct"],
                lead_time_after_days=c["lead_time_after_days"],
                adopted_at=c["adopted_at"]))
        s.commit()
    print(f"入库完成: {len(materials)} 物料 / {len(boms)} 产品 / {len(cases)} 案例")


def get_materials_by_code(session: Session) -> dict[str, Material]:
    return {m.code: m for m in session.execute(select(Material)).scalars()}
