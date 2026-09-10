"""生成仿真产品 BOM 数据 data/processed/boms.json

8 个典型离散制造产品, 3~4 层 BOM(整机→组件/模块→子板→元器件/零件)。
每个产品刻意引用 2~4 个风险物料(EOL/缺货/长交期/工况约束), 形成
"风险识别 → 替代推理 → 方案评估"演示闭环。
产品结构与物料类别需求参考典型工业控制/电力电子设备 BOM 构成。

运行: cd backend && py -3.13 scripts/generate_boms.py
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATERIALS_FILE = ROOT / "data" / "processed" / "materials.json"
OUT = ROOT / "data" / "processed" / "boms.json"

rng = random.Random(42)

BY_CAT = {}
BY_CODE = {}
ALT_COUNT = {}   # 物料 -> 合规替代候选数(保证 BOM 引用物料都有替代链)


def load_materials():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
    from scripts.generate_cases import check_coverage
    data = json.loads(MATERIALS_FILE.read_text(encoding="utf-8"))
    for m in data["materials"]:
        BY_CAT.setdefault(m["category_id"], []).append(m)
        BY_CODE[m["code"]] = m
    # 预计算每个物料的合规替代候选数(与本体推理 L2 参数覆盖逻辑同源)
    ont = json.loads((ROOT / "knowledge" / "material_ontology.json")
                     .read_text(encoding="utf-8"))
    schema = ont["property_schema"]
    for m in data["materials"]:
        if m["category_id"] not in schema:
            continue
        n = sum(1 for c in BY_CAT[m["category_id"]]
                if c["code"] != m["code"] and c["lifecycle_status"] == "active"
                and not check_coverage(m["attrs"], c["attrs"], schema[m["category_id"]])[1])
        ALT_COUNT[m["code"]] = n


def is_risky(m):
    return (m["lifecycle_status"] in ("EOL", "phaseout")
            or m["stock_qty"] < m["safety_stock"]
            or m["lead_time_days"] >= 30)


def pick(cat_id, n=1, status=None, prefer=None):
    """按小类随机挑物料; 排除"风险且无替代候选"的物料(避免演示中推理为空)"""
    pool = [m for m in BY_CAT.get(cat_id, [])
            if (status is None or m["lifecycle_status"] == status)
            and not (is_risky(m) and ALT_COUNT.get(m["code"], 0) == 0)]
    if not pool:
        raise ValueError(f"类别 {cat_id} 无可用物料(status={status})")
    if prefer:
        pre = [m for m in pool if prefer(m)]
        if pre:
            pool = pre
    return rng.sample(pool, min(n, len(pool)))


def find_risky(cat_id, cond):
    """挑满足条件的风险物料(EOL/缺货/长交期等), 且必须有替代候选"""
    pool = [m for m in BY_CAT.get(cat_id, [])
            if cond(m) and ALT_COUNT.get(m["code"], 0) >= 1]
    if not pool:
        raise ValueError(f"类别 {cat_id} 无满足条件的风险物料(含替代候选)")
    return rng.choice(pool)


def r(cat_id, qty, remark=""):
    """类别需求: 从该小类随机挑 1 个物料"""
    return {"cat": cat_id, "qty": qty, "remark": remark}


def risky(kind, qty, remark=""):
    """风险物料需求: 从对应风险池挑选(刻意引用)"""
    return {"risky": kind, "qty": qty, "remark": remark}


RISKY_POOLS = {
    "EOL_RES": lambda: find_risky("CAT_RES_SMD", lambda m: m["lifecycle_status"] == "EOL"),
    "EOL_STEP": lambda: find_risky("CAT_MOTOR_STEP", lambda m: m["lifecycle_status"] == "EOL"),
    "EOL_MOS": lambda: find_risky("CAT_MOSFET", lambda m: m["lifecycle_status"] == "EOL"),
    "EOL_CAP": lambda: find_risky("CAT_CAP_ALU", lambda m: m["lifecycle_status"] == "EOL"),
    "STOCKOUT_TANT": lambda: find_risky("CAT_CAP_TANT", lambda m: m["stock_qty"] < m["safety_stock"]),
    "STOCKOUT_CAP": lambda: find_risky("CAT_CAP_ALU", lambda m: m["stock_qty"] < m["safety_stock"]),
    "LONG_LT_BRG": lambda: find_risky("CAT_BRG_DGBB", lambda m: m["lead_time_days"] >= 30),
    "PHASEOUT_MLCC": lambda: find_risky("CAT_CAP_MLCC", lambda m: m["lifecycle_status"] == "phaseout"),
    "ENV_BOLT_DAC": lambda: find_risky("CAT_BOLT", lambda m: m["attrs"].get("surface") == "达克罗"),
}


def resolve(node):
    """需求节点 -> (物料 code, 名称, remark); 同产品内同 risky 需求复用同一物料"""
    if isinstance(node, str):
        mat = BY_CODE.get(node)
        return node, mat["name"] if mat else node, ""
    if "risky" in node:
        code = node.get("_code")
        if code is None:
            code = RISKY_POOLS[node["risky"]]()["code"]
            node["_code"] = code
        mat = BY_CODE[code]
    else:
        code = node.get("_code")
        if code is None:
            code = pick(node["cat"], 1)[0]["code"]
            node["_code"] = code
        mat = BY_CODE[code]
    return code, mat["name"], node.get("remark", "")


# ---------- 组件定义: 组件 code -> [(需求节点, 单组件用量)] ----------
COMP_DEFS = {
    # 智能电表 PSM-100
    "ASM-PCBA-PSM100-MAIN": [
        (r("CAT_SENSOR_TEMP", 1, "RT1"), 1), (r("CAT_CAP_MLCC", 12, "C1-C12"), 1),
        (r("CAT_CAP_ALU", 4, "C13-C16"), 1), (r("CAT_RES_SMD", 30, "R1-R30"), 1),
        (r("CAT_DIODE_RECT", 3, "D1-D3"), 1), (r("CAT_DIODE_ZENER", 2, "D4,D5"), 1),
        (r("CAT_MOSFET", 2, "Q1,Q2"), 1), (r("CAT_CONN_BTB", 2, "J1,J2"), 1),
        (r("CAT_IND_PWR", 2, "L1,L2"), 1), (risky("EOL_RES", 4, "R31-R34(停产风险)"), 1),
    ],
    "ASM-PCBA-PSM100-PWR": [
        (r("CAT_PSU_ACDC", 1, "PS1"), 1), (r("CAT_CAP_ALU", 6, "C21-C26"), 1),
        (risky("STOCKOUT_TANT", 3, "C27-C29(缺货风险)"), 1),
        (r("CAT_DIODE_RECT", 4, "D11-D14"), 1), (r("CAT_CONN_TERM", 2, "J11,J12"), 1),
    ],
    "ASM-PCBA-PSM100-IO": [
        (r("CAT_CONN_TERM", 6, "J21-J26"), 1), (r("CAT_RELAY_EM", 2, "K1,K2"), 1),
        (r("CAT_RES_SMD", 16, "R41-R56"), 1), (r("CAT_DIODE_ZENER", 3, "D21-D23"), 1),
    ],
    "SHT-CASE-PSM100-1.0MM": [
        (r("CAT_PLASTIC_SHELL", 1, ""), 1), (risky("LONG_LT_BRG", 2, "传动用轴承(长交期)"), 1),
        (r("CAT_BOLT", 8, "M3/M4 紧固"), 1), (r("CAT_NUT", 8, ""), 1),
    ],
    "ASM-CABLE-PSM100": [(r("CAT_SEAL_ORING", 2, ""), 1)],
    # 变频器控制板 VFD-2000(高温工况)
    "ASM-PCBA-VFD2000-MAIN": [
        (r("CAT_MOSFET", 6, "Q1-Q6 功率桥"), 1), (risky("EOL_RES", 6, "R1-R6(停产风险)"), 1),
        (r("CAT_CAP_MLCC", 20, "C1-C20"), 1), (r("CAT_CAP_ALU", 8, "C21-C28"), 1),
        (r("CAT_IND_PWR", 4, "L1-L4"), 1), (r("CAT_DIODE_RECT", 6, "D1-D6"), 1),
        (r("CAT_CONN_BTB", 3, "J1-J3"), 1), (r("CAT_RES_SMD", 40, "R7-R46"), 1),
        (r("CAT_SENSOR_TEMP", 2, "RT1,RT2"), 1), ("ASM-PCBA-VFD2000-DRV", 1),
    ],
    "ASM-PCBA-VFD2000-DRV": [
        (r("CAT_MOSFET", 3, "Q7-Q9 驱动级"), 1), (r("CAT_DIODE_RECT", 3, "D7-D9"), 1),
        (r("CAT_CAP_MLCC", 6, "C41-C46"), 1), (r("CAT_RES_SMD", 12, "R61-R72"), 1),
    ],
    "ASM-PCBA-VFD2000-PWR": [
        (r("CAT_PSU_ACDC", 1, "PS1"), 1), (r("CAT_CAP_ALU", 4, "C31-C34"), 1),
        (risky("STOCKOUT_TANT", 2, "C35,C36(缺货风险)"), 1), (r("CAT_CONN_TERM", 4, "J11-J14"), 1),
    ],
    "ASM-PCBA-VFD2000-IO": [
        (r("CAT_CONN_TERM", 8, "J21-J28"), 1), (r("CAT_RELAY_EM", 3, "K1-K3"), 1),
        (r("CAT_RES_SMD", 20, "R51-R70"), 1),
    ],
    "SHT-CASE-VFD2000-1.0MM": [
        (r("CAT_PLASTIC_SHELL", 1, ""), 1), (r("CAT_FAN_AXIAL", 2, "散热风机"), 1),
        (r("CAT_BOLT", 10, ""), 1),
    ],
    "ASM-CABLE-VFD2000": [(r("CAT_SEAL_ORING", 3, ""), 1)],
    # AGV 驱动器 AGV-DRV(振动工况)
    "ASM-PCBA-AGVDRV-MAIN": [
        (risky("EOL_STEP", 2, "M1,M2 驱动电机(停产)"), 1),
        (r("CAT_MOSFET", 8, "Q1-Q8"), 1), (r("CAT_CAP_ALU", 6, "C1-C6"), 1),
        (r("CAT_CAP_MLCC", 16, "C7-C22"), 1), (r("CAT_RES_SMD", 35, "R1-R35"), 1),
        (r("CAT_DIODE_RECT", 4, "D1-D4"), 1), (r("CAT_CONN_BTB", 4, "J1-J4"), 1),
        (r("CAT_IND_PWR", 3, "L1-L3"), 1), ("ASM-PCBA-AGVDRV-DRV", 1),
    ],
    "ASM-PCBA-AGVDRV-DRV": [
        (r("CAT_MOSFET", 4, "Q9-Q12 驱动级"), 1), (r("CAT_DIODE_RECT", 2, "D5,D6"), 1),
        (r("CAT_CAP_MLCC", 5, "C41-C45"), 1), (r("CAT_RES_SMD", 10, "R61-R70"), 1),
    ],
    "ASM-PCBA-AGVDRV-PWR": [
        (r("CAT_PSU_ACDC", 1, "PS1"), 1), (r("CAT_CAP_ALU", 5, "C31-C35"), 1),
        (r("CAT_CONN_TERM", 3, "J11-J13"), 1), (r("CAT_DIODE_RECT", 2, "D11,D12"), 1),
    ],
    "ASM-PCBA-AGVDRV-IO": [
        (r("CAT_CONN_TERM", 6, "J21-J26"), 1), (r("CAT_RELAY_EM", 2, "K1,K2"), 1),
        (r("CAT_RES_SMD", 18, "R41-R58"), 1), (r("CAT_SENSOR_TEMP", 1, "RT1"), 1),
    ],
    "MAC-ALU-6061-AGVDRV": [
        (risky("LONG_LT_BRG", 4, "轮系轴承(长交期)"), 1), (r("CAT_BOLT", 12, ""), 1),
        (r("CAT_NUT", 12, ""), 1), (r("CAT_WASHER", 12, ""), 1),
    ],
    "ASM-CABLE-AGVDRV": [(r("CAT_SEAL_ORING", 4, ""), 1)],
    # 工业网关 GW-3100
    "ASM-PCBA-GW3100-MAIN": [
        (r("CAT_CAP_MLCC", 18, "C1-C18"), 1), (r("CAT_RES_SMD", 28, "R1-R28"), 1),
        (risky("EOL_RES", 3, "R29-R31(停产风险)"), 1),
        (r("CAT_MOSFET", 2, "Q1,Q2"), 1), (r("CAT_DIODE_ZENER", 2, "D1,D2"), 1),
        (r("CAT_CONN_BTB", 3, "J1-J3"), 1), (r("CAT_IND_PWR", 2, "L1,L2"), 1),
        (r("CAT_CAP_ALU", 3, "C19-C21"), 1),
    ],
    "ASM-PCBA-GW3100-PWR": [
        (r("CAT_PSU_ACDC", 1, "PS1"), 1), (risky("STOCKOUT_TANT", 2, "C31,C32(缺货风险)"), 1),
        (r("CAT_DIODE_RECT", 2, "D11,D12"), 1), (r("CAT_CONN_TERM", 2, "J11,J12"), 1),
    ],
    "ASM-PCBA-GW3100-IO": [
        (r("CAT_CONN_TERM", 8, "J21-J28"), 1), (r("CAT_RELAY_EM", 1, "K1"), 1),
        (r("CAT_RES_SMD", 12, "R41-R52"), 1),
    ],
    "SHT-CASE-GW3100-1.0MM": [
        (r("CAT_PLASTIC_SHELL", 1, ""), 1), (r("CAT_BOLT", 6, ""), 1),
    ],
    "ASM-CABLE-GW3100": [],
    # 伺服控制器 SRV-CTL(高温工况)
    "ASM-PCBA-SRVCTL-MAIN": [
        (risky("EOL_MOS", 3, "Q1-Q3(停产风险)"), 1),
        (r("CAT_CAP_MLCC", 24, "C1-C24"), 1), (r("CAT_CAP_ALU", 10, "C25-C34"), 1),
        (r("CAT_RES_SMD", 45, "R1-R45"), 1), (r("CAT_IND_PWR", 5, "L1-L5"), 1),
        (r("CAT_DIODE_RECT", 6, "D1-D6"), 1), (r("CAT_CONN_BTB", 3, "J1-J3"), 1),
        (r("CAT_SENSOR_TEMP", 2, "RT1,RT2"), 1), ("ASM-PCBA-SRVCTL-DRV", 1),
    ],
    "ASM-PCBA-SRVCTL-DRV": [
        (r("CAT_MOSFET", 3, "Q4-Q6 驱动级"), 1), (r("CAT_DIODE_RECT", 3, "D7-D9"), 1),
        (r("CAT_CAP_MLCC", 6, "C51-C56"), 1), (r("CAT_RES_SMD", 10, "R81-R90"), 1),
    ],
    "ASM-PCBA-SRVCTL-PWR": [
        (r("CAT_PSU_ACDC", 1, "PS1"), 1), (r("CAT_CAP_ALU", 6, "C41-C46"), 1),
        (risky("STOCKOUT_TANT", 2, "C47,C48(缺货风险)"), 1), (r("CAT_CONN_TERM", 5, "J11-J15"), 1),
    ],
    "ASM-PCBA-SRVCTL-IO": [
        (r("CAT_CONN_TERM", 10, "J21-J30"), 1), (r("CAT_RELAY_EM", 3, "K1-K3"), 1),
        (r("CAT_RES_SMD", 22, "R51-R72"), 1),
    ],
    "SHT-CASE-SRVCTL-1.0MM": [
        (r("CAT_PLASTIC_SHELL", 1, ""), 1), (r("CAT_FAN_AXIAL", 2, ""), 1),
        (r("CAT_BOLT", 10, ""), 1),
    ],
    "ASM-CABLE-SRVCTL": [(r("CAT_SEAL_ORING", 2, ""), 1)],
    # PLC 扩展模块 PLC-EXT(潮湿工况)
    "ASM-PCBA-PLCEXT-MAIN": [
        (r("CAT_RES_SMD", 25, "R1-R25"), 1), (r("CAT_CAP_MLCC", 15, "C1-C15"), 1),
        (risky("EOL_RES", 2, "R26,R27(停产风险)"), 1),
        (r("CAT_DIODE_RECT", 3, "D1-D3"), 1), (r("CAT_MOSFET", 2, "Q1,Q2"), 1),
        (r("CAT_CONN_BTB", 2, "J1,J2"), 1), (r("CAT_IND_PWR", 2, "L1,L2"), 1),
    ],
    "ASM-PCBA-PLCEXT-IO": [
        (r("CAT_CONN_TERM", 12, "J11-J22"), 1), (r("CAT_RELAY_EM", 4, "K1-K4"), 1),
        (risky("STOCKOUT_CAP", 3, "C21-C23(缺货风险)"), 1),
        (r("CAT_RES_SMD", 20, "R31-R50"), 1), (r("CAT_DIODE_ZENER", 4, "D11-D14"), 1),
    ],
    "SHT-CASE-PLCEXT-1.0MM": [
        (r("CAT_PLASTIC_SHELL", 1, ""), 1), (risky("ENV_BOLT_DAC", 4, "潮湿环境紧固件"), 1),
        (r("CAT_SEAL_ORING", 2, ""), 1),
    ],
    "ASM-CABLE-PLCEXT": [],
    # 温控仪 TC-800(高温工况)
    "ASM-PCBA-TC800-MAIN": [
        (r("CAT_SENSOR_TEMP", 3, "RT1-RT3"), 1), (risky("EOL_RES", 3, "R1-R3(停产风险)"), 1),
        (r("CAT_CAP_MLCC", 14, "C1-C14"), 1), (r("CAT_CAP_ALU", 4, "C15-C18"), 1),
        (r("CAT_RES_SMD", 30, "R4-R33"), 1), (r("CAT_DIODE_ZENER", 2, "D1,D2"), 1),
        (r("CAT_MOSFET", 2, "Q1,Q2"), 1), (r("CAT_CONN_BTB", 2, "J1,J2"), 1),
    ],
    "ASM-PCBA-TC800-PWR": [
        (r("CAT_PSU_ACDC", 1, "PS1"), 1), (r("CAT_DIODE_RECT", 3, "D11-D13"), 1),
        (r("CAT_CAP_ALU", 3, "C21-C23"), 1), (r("CAT_CONN_TERM", 4, "J11-J14"), 1),
    ],
    "ASM-PCBA-TC800-IO": [
        (r("CAT_CONN_TERM", 6, "J21-J26"), 1), (r("CAT_RELAY_EM", 3, "K1-K3"), 1),
        (r("CAT_RES_SMD", 14, "R41-R54"), 1),
    ],
    "SHT-CASE-TC800-1.0MM": [
        (r("CAT_PLASTIC_SHELL", 1, ""), 1), (r("CAT_BOLT", 6, ""), 1),
    ],
    "ASM-CABLE-TC800": [],
    # 步进驱动器 STP-DRV(振动工况)
    "ASM-PCBA-STPDRV-MAIN": [
        (risky("EOL_STEP", 1, "M1 驱动电机(停产)"), 1),
        (r("CAT_MOSFET", 4, "Q1-Q4"), 1), (r("CAT_CAP_ALU", 5, "C1-C5"), 1),
        (r("CAT_CAP_MLCC", 12, "C6-C17"), 1), (r("CAT_RES_SMD", 30, "R1-R30"), 1),
        (r("CAT_DIODE_RECT", 3, "D1-D3"), 1), (r("CAT_CONN_BTB", 2, "J1,J2"), 1),
        (r("CAT_IND_PWR", 2, "L1,L2"), 1),
    ],
    "ASM-PCBA-STPDRV-IO": [
        (r("CAT_CONN_TERM", 5, "J11-J15"), 1), (r("CAT_RELAY_EM", 1, "K1"), 1),
        (r("CAT_RES_SMD", 16, "R31-R46"), 1), (r("CAT_SENSOR_TEMP", 1, "RT1"), 1),
    ],
    "MAC-ALU-6061-STPDRV": [
        (risky("LONG_LT_BRG", 2, "传动轴承(长交期)"), 1), (r("CAT_BOLT", 6, ""), 1),
        (r("CAT_WASHER", 6, ""), 1),
    ],
    "ASM-CABLE-STPDRV": [(r("CAT_SEAL_ORING", 2, ""), 1)],
}

# 产品定义: 顶层组件(产品直接子件)
PRODUCTS = [
    {"code": "PSM-100", "name": "智能电表 PSM-100", "category": "电力计量仪表",
     "cond": {"temp_grade": "普通", "voltage_grade": "AC220V", "env": "室内"},
     "components": [("ASM-PCBA-PSM100-MAIN", 1), ("ASM-PCBA-PSM100-PWR", 1),
                    ("ASM-PCBA-PSM100-IO", 1), ("SHT-CASE-PSM100-1.0MM", 1),
                    ("ASM-CABLE-PSM100", 1)]},
    {"code": "VFD-2000", "name": "变频器控制板 VFD-2000", "category": "变频器",
     "cond": {"temp_grade": "高温", "voltage_grade": "AC220V", "env": "室内"},
     "components": [("ASM-PCBA-VFD2000-MAIN", 1), ("ASM-PCBA-VFD2000-PWR", 1),
                    ("ASM-PCBA-VFD2000-IO", 1), ("SHT-CASE-VFD2000-1.0MM", 1),
                    ("ASM-CABLE-VFD2000", 1)]},
    {"code": "AGV-DRV", "name": "AGV 驱动器 AGV-DRV", "category": "电机驱动",
     "cond": {"temp_grade": "普通", "voltage_grade": "DC24V", "env": "振动"},
     "components": [("ASM-PCBA-AGVDRV-MAIN", 1), ("ASM-PCBA-AGVDRV-PWR", 1),
                    ("ASM-PCBA-AGVDRV-IO", 1), ("MAC-ALU-6061-AGVDRV", 1),
                    ("ASM-CABLE-AGVDRV", 2)]},
    {"code": "GW-3100", "name": "工业网关 GW-3100", "category": "工业通信",
     "cond": {"temp_grade": "普通", "voltage_grade": "DC24V", "env": "室内"},
     "components": [("ASM-PCBA-GW3100-MAIN", 1), ("ASM-PCBA-GW3100-PWR", 1),
                    ("ASM-PCBA-GW3100-IO", 1), ("SHT-CASE-GW3100-1.0MM", 1),
                    ("ASM-CABLE-GW3100", 1)]},
    {"code": "SRV-CTL", "name": "伺服控制器 SRV-CTL", "category": "伺服控制",
     "cond": {"temp_grade": "高温", "voltage_grade": "AC220V", "env": "室内"},
     "components": [("ASM-PCBA-SRVCTL-MAIN", 1), ("ASM-PCBA-SRVCTL-PWR", 1),
                    ("ASM-PCBA-SRVCTL-IO", 1), ("SHT-CASE-SRVCTL-1.0MM", 1),
                    ("ASM-CABLE-SRVCTL", 1)]},
    {"code": "PLC-EXT", "name": "PLC 扩展模块 PLC-EXT", "category": "工业控制",
     "cond": {"temp_grade": "普通", "voltage_grade": "DC24V", "env": "潮湿"},
     "components": [("ASM-PCBA-PLCEXT-MAIN", 1), ("ASM-PCBA-PLCEXT-IO", 1),
                    ("SHT-CASE-PLCEXT-1.0MM", 1), ("ASM-CABLE-PLCEXT", 1)]},
    {"code": "TC-800", "name": "温控仪 TC-800", "category": "温度控制",
     "cond": {"temp_grade": "高温", "voltage_grade": "AC220V", "env": "室内"},
     "components": [("ASM-PCBA-TC800-MAIN", 1), ("ASM-PCBA-TC800-PWR", 1),
                    ("ASM-PCBA-TC800-IO", 1), ("SHT-CASE-TC800-1.0MM", 1),
                    ("ASM-CABLE-TC800", 1)]},
    {"code": "STP-DRV", "name": "步进驱动器 STP-DRV", "category": "电机驱动",
     "cond": {"temp_grade": "普通", "voltage_grade": "DC24V", "env": "振动"},
     "components": [("ASM-PCBA-STPDRV-MAIN", 1), ("ASM-PCBA-STPDRV-IO", 1),
                    ("MAC-ALU-6061-STPDRV", 1), ("ASM-CABLE-STPDRV", 1)]},
]


def build_product(prod):
    """展开组件定义 -> BOM 行(层级/父件/用量/路径)"""
    lines = []
    prod_code = prod["code"]

    def add(parent_code, node, qty, level, path):
        code, name, remark = resolve(node)
        lines.append({
            "product_code": prod_code, "parent_code": parent_code,
            "material_code": code, "material_name": name,
            "qty_per": qty, "unit": "只", "level": level,
            "path": f"{path}/{code}", "remark": remark,
        })

    def expand(comp_code, qty, level, path):
        children = COMP_DEFS.get(comp_code, [])
        for node, cqty in children:
            eff = cqty * qty
            add(comp_code, node, eff, level + 1, f"{path}/{comp_code}")
            if isinstance(node, str) and node in COMP_DEFS:
                expand(node, eff, level + 1, f"{path}/{comp_code}")

    for comp_code, qty in prod["components"]:
        add(prod_code, comp_code, qty, 0, f"/{prod_code}")
        expand(comp_code, qty, 0, f"/{prod_code}")

    for i, ln in enumerate(lines, 1):
        ln["line_no"] = i
    return {"code": prod_code, "name": prod["name"], "category": prod["category"],
            "condition": prod["cond"], "lines": lines}


def main():
    load_materials()
    products = []
    for p in PRODUCTS:
        b = build_product(p)
        products.append(b)
        risks = {}
        for ln in b["lines"]:
            m = BY_CODE[ln["material_code"]]
            if m["lifecycle_status"] == "EOL":
                risks[ln["material_code"]] = "EOL"
            elif m["lifecycle_status"] == "phaseout":
                risks[ln["material_code"]] = "phaseout"
            elif m["stock_qty"] < m["safety_stock"]:
                risks[ln["material_code"]] = "缺货"
            elif m["lead_time_days"] >= 30:
                risks[ln["material_code"]] = "长交期"
        print(f"{b['code']}: {len(b['lines'])} 行, 风险物料 {len(risks)} 种")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {"source": "仿真数据(scripts 生成, seed=42)",
                 "disclaimer": "非企业真实数据; 产品结构与 BOM 构成参考典型工业控制/电力电子设备公开资料"},
        "products": products,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成 {OUT}: {len(products)} 个产品")


if __name__ == "__main__":
    main()
