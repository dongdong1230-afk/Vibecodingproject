"""一键重建全部仿真数据: 本体 -> 物料 -> BOM -> 历史案例 -> (数据库)

数据来源如实说明: 均为脚本生成的仿真数据(随机种子固定 seed=42, 可复现),
非企业真实数据。物料件号体系/参数范围参考公开物料数据(Octopart CPL),
产品 BOM 结构参考典型工业控制/电力电子设备公开资料。

运行: cd backend && py -3.13 scripts/seed_all.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from scripts import generate_ontology, generate_materials, generate_boms, generate_cases


def seed_db():
    """把 JSON 数据写入 SQLite(依赖 app.db, 里程碑 8 实现后自动启用)"""
    try:
        from app.db import init_db, seed_database
    except ImportError:
        print("app.db 尚未实现, 跳过数据库入库(JSON 已生成)")
        return
    init_db()
    seed_database()


def main():
    print("== 1/4 生成物料替代本体 ==")
    generate_ontology.main()
    print("== 2/4 生成物料主数据 ==")
    generate_materials.main()
    print("== 3/4 生成产品 BOM ==")
    generate_boms.main()
    print("== 4/4 生成历史变更案例 ==")
    generate_cases.main()
    print("== 入库 ==")
    seed_db()
    print("全部完成: knowledge/*.json + data/processed/*.json (+ bom.db)")


if __name__ == "__main__":
    main()
