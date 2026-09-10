"""生成物料替代本体 knowledge/material_ontology.json

本体要素(与标准本体语言对应关系见 meta.owl_mapping_note):
  categories       类别层级(OWL 类公理 subClassOf)
  property_schema  每小类性能参数 schema(OWL DataProperty 定义域/值域)
  forbidden_pairs  禁止替代对(负向断言)
  rules            替代适配规则(SWRL 规则对应)

运行: cd backend && py -3.13 scripts/generate_ontology.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # dsh/
KNOWLEDGE_DIR = ROOT / "knowledge"

# ---------- 类别树: 4 大类 / 15 中类 / 26 小类 ----------
CATEGORIES = [
    # 电子元件
    {"id": "CAT_ELEC", "parent_id": None, "name": "电子元件"},
    {"id": "CAT_RES", "parent_id": "CAT_ELEC", "name": "电阻器"},
    {"id": "CAT_RES_SMD", "parent_id": "CAT_RES", "name": "贴片电阻"},
    {"id": "CAT_RES_TH", "parent_id": "CAT_RES", "name": "插件电阻"},
    {"id": "CAT_CAP", "parent_id": "CAT_ELEC", "name": "电容器"},
    {"id": "CAT_CAP_MLCC", "parent_id": "CAT_CAP", "name": "片式多层陶瓷电容(MLCC)"},
    {"id": "CAT_CAP_ALU", "parent_id": "CAT_CAP", "name": "铝电解电容"},
    {"id": "CAT_CAP_TANT", "parent_id": "CAT_CAP", "name": "钽电容"},
    {"id": "CAT_IND", "parent_id": "CAT_ELEC", "name": "电感器"},
    {"id": "CAT_IND_PWR", "parent_id": "CAT_IND", "name": "功率电感"},
    {"id": "CAT_DIODE", "parent_id": "CAT_ELEC", "name": "二极管"},
    {"id": "CAT_DIODE_RECT", "parent_id": "CAT_DIODE", "name": "整流二极管"},
    {"id": "CAT_DIODE_ZENER", "parent_id": "CAT_DIODE", "name": "稳压二极管"},
    {"id": "CAT_TRANS", "parent_id": "CAT_ELEC", "name": "晶体管"},
    {"id": "CAT_MOSFET", "parent_id": "CAT_TRANS", "name": "功率MOSFET"},
    {"id": "CAT_CONN", "parent_id": "CAT_ELEC", "name": "连接器"},
    {"id": "CAT_CONN_BTB", "parent_id": "CAT_CONN", "name": "板对板连接器"},
    {"id": "CAT_CONN_TERM", "parent_id": "CAT_CONN", "name": "接线端子"},
    {"id": "CAT_SENSOR", "parent_id": "CAT_ELEC", "name": "传感器"},
    {"id": "CAT_SENSOR_TEMP", "parent_id": "CAT_SENSOR", "name": "温度传感器"},
    # 机械零件
    {"id": "CAT_MECH", "parent_id": None, "name": "机械零件"},
    {"id": "CAT_BRG", "parent_id": "CAT_MECH", "name": "轴承"},
    {"id": "CAT_BRG_DGBB", "parent_id": "CAT_BRG", "name": "深沟球轴承"},
    {"id": "CAT_BRG_NEEDLE", "parent_id": "CAT_BRG", "name": "滚针轴承"},
    {"id": "CAT_FAST", "parent_id": "CAT_MECH", "name": "紧固件"},
    {"id": "CAT_BOLT", "parent_id": "CAT_FAST", "name": "螺栓"},
    {"id": "CAT_NUT", "parent_id": "CAT_FAST", "name": "螺母"},
    {"id": "CAT_WASHER", "parent_id": "CAT_FAST", "name": "垫圈"},
    {"id": "CAT_SEAL", "parent_id": "CAT_MECH", "name": "密封件"},
    {"id": "CAT_SEAL_ORING", "parent_id": "CAT_SEAL", "name": "O型密封圈"},
    # 机电部件
    {"id": "CAT_EM", "parent_id": None, "name": "机电部件"},
    {"id": "CAT_MOTOR", "parent_id": "CAT_EM", "name": "电机"},
    {"id": "CAT_MOTOR_STEP", "parent_id": "CAT_MOTOR", "name": "步进电机"},
    {"id": "CAT_MOTOR_DC", "parent_id": "CAT_MOTOR", "name": "直流电机"},
    {"id": "CAT_MOTOR_SERVO", "parent_id": "CAT_MOTOR", "name": "伺服电机"},
    {"id": "CAT_RELAY", "parent_id": "CAT_EM", "name": "继电器"},
    {"id": "CAT_RELAY_EM", "parent_id": "CAT_RELAY", "name": "电磁继电器"},
    {"id": "CAT_PSU", "parent_id": "CAT_EM", "name": "开关电源"},
    {"id": "CAT_PSU_ACDC", "parent_id": "CAT_PSU", "name": "AC-DC导轨电源"},
    {"id": "CAT_FAN", "parent_id": "CAT_EM", "name": "风机"},
    {"id": "CAT_FAN_AXIAL", "parent_id": "CAT_FAN", "name": "轴流风机"},
    # 结构件
    {"id": "CAT_STRUCT", "parent_id": None, "name": "结构件"},
    {"id": "CAT_SHEET", "parent_id": "CAT_STRUCT", "name": "钣金件"},
    {"id": "CAT_SHEET_CASE", "parent_id": "CAT_SHEET", "name": "机箱钣金件"},
    {"id": "CAT_MACHINED", "parent_id": "CAT_STRUCT", "name": "机加件"},
    {"id": "CAT_MACH_ALU", "parent_id": "CAT_MACHINED", "name": "铝合金机加件"},
    {"id": "CAT_PLASTIC", "parent_id": "CAT_STRUCT", "name": "塑胶件"},
    {"id": "CAT_PLASTIC_SHELL", "parent_id": "CAT_PLASTIC", "name": "注塑外壳"},
    # 组件与模块(中间层装配件, 不参与物料级替代推理)
    {"id": "CAT_MOD", "parent_id": None, "name": "组件与模块"},
    {"id": "CAT_MOD_PCBA", "parent_id": "CAT_MOD", "name": "PCBA组件"},
    {"id": "CAT_MOD_CABLE", "parent_id": "CAT_MOD", "name": "线束组件"},
]
# 计算层级(0=大类, 1=中类, 2=小类)
LEVEL = {}
for c in CATEGORIES:
    if c["parent_id"] is None:
        LEVEL[c["id"]] = 0
for c in CATEGORIES:
    if c["parent_id"] is not None:
        LEVEL[c["id"]] = LEVEL[c["parent_id"]] + 1
for c in CATEGORIES:
    c["level"] = LEVEL[c["id"]]

# ---------- 属性 schema: 每小类关键性能参数 ----------
# key 与物料 attrs 字段一致; coverage: equal(相等或容差内) / gte(候选>=原件) / lte(候选<=原件)
# tolerance_pct: equal 型数值的允许偏差(%); allow_map: 类别型属性的"向上兼容"映射
P = {}  # 属性构造简写
P["resistance_ohm"] = {"key": "resistance_ohm", "name": "阻值", "type": "numeric",
                       "coverage": "equal", "tolerance_pct": 5}
P["power_w"] = {"key": "power_w", "name": "额定功率", "type": "numeric",
                "coverage": "gte"}
P["tolerance_pct"] = {"key": "tolerance_pct", "name": "精度", "type": "numeric",
                      "coverage": "lte"}
P["footprint_up"] = {"key": "footprint", "name": "封装", "type": "categorical",
                     "coverage": "equal",
                     "allow_map": {"0201": ["0201", "0402", "0603", "0805", "1206"],
                                   "0402": ["0402", "0603", "0805", "1206"],
                                   "0603": ["0603", "0805", "1206"],
                                   "0805": ["0805", "1206"],
                                   "1206": ["1206", "1210"],
                                   "1210": ["1210"]}}
P["footprint_tant"] = {"key": "footprint", "name": "外壳规格", "type": "categorical",
                       "coverage": "equal",
                       "allow_map": {"A": ["A", "B", "C"], "B": ["B", "C", "D"],
                                     "C": ["C", "D"], "D": ["D"]}}
P["voltage_v"] = {"key": "voltage_v", "name": "额定电压", "type": "numeric",
                  "coverage": "gte"}
P["capacitance_uf"] = {"key": "capacitance_uf", "name": "容值", "type": "numeric",
                       "coverage": "equal", "tolerance_pct": 10}
P["capacitance_uf20"] = {"key": "capacitance_uf", "name": "容值", "type": "numeric",
                         "coverage": "equal", "tolerance_pct": 20}
P["dielectric"] = {"key": "dielectric", "name": "介质", "type": "categorical",
                   "coverage": "equal",
                   "allow_map": {"X5R": ["X5R", "X7R"], "X7R": ["X7R"],
                                 "C0G": ["C0G"]}}
P["esr_mohm"] = {"key": "esr_mohm", "name": "等效串联电阻", "type": "numeric",
                 "coverage": "lte"}
P["temp_max_c"] = {"key": "temp_max_c", "name": "工作温度上限", "type": "numeric",
                   "coverage": "gte"}
P["inductance_uh"] = {"key": "inductance_uh", "name": "电感量", "type": "numeric",
                      "coverage": "equal", "tolerance_pct": 20}
P["current_a"] = {"key": "current_a", "name": "额定电流", "type": "numeric",
                  "coverage": "gte"}
P["dcr_ohm"] = {"key": "dcr_ohm", "name": "直流电阻", "type": "numeric",
                "coverage": "lte"}
P["voltage_vrrm"] = {"key": "voltage_vrrm", "name": "反向峰值电压", "type": "numeric",
                     "coverage": "gte"}
P["vf_v"] = {"key": "vf_v", "name": "正向压降", "type": "numeric", "coverage": "lte"}
P["vz_v"] = {"key": "vz_v", "name": "稳压值", "type": "numeric",
             "coverage": "equal", "tolerance_pct": 5}
P["vds_v"] = {"key": "vds_v", "name": "漏源电压", "type": "numeric", "coverage": "gte"}
P["id_a"] = {"key": "id_a", "name": "漏极电流", "type": "numeric", "coverage": "gte"}
P["rds_on_mohm"] = {"key": "rds_on_mohm", "name": "导通电阻", "type": "numeric",
                    "coverage": "lte"}
P["package_mos"] = {"key": "package", "name": "封装", "type": "categorical",
                    "coverage": "equal",
                    "allow_map": {"TO-252": ["TO-252", "TO-263"],
                                  "TO-263": ["TO-263"], "DFN5x6": ["DFN5x6"]}}
P["pins"] = {"key": "pins", "name": "针数", "type": "numeric",
             "coverage": "equal", "tolerance_pct": 0}
P["pitch_mm"] = {"key": "pitch_mm", "name": "间距", "type": "numeric",
                 "coverage": "equal", "tolerance_pct": 0}
P["height_mm"] = {"key": "height_mm", "name": "配合高度", "type": "numeric",
                  "coverage": "lte"}
P["range_max_c"] = {"key": "range_max_c", "name": "测温上限", "type": "numeric",
                    "coverage": "gte"}
P["accuracy_c"] = {"key": "accuracy_c", "name": "测量精度", "type": "numeric",
                   "coverage": "lte"}
P["output"] = {"key": "output", "name": "输出类型", "type": "categorical",
               "coverage": "equal",
               "allow_map": {"NTC10K": ["NTC10K"], "NTC100K": ["NTC100K"],
                             "PT100": ["PT100"], "DS18B20": ["DS18B20"]}}
P["bore_mm"] = {"key": "bore_mm", "name": "内径", "type": "numeric",
                "coverage": "equal", "tolerance_pct": 0}
P["od_mm"] = {"key": "od_mm", "name": "外径", "type": "numeric",
              "coverage": "equal", "tolerance_pct": 0}
P["width_mm"] = {"key": "width_mm", "name": "宽度", "type": "numeric",
                 "coverage": "equal", "tolerance_pct": 0}
P["dynamic_load_kn"] = {"key": "dynamic_load_kn", "name": "额定动载荷", "type": "numeric",
                        "coverage": "gte"}
P["speed_limit_rpm"] = {"key": "speed_limit_rpm", "name": "极限转速", "type": "numeric",
                        "coverage": "gte"}
P["seal"] = {"key": "seal", "name": "密封形式", "type": "categorical",
             "coverage": "equal",
             "allow_map": {"开式": ["开式", "ZZ", "2RS"], "ZZ": ["ZZ", "2RS"],
                           "2RS": ["2RS"]}}
P["precision"] = {"key": "precision", "name": "精度等级", "type": "categorical",
                  "coverage": "equal",
                  "allow_map": {"P0": ["P0", "P6", "P5"], "P6": ["P6", "P5"],
                                "P5": ["P5"]}}
P["size"] = {"key": "size", "name": "规格", "type": "categorical",
             "coverage": "equal", "allow_map": {}}
P["length_mm"] = {"key": "length_mm", "name": "长度", "type": "numeric",
                  "coverage": "equal", "tolerance_pct": 15}
P["strength_grade"] = {"key": "strength_grade", "name": "强度等级", "type": "categorical",
                       "coverage": "equal",
                       "allow_map": {"4.8": ["4.8", "8.8", "10.9", "12.9"],
                                     "8.8": ["8.8", "10.9", "12.9"],
                                     "10.9": ["10.9", "12.9"],
                                     "12.9": ["12.9"]}}
P["surface"] = {"key": "surface", "name": "表面处理", "type": "categorical",
                "coverage": "equal",
                "allow_map": {"镀锌": ["镀锌", "发黑", "达克罗"],
                              "发黑": ["发黑", "达克罗"],
                              "达克罗": ["达克罗"]}}
P["material_fast"] = {"key": "material", "name": "材料", "type": "categorical",
                      "coverage": "equal",
                      "allow_map": {"碳钢": ["碳钢", "不锈钢"], "不锈钢": ["不锈钢"]}}
P["inner_dia_mm"] = {"key": "inner_dia_mm", "name": "内径", "type": "numeric",
                     "coverage": "equal", "tolerance_pct": 0}
P["wire_dia_mm"] = {"key": "wire_dia_mm", "name": "线径", "type": "numeric",
                    "coverage": "equal", "tolerance_pct": 0}
P["material_oring"] = {"key": "material", "name": "材料", "type": "categorical",
                       "coverage": "equal",
                       "allow_map": {"NBR": ["NBR", "FKM"], "FKM": ["FKM"],
                                     "SILICONE": ["SILICONE", "FKM"]}}
P["step_angle_deg"] = {"key": "step_angle_deg", "name": "步距角", "type": "numeric",
                       "coverage": "equal", "tolerance_pct": 0}
P["holding_torque_nm"] = {"key": "holding_torque_nm", "name": "保持转矩", "type": "numeric",
                          "coverage": "gte"}
P["flange_mm"] = {"key": "flange_mm", "name": "法兰尺寸", "type": "numeric",
                  "coverage": "equal", "tolerance_pct": 0}
P["torque_nm"] = {"key": "torque_nm", "name": "额定转矩", "type": "numeric",
                  "coverage": "gte"}
P["speed_rpm"] = {"key": "speed_rpm", "name": "额定转速", "type": "numeric",
                  "coverage": "equal", "tolerance_pct": 20}
P["diameter_mm"] = {"key": "diameter_mm", "name": "机身直径", "type": "numeric",
                    "coverage": "equal", "tolerance_pct": 0}
P["coil_voltage_v"] = {"key": "coil_voltage_v", "name": "线圈电压", "type": "numeric",
                       "coverage": "equal", "tolerance_pct": 0}
P["contact_current_a"] = {"key": "contact_current_a", "name": "触点电流", "type": "numeric",
                          "coverage": "gte"}
P["contact_voltage_v"] = {"key": "contact_voltage_v", "name": "触点电压", "type": "numeric",
                          "coverage": "gte"}
P["config"] = {"key": "config", "name": "触点形式", "type": "categorical",
               "coverage": "equal", "allow_map": {"SPDT": ["SPDT", "DPDT"],
                                                   "DPDT": ["DPDT"]}}
P["output_v"] = {"key": "output_v", "name": "输出电压", "type": "numeric",
                 "coverage": "equal", "tolerance_pct": 0}
P["output_a"] = {"key": "output_a", "name": "输出电流", "type": "numeric",
                 "coverage": "gte"}
P["power_w_psu"] = {"key": "power_w", "name": "输出功率", "type": "numeric",
                    "coverage": "gte"}
P["size_mm"] = {"key": "size_mm", "name": "外形尺寸", "type": "numeric",
                "coverage": "equal", "tolerance_pct": 0}
P["airflow_cfm"] = {"key": "airflow_cfm", "name": "风量", "type": "numeric",
                    "coverage": "gte"}
P["noise_db"] = {"key": "noise_db", "name": "噪音", "type": "numeric",
                 "coverage": "lte"}
P["bearing"] = {"key": "bearing", "name": "轴承类型", "type": "categorical",
                "coverage": "equal",
                "allow_map": {"含油": ["含油", "滚珠"], "滚珠": ["滚珠"]}}
P["thickness_mm"] = {"key": "thickness_mm", "name": "板厚", "type": "numeric",
                     "coverage": "equal", "tolerance_pct": 20}
P["material_sheet"] = {"key": "material", "name": "材料", "type": "categorical",
                       "coverage": "equal",
                       "allow_map": {"冷轧板": ["冷轧板", "镀锌板", "不锈钢"],
                                     "镀锌板": ["镀锌板", "不锈钢"],
                                     "不锈钢": ["不锈钢"]}}
P["material_alu"] = {"key": "material", "name": "材料", "type": "categorical",
                     "coverage": "equal",
                     "allow_map": {"6061": ["6061", "7075"], "7075": ["7075"]}}
P["flame_rating"] = {"key": "flame_rating", "name": "阻燃等级", "type": "categorical",
                     "coverage": "equal",
                     "allow_map": {"V2": ["V2", "V0"], "V0": ["V0"]}}
P["material_plastic"] = {"key": "material", "name": "材料", "type": "categorical",
                         "coverage": "equal",
                         "allow_map": {"ABS": ["ABS", "PC+ABS", "PC"],
                                       "PC+ABS": ["PC+ABS", "PC"],
                                       "PC": ["PC"]}}

PROPERTY_SCHEMA = {
    "CAT_RES_SMD": [P["resistance_ohm"], P["power_w"], P["tolerance_pct"], P["footprint_up"]],
    "CAT_RES_TH": [P["resistance_ohm"], P["power_w"], P["tolerance_pct"]],
    "CAT_CAP_MLCC": [P["capacitance_uf"], P["voltage_v"], P["dielectric"], P["footprint_up"]],
    "CAT_CAP_ALU": [P["capacitance_uf20"], P["voltage_v"], P["esr_mohm"], P["temp_max_c"]],
    "CAT_CAP_TANT": [P["capacitance_uf"], P["voltage_v"], P["footprint_tant"]],
    "CAT_IND_PWR": [P["inductance_uh"], P["current_a"], P["dcr_ohm"]],
    "CAT_DIODE_RECT": [P["voltage_vrrm"], P["current_a"], P["vf_v"]],
    "CAT_DIODE_ZENER": [P["vz_v"], P["power_w"]],
    "CAT_MOSFET": [P["vds_v"], P["id_a"], P["rds_on_mohm"], P["package_mos"]],
    "CAT_CONN_BTB": [P["pins"], P["pitch_mm"], P["height_mm"], P["current_a"]],
    "CAT_CONN_TERM": [P["pins"], P["pitch_mm"], P["current_a"]],
    "CAT_SENSOR_TEMP": [P["range_max_c"], P["accuracy_c"], P["output"]],
    "CAT_BRG_DGBB": [P["bore_mm"], P["od_mm"], P["width_mm"], P["dynamic_load_kn"],
                     P["speed_limit_rpm"], P["seal"], P["precision"]],
    "CAT_BRG_NEEDLE": [P["bore_mm"], P["od_mm"], P["width_mm"], P["dynamic_load_kn"]],
    "CAT_BOLT": [P["size"], P["length_mm"], P["strength_grade"], P["surface"]],
    "CAT_NUT": [P["size"], P["strength_grade"], P["surface"]],
    "CAT_WASHER": [P["size"], P["material_fast"]],
    "CAT_SEAL_ORING": [P["inner_dia_mm"], P["wire_dia_mm"], P["material_oring"], P["temp_max_c"]],
    "CAT_MOTOR_STEP": [P["step_angle_deg"], P["holding_torque_nm"], P["current_a"],
                       P["flange_mm"]],
    "CAT_MOTOR_DC": [P["voltage_v"], P["power_w"], P["torque_nm"], P["speed_rpm"],
                     P["diameter_mm"]],
    "CAT_MOTOR_SERVO": [P["voltage_v"], P["power_w"], P["torque_nm"], P["speed_rpm"],
                        P["flange_mm"]],
    "CAT_RELAY_EM": [P["coil_voltage_v"], P["contact_current_a"], P["contact_voltage_v"],
                     P["config"]],
    "CAT_PSU_ACDC": [P["output_v"], P["output_a"], P["power_w_psu"]],
    "CAT_FAN_AXIAL": [P["size_mm"], P["voltage_v"], P["airflow_cfm"], P["noise_db"],
                      P["bearing"]],
    "CAT_SHEET_CASE": [P["material_sheet"], P["thickness_mm"]],
    "CAT_MACH_ALU": [P["material_alu"]],
    "CAT_PLASTIC_SHELL": [P["material_plastic"], P["flame_rating"]],
}

# ---------- 禁止替代对(负向断言) ----------
FORBIDDEN_PAIRS = [
    {"rule_id": "FP-001", "pair": ["CAT_CAP_ALU", "CAT_CAP_TANT"],
     "reason": "铝电解电容与钽电容特性差异大(ESR/极性/失效模式), 不可互代", "scope": {}},
    {"rule_id": "FP-002", "pair": ["CAT_CAP_MLCC", "CAT_CAP_TANT"],
     "reason": "MLCC 与钽电容容值-电压特性差异大, 不可互代", "scope": {}},
    {"rule_id": "FP-003", "pair": ["CAT_MOTOR_STEP", "CAT_MOTOR_SERVO"],
     "reason": "驱动控制方式不同(开环脉冲 vs 闭环), 不可直接互代", "scope": {}},
    {"rule_id": "FP-004", "pair": ["CAT_MOTOR_STEP", "CAT_MOTOR_DC"],
     "reason": "电机类型与控制方式不同, 不可互代", "scope": {}},
    {"rule_id": "FP-005", "pair": ["CAT_MOTOR_DC", "CAT_MOTOR_SERVO"],
     "reason": "控制方式与反馈机制不同, 不可互代", "scope": {}},
    {"rule_id": "FP-006", "pair": ["CAT_BRG_DGBB", "CAT_BRG_NEEDLE"],
     "reason": "承载特性不同(径向球轴承 vs 滚针轴承), 安装空间要求不同", "scope": {}},
    {"rule_id": "FP-007", "pair": ["CAT_DIODE_RECT", "CAT_DIODE_ZENER"],
     "reason": "功能不同(整流 vs 稳压), 不可互代", "scope": {}},
    {"rule_id": "FP-008", "pair": ["CAT_RES_SMD", "CAT_RES_TH"],
     "reason": "安装工艺不同(贴片 vs 插件), 需工艺变更评估", "scope": {}},
    {"rule_id": "FP-009", "pair": ["CAT_CONN_BTB", "CAT_CONN_TERM"],
     "reason": "连接方式不同(板对板 vs 线对板), 不可互代", "scope": {}},
    {"rule_id": "FP-010", "pair": ["CAT_SHEET_CASE", "CAT_PLASTIC_SHELL"],
     "reason": "材料体系不同(金属 vs 塑胶), 模具/加工工艺不同", "scope": {}},
    {"rule_id": "FP-011", "pair": ["CAT_MACH_ALU", "CAT_SHEET_CASE"],
     "reason": "加工工艺不同(机加 vs 钣金), 结构设计需重做", "scope": {}},
    {"rule_id": "FP-012", "pair": ["CAT_PSU_ACDC", "CAT_RELAY_EM"],
     "reason": "功能完全不同, 不可互代", "scope": {}},
]

# ---------- 显式替代规则(rule_engine 求值, 带 SWRL 对应) ----------
# 表达式变量: cand.*=候选物料字段/属性, orig.*=原物料字段/属性, cond.*=产品工况
RULES = [
    {"rule_id": "R-CAT-01", "name": "同小类可替代", "priority": 1, "scope": "*", "hard": True,
     "if": {"op": "eq", "left": "cand.category_l3", "right": "orig.category_l3"},
     "then": "allow", "reason": "同小类物料具备替代基础",
     "swrl": "Material(?c) ∧ Material(?o) ∧ hasCategory(?c,?k) ∧ hasCategory(?o,?k) → CanSubstitute(?c,?o)"},
    {"rule_id": "R-COND-01", "name": "高温工况 X5R 不可替代 X7R", "priority": 3,
     "scope": "CAT_CAP_MLCC", "hard": True,
     "if": {"op": "and", "args": [
         {"op": "eq", "left": "cond.temp_grade", "right": "高温"},
         {"op": "eq", "left": "orig.attrs.dielectric", "right": "X7R"},
         {"op": "eq", "left": "cand.attrs.dielectric", "right": "X5R"}]},
     "then": "deny", "reason": "X5R 高温容量衰减大, 高温工况不可替代 X7R",
     "swrl": "WorkCond(?w) ∧ hasTempGrade(?w,高温) ∧ hasDielectric(?o,X7R) ∧ hasDielectric(?c,X5R) → ¬CanSubstitute(?c,?o)"},
    {"rule_id": "R-COND-02", "name": "高温工况 NBR 不可替代 FKM 密封圈", "priority": 3,
     "scope": "CAT_SEAL_ORING", "hard": True,
     "if": {"op": "and", "args": [
         {"op": "eq", "left": "cond.temp_grade", "right": "高温"},
         {"op": "eq", "left": "orig.attrs.material", "right": "FKM"},
         {"op": "eq", "left": "cand.attrs.material", "right": "NBR"}]},
     "then": "deny", "reason": "NBR 耐温上限不足(100℃), 高温工况不可替代 FKM",
     "swrl": "WorkCond(?w) ∧ hasTempGrade(?w,高温) ∧ hasMaterial(?o,FKM) ∧ hasMaterial(?c,NBR) → ¬CanSubstitute(?c,?o)"},
    {"rule_id": "R-COND-03", "name": "潮湿环境镀锌螺栓不可替代达克罗", "priority": 3,
     "scope": "CAT_BOLT", "hard": True,
     "if": {"op": "and", "args": [
         {"op": "eq", "left": "cond.env", "right": "潮湿"},
         {"op": "eq", "left": "orig.attrs.surface", "right": "达克罗"},
         {"op": "eq", "left": "cand.attrs.surface", "right": "镀锌"}]},
     "then": "deny", "reason": "镀锌件耐盐雾能力弱, 潮湿环境不可替代达克罗处理件",
     "swrl": "WorkCond(?w) ∧ hasEnv(?w,潮湿) ∧ hasSurface(?o,达克罗) ∧ hasSurface(?c,镀锌) → ¬CanSubstitute(?c,?o)"},
    {"rule_id": "R-COND-04", "name": "振动环境含油轴承风机不可替代滚珠风机", "priority": 3,
     "scope": "CAT_FAN_AXIAL", "hard": True,
     "if": {"op": "and", "args": [
         {"op": "eq", "left": "cond.env", "right": "振动"},
         {"op": "eq", "left": "orig.attrs.bearing", "right": "滚珠"},
         {"op": "eq", "left": "cand.attrs.bearing", "right": "含油"}]},
     "then": "deny", "reason": "含油轴承不耐振动, 振动环境不可替代滚珠轴承风机",
     "swrl": "WorkCond(?w) ∧ hasEnv(?w,振动) ∧ hasBearing(?o,滚珠) ∧ hasBearing(?c,含油) → ¬CanSubstitute(?c,?o)"},
    {"rule_id": "R-COND-05", "name": "低温工况 C0G 不可替代 X7R", "priority": 3,
     "scope": "CAT_CAP_MLCC", "hard": True,
     "if": {"op": "and", "args": [
         {"op": "eq", "left": "cond.temp_grade", "right": "低温"},
         {"op": "eq", "left": "orig.attrs.dielectric", "right": "C0G"},
         {"op": "eq", "left": "cand.attrs.dielectric", "right": "X7R"}]},
     "then": "deny", "reason": "C0G 用于高稳定场合, 低温工况不可用 X7R 替代",
     "swrl": "WorkCond(?w) ∧ hasTempGrade(?w,低温) ∧ hasDielectric(?o,C0G) ∧ hasDielectric(?c,X7R) → ¬CanSubstitute(?c,?o)"},
    {"rule_id": "R-QUAL-01", "name": "故障率质量底线", "priority": 5, "scope": "*", "hard": True,
     "if": {"op": "gt", "left": "cand.failure_rate_ppm",
            "right": {"op": "mul", "args": [{"op": "ref", "path": "orig.failure_rate_ppm"}, 3]}},
     "then": "deny", "reason": "候选历史故障率超过原件 3 倍, 质量底线约束剔除",
     "swrl": "Material(?c) ∧ Material(?o) ∧ hasFailureRate(?c,?fc) ∧ hasFailureRate(?o,?fo) ∧ swrlb:greaterThan(?fc, multiply(?fo,3)) → ¬CanSubstitute(?c,?o)"},
    {"rule_id": "R-PRICE-01", "name": "替代成本上限约束", "priority": 4, "scope": "*", "hard": False,
     "if": {"op": "gt", "left": "cand.unit_price",
            "right": {"op": "mul", "args": [{"op": "ref", "path": "orig.unit_price"}, 1.5]}},
     "then": "warn", "reason": "候选单价超过原件 150%, 建议在 FCE 评估中关注成本指标",
     "swrl": "Material(?c) ∧ Material(?o) ∧ hasPrice(?c,?pc) ∧ hasPrice(?o,?po) ∧ swrlb:greaterThan(?pc, multiply(?po,1.5)) → CostWarning(?c,?o)"},
    {"rule_id": "R-LT-01", "name": "替代交期不劣化约束", "priority": 4, "scope": "*", "hard": False,
     "if": {"op": "gt", "left": "cand.lead_time_days",
            "right": {"op": "mul", "args": [{"op": "ref", "path": "orig.lead_time_days"}, 2]}},
     "then": "warn", "reason": "候选交期超过原件 2 倍, 替代可能引入新的采购风险",
     "swrl": "Material(?c) ∧ Material(?o) ∧ hasLeadTime(?c,?lc) ∧ hasLeadTime(?o,?lo) ∧ swrlb:greaterThan(?lc, multiply(?lo,2)) → LeadTimeWarning(?c,?o)"},
]

ONTOLOGY = {
    "meta": {
        "name": "离散制造物料替代本体",
        "version": "1.0",
        "description": "面向离散制造产品 BOM 物料替代推理的轻量本体: 类别层级、性能参数 schema、"
                       "兼容约束与替代适配规则。存储为 JSON, 推理由规则引擎执行。",
        "owl_mapping_note": "与标准本体语言的对应关系: ①categories 层级↔OWL 类公理(subClassOf); "
                           "②property_schema↔OWL DataProperty 及其定义域/值域; "
                           "③rules↔SWRL 规则(每条规则附 swrl 字段); "
                           "④forbidden_pairs↔负向断言(¬CanSubstitute); "
                           "⑤物料实例(materials 表)↔个体断言 ABox。",
    },
    "categories": CATEGORIES,
    "property_schema": PROPERTY_SCHEMA,
    "forbidden_pairs": FORBIDDEN_PAIRS,
    "rules": RULES,
}


def main():
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    out = KNOWLEDGE_DIR / "material_ontology.json"
    out.write_text(json.dumps(ONTOLOGY, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成 {out} ({len(CATEGORIES)} 类别, {len(PROPERTY_SCHEMA)} 小类属性schema, "
          f"{len(FORBIDDEN_PAIRS)} 禁止对, {len(RULES)} 条规则)")


if __name__ == "__main__":
    main()
