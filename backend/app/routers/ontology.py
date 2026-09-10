"""本体与知识库 API: 类别树 / 替代规则(SWRL 对应)展示"""
import sys
from pathlib import Path

from fastapi import APIRouter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from app.services.ontology_service import get_ontology

router = APIRouter(prefix="/api/ontology", tags=["本体与知识推理"])


@router.get("/categories")
def categories():
    ont = get_ontology()
    cats = sorted(ont.categories.values(), key=lambda c: (c["level"], c["id"]))
    return {"items": cats}


@router.get("/rules")
def rules():
    ont = get_ontology()
    return {
        "meta": ont.meta,
        "rules": ont.rules,
        "forbidden_pairs": ont.forbidden_pairs,
        "property_schema": ont.property_schema,
    }
