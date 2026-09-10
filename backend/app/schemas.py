"""Pydantic 请求模型(API 输入校验)"""
from pydantic import BaseModel, Field


# ---------- BOM ----------
class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=300)
    condition: dict = Field(default_factory=dict)   # 产品工况 {temp_grade, voltage_grade, env}


class BomLineIn(BaseModel):
    parent_code: str = Field(default="", max_length=40)
    material_code: str = Field(min_length=1, max_length=40)
    qty_per: float = Field(default=1.0, gt=0)
    unit: str = Field(default="只", max_length=20)
    level: int = Field(default=0, ge=0)
    remark: str = Field(default="", max_length=200)


class ImportParams(BaseModel):
    product_code: str = Field(default="", max_length=50)
    product_name: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=50)
    condition: dict = Field(default_factory=dict)


# ---------- 物料 ----------
class MaterialIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    category_id: str = Field(default="", max_length=30)
    attrs: dict = Field(default_factory=dict)
    unit_price: float = Field(default=0.0, ge=0)
    lead_time_days: int = Field(default=0, ge=0)
    moq: int = Field(default=1, ge=1)
    supplier: str = Field(default="", max_length=100)
    lifecycle_status: str = Field(default="active", pattern="^(active|phaseout|EOL)$")
    stock_qty: int = Field(default=0, ge=0)
    safety_stock: int = Field(default=0, ge=0)
    failure_rate_ppm: float = Field(default=0.0, ge=0)


# ---------- 风险 ----------
class RiskScanParams(BaseModel):
    product_id: int


# ---------- 替代推理 ----------
class InferRequest(BaseModel):
    product_id: int
    material_code: str = Field(min_length=1, max_length=40)
    risk_type: str = Field(default="", max_length=20)   # EOL/STOCKOUT/LEAD_TIME


class EvaluateRequest(BaseModel):
    product_id: int
    bom_line_id: int
    candidate_codes: list[str] = Field(default_factory=list)


class PlanCreate(BaseModel):
    product_id: int
    bom_line_id: int
    new_material_code: str = Field(min_length=1, max_length=40)
    trigger_type: str = Field(default="", max_length=20)
    candidate_source: str = Field(default="ontology", max_length=30)
    ontology_rules: list = Field(default_factory=list)
    cbr_case_id: int | None = None
    fce_score: float = Field(default=0.0)
    fce_grade: str = Field(default="", max_length=10)
    evaluation: dict | None = None   # FCE 评估明细(indicators), 用于落库 plan_scores


# ---------- 案例 ----------
class CaseIn(BaseModel):
    product_category: str = Field(default="", max_length=50)
    work_condition: dict = Field(default_factory=dict)
    old_material_code: str = Field(min_length=1, max_length=40)
    new_material_code: str = Field(min_length=1, max_length=40)
    change_reason: str = Field(default="EOL", max_length=20)
    effect: str = Field(default="success", pattern="^(success|partial|failed)$")
    effect_detail: str = Field(default="", max_length=200)
    failure_rate_after_ppm: float = Field(default=0.0, ge=0)
    cost_change_pct: float = Field(default=0.0)
    lead_time_after_days: int = Field(default=0, ge=0)
