"""全局配置: 路径与领域常量(路径为各模块共享的单一事实来源)"""
from pathlib import Path

# ---------- 路径 ----------
ROOT_DIR = Path(__file__).resolve().parent.parent.parent          # dsh/
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
ONTOLOGY_FILE = KNOWLEDGE_DIR / "material_ontology.json"
RISK_RULES_FILE = KNOWLEDGE_DIR / "risk_rules.json"
FCE_CONFIG_FILE = KNOWLEDGE_DIR / "fce_config.json"
MATERIALS_FILE = PROCESSED_DIR / "materials.json"
BOMS_FILE = PROCESSED_DIR / "boms.json"
CASES_FILE = PROCESSED_DIR / "cases.json"
DB_URL = f"sqlite:///{PROCESSED_DIR / 'bom.db'}"
