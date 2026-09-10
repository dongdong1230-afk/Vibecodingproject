"""生成仿真物料主数据 data/processed/materials.json

物料件号编码体系参考 Octopart Common Parts Library 思想(类别-关键参数-规格);
类别与属性 schema 与 knowledge/material_ontology.json 一致(本体个体 ABox)。
生成策略保证"替代链": 同类物料间存在参数覆盖关系(gte/lte/equal/allow_map),
使任意风险物料(EOL/缺货/长交期)都有合规替代候选, 支撑演示闭环。
刻意植入风险物料: 约 12% 停产(EOL)、8% 即将停产(phaseout)、12% 缺货,
以及进口件长交期(15~45 天)。

运行: cd backend && py -3.13 scripts/generate_materials.py
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # dsh/
ONTOLOGY_FILE = ROOT / "knowledge" / "material_ontology.json"
OUT = ROOT / "data" / "processed" / "materials.json"

rng = random.Random(42)  # 固定种子, 可复现

# 供应商池(国产现货/进口长交期)
SUP_DOMESTIC = ["苏州华芯电子", "深圳联创元件", "无锡精工机电", "东莞金鼎标准件厂",
                "宁波甬峰轴承", "常州步科电机", "浙江正泰配件", "东莞铭基塑胶"]
SUP_FOREIGN = ["Murata", "Panasonic", "TDK", "NSK", "SKF", "Omron", "明纬(台)", "台达(台)"]

CAT_BY_ID = {}
MATERIALS = []


def load_ontology():
    ont = json.loads(ONTOLOGY_FILE.read_text(encoding="utf-8"))
    for c in ont["categories"]:
        CAT_BY_ID[c["id"]] = c


def cat_names(cat_id):
    """类别 id -> (l1, l2, l3) 中文名(兼容两层类别: 组件与模块)"""
    c3 = CAT_BY_ID[cat_id]
    c2 = CAT_BY_ID[c3["parent_id"]]
    if c2["parent_id"] is None:
        return c2["name"], c3["name"], c3["name"]
    c1 = CAT_BY_ID[c2["parent_id"]]
    return c1["name"], c2["name"], c3["name"]


def material(cat_id, code, name, attrs, unit_price, lead_time, moq,
             supplier=None, failure_ppm=20):
    l1, l2, l3 = cat_names(cat_id)
    return {
        "code": code, "name": name, "category_id": cat_id,
        "category_l1": l1, "category_l2": l2, "category_l3": l3,
        "attrs": attrs,
        "unit_price": round(unit_price, 4),
        "lead_time_days": lead_time,
        "moq": moq,
        "supplier": supplier or rng.choice(SUP_DOMESTIC),
        "lifecycle_status": "active",
        "stock_qty": 0,          # 后处理统一分配
        "safety_stock": 0,
        "failure_rate_ppm": failure_ppm,
    }


def _fmt_val(v):
    if v >= 1000000 and v % 1000000 == 0:
        return f"{v // 1000000}M"
    if v >= 1000 and v % 1000 == 0:
        return f"{v // 1000}K"
    return str(v)


def _fmt_pw(p):
    return str(p).rstrip("0").rstrip(".")


def _fmt_uf(uf):
    if uf >= 1:
        return str(int(uf)) if float(uf).is_integer() else str(uf)
    if uf >= 0.001:
        v = uf * 1000
        return f"{int(v)}n" if float(v).is_integer() else f"{v}n"
    return f"{int(uf * 1e6)}p"


def _fmt_num(p):
    return str(p)


# ---------- 电阻器 ----------
def gen_resistors():
    # 全部阻值 × 4 封装 × 5%(替代链: 封装向上映射+功率覆盖), 半数阻值加 1% 精度档
    values = [10, 22, 47, 100, 220, 330, 470, 680, 1000, 2200, 3300, 4700,
              6800, 10000, 22000, 47000, 100000, 220000, 470000, 1000000]
    fp_power = {"0402": 0.063, "0603": 0.1, "0805": 0.125, "1206": 0.25}
    fp_price = {"0402": 0.8, "0603": 1.0, "0805": 1.4, "1206": 2.0}
    for i, v in enumerate(values):
        for fp in ["0402", "0603", "0805", "1206"]:
            for tol in ([1, 5] if i % 2 == 0 else [5]):
                pw = fp_power[fp]
                code = f"RES-{fp}-{_fmt_val(v)}-{tol}PCT-{_fmt_pw(pw)}"
                name = f"贴片电阻 {_fmt_val(v)}Ω ±{tol}% {fp} {_fmt_pw(pw)}W"
                attrs = {"resistance_ohm": v, "power_w": pw,
                         "tolerance_pct": tol, "footprint": fp}
                price = round(0.008 * fp_price[fp] * (2.0 if tol == 1 else 1.0), 4)
                MATERIALS.append(material(
                    "CAT_RES_SMD", code, name, attrs, price,
                    rng.choice([3, 4, 5, 7]), 100, failure_ppm=5))
    # 插件电阻(旧设计在用; 功率档形成覆盖链)
    for v in [100, 1000, 10000, 47000]:
        for pw, tol in [(0.25, 5), (0.5, 5), (0.5, 1)]:
            code = f"RESTH-AX-{_fmt_val(v)}-{tol}PCT-{_fmt_pw(pw)}"
            attrs = {"resistance_ohm": v, "power_w": pw, "tolerance_pct": tol}
            MATERIALS.append(material(
                "CAT_RES_TH", code, f"插件电阻 {_fmt_val(v)}Ω ±{tol}% {_fmt_pw(pw)}W",
                attrs, round(0.02 + pw * 0.2, 4), rng.choice([3, 5, 7]), 50,
                failure_ppm=8))


# ---------- 电容器 ----------
def gen_capacitors():
    # MLCC: 容值×电压×介质×封装(同容值多电压多封装, 保证电压覆盖+封装升级链)
    for uf in [0.1, 1, 2.2, 4.7, 10, 22, 47]:
        vols = [16, 25, 50] if uf <= 10 else [10, 16, 25]
        for v in vols:
            dielec = "C0G" if uf <= 0.1 else ("X7R" if v >= 25 else rng.choice(["X5R", "X7R"]))
            fps = ["0402", "0603"] if uf <= 1 else ["0603", "0805", "1206"]
            for fp in fps:
                code = f"CAP-MLCC-{fp}-{_fmt_uf(uf)}-{v}V-{dielec}"
                attrs = {"capacitance_uf": uf, "voltage_v": v,
                         "dielectric": dielec, "footprint": fp}
                price = round(0.015 * uf * (1.5 if dielec == "C0G" else 1.0) *
                              (1.3 if v >= 50 else 1.0) + 0.01, 4)
                MATERIALS.append(material(
                    "CAT_CAP_MLCC", code,
                    f"片式多层陶瓷电容 {_fmt_uf(uf)}µF {v}V {dielec} {fp}",
                    attrs, min(price, 1.5), rng.choice([3, 5, 7, 15]), 50,
                    failure_ppm=10))
    # 铝电解: 同容值多电压(电压覆盖链)
    for uf in [10, 22, 47, 100, 220, 470, 1000]:
        for v in ([16, 35, 63] if uf <= 220 else [16, 25, 35, 50]):
            temp = rng.choice([85, 105])
            esr = max(20, int(2200 / uf) * 10) if uf <= 1000 else 20
            code = f"CAP-ALU-{_fmt_uf(uf)}-{v}V-{temp}C"
            attrs = {"capacitance_uf": uf, "voltage_v": v, "esr_mohm": esr,
                     "temp_max_c": temp}
            price = round(0.05 + uf * 0.002 * (1.3 if temp == 105 else 1.0), 4)
            MATERIALS.append(material(
                "CAT_CAP_ALU", code, f"铝电解电容 {_fmt_uf(uf)}µF {v}V {temp}℃",
                attrs, price, rng.choice([3, 5, 7, 15]), 20,
                failure_ppm=50))
    # 钽电容(部分缺货——真实世界钽电容供应紧张); 外壳按电压递进, 形成 C→D 升级链
    for uf in [1, 4.7, 10, 22, 47, 100]:
        for v, shell in [(10, "A"), (16, "B"), (25, "C"), (35, "D")]:
            code = f"CAP-TANT-{shell}-{_fmt_uf(uf)}-{v}V"
            attrs = {"capacitance_uf": uf, "voltage_v": v, "footprint": shell}
            price = round(0.3 + uf * 0.06 + v * 0.01, 4)
            MATERIALS.append(material(
                "CAT_CAP_TANT", code, f"钽电容 {_fmt_uf(uf)}µF {v}V {shell}壳",
                attrs, price, rng.choice([7, 15, 21, 30]), 20,
                failure_ppm=80))


# ---------- 电感/二极管/晶体管 ----------
def gen_passives():
    # 功率电感: 同电感量多电流档×2 变体(电流覆盖链)
    for uh in [1, 2.2, 4.7, 10, 22, 47, 100]:
        for cur in ([1.5, 3, 5] if uh <= 22 else [0.8, 1.5, 2.5]):
            for variant in range(2):
                dcr = round(max(0.02, 0.5 / cur + uh * 0.001) * (1 - variant * 0.15), 3)
                code = f"IND-PWR-{_fmt_num(uh)}-{_fmt_val(int(cur * 1000))}MA{'-B' if variant else ''}"
                attrs = {"inductance_uh": uh, "current_a": cur, "dcr_ohm": dcr}
                MATERIALS.append(material(
                    "CAT_IND_PWR", code, f"功率电感 {_fmt_num(uh)}µH {cur}A",
                    attrs, round(0.25 + uh * 0.01 + cur * 0.2, 4),
                    rng.choice([3, 5, 7]), 20, failure_ppm=15))
    for vrm, cur in [(100, 1), (200, 1), (400, 2), (600, 2), (1000, 1), (1000, 3)]:
        code = f"DIO-RECT-{vrm}V-{cur}A"
        attrs = {"voltage_vrrm": vrm, "current_a": cur, "vf_v": 0.95}
        MATERIALS.append(material(
            "CAT_DIODE_RECT", code, f"整流二极管 {vrm}V {cur}A",
            attrs, round(0.08 + vrm * 0.0004, 4), rng.choice([3, 5]), 50,
            failure_ppm=12))
    # 稳压二极管: 同稳压值 0.5W/1W 两档(功率覆盖链)
    for vz in [3.3, 5.1, 5.6, 6.8, 9.1, 12, 15, 18, 24]:
        for pw in [0.5, 1.0]:
            code = f"DIO-ZENER-{_fmt_num(vz).replace('.', 'V')}-{_fmt_pw(pw)}W"
            attrs = {"vz_v": vz, "power_w": pw}
            MATERIALS.append(material(
                "CAT_DIODE_ZENER", code, f"稳压二极管 {_fmt_num(vz)}V {_fmt_pw(pw)}W",
                attrs, round(0.08 + pw * 0.1, 4), rng.choice([3, 5]), 50,
                failure_ppm=10))
    # MOSFET: 电压/电流/RDS 递进 + TO-252→TO-263 封装升级链
    for vds, ida, rds, pkg in [
        (30, 10, 12, "TO-252"), (30, 20, 8, "TO-252"), (40, 20, 8, "TO-252"),
        (60, 30, 8, "TO-252"), (60, 40, 6, "TO-263"), (100, 10, 40, "TO-252"),
        (100, 20, 25, "TO-252"), (100, 30, 20, "TO-263"),
    ]:
        code = f"MOS-{vds}V-{ida}A-{rds}MR"
        attrs = {"vds_v": vds, "id_a": ida, "rds_on_mohm": rds, "package": pkg}
        MATERIALS.append(material(
            "CAT_MOSFET", code, f"功率MOSFET {vds}V {ida}A {rds}mΩ {pkg}",
            attrs, round(0.5 + vds * 0.01 + ida * 0.08, 4),
            rng.choice([3, 5, 7, 15]), 10, failure_ppm=40))


# ---------- 连接器/传感器 ----------
def gen_connectors():
    # 板对板: 同针数同间距 3 变体(高度/电流递进, 覆盖链)
    for pins in [2, 4, 6, 8, 10, 12, 16, 20]:
        pitch = rng.choice([1.27, 2.54])
        for h, cur in [(4.3, 1), (4.3, 3), (8.5, 3)]:
            code = f"CON-BTB-{pins}P-{_fmt_num(pitch)}MM-H{_fmt_num(h)}-{cur}A"
            attrs = {"pins": pins, "pitch_mm": pitch, "height_mm": h, "current_a": cur}
            MATERIALS.append(material(
                "CAT_CONN_BTB", code, f"板对板连接器 {pins}针 {_fmt_num(pitch)}mm 高{h}",
                attrs, round(0.3 + pins * 0.12 + h * 0.02, 4),
                rng.choice([3, 5, 7]), 20, failure_ppm=25))
    # 接线端子: 同针数同间距 2 变体(电流递进)
    for pins in [2, 3, 4, 6, 8, 10, 12]:
        pitch = rng.choice([3.5, 5.08])
        curs = [8, 12] if pitch == 3.5 else [16, 20]
        for cur in curs:
            code = f"CON-TERM-{pins}P-{_fmt_num(pitch)}MM-{cur}A"
            attrs = {"pins": pins, "pitch_mm": pitch, "current_a": cur}
            MATERIALS.append(material(
                "CAT_CONN_TERM", code, f"接线端子 {pins}位 {_fmt_num(pitch)}mm {cur}A",
                attrs, round(0.4 + pins * 0.15, 4), rng.choice([3, 5]), 10,
                failure_ppm=20))
    for typ, name, rmax, acc, price in [
        ("NTC10K", "NTC热敏电阻 10KΩ B3950", 125, 1.0, 1.2),
        ("NTC100K", "NTC热敏电阻 100KΩ", 125, 1.0, 1.5),
        ("PT100", "铂电阻温度传感器 PT100", 200, 0.3, 8.0),
        ("DS18B20", "数字温度传感器 DS18B20", 125, 0.5, 3.5),
    ]:
        code = f"SEN-TEMP-{typ}"
        attrs = {"range_max_c": rmax, "accuracy_c": acc, "output": typ}
        MATERIALS.append(material(
            "CAT_SENSOR_TEMP", code, name, attrs, price,
            rng.choice([3, 5, 15]), 10, failure_ppm=30))


# ---------- 轴承/紧固件/密封 ----------
BEARINGS = [
    ("6000", 10, 26, 8, 4.6, 26000), ("6001", 12, 28, 8, 5.1, 22000),
    ("6002", 15, 32, 9, 5.6, 18000), ("6200", 10, 30, 9, 5.1, 20000),
    ("6201", 12, 32, 10, 6.8, 17000), ("6202", 15, 35, 11, 7.6, 15000),
    ("6203", 17, 40, 12, 9.6, 13000), ("6204", 20, 47, 14, 12.8, 11000),
    ("6205", 25, 52, 15, 14.0, 9500), ("6300", 10, 35, 11, 8.2, 16000),
    ("6301", 12, 37, 12, 9.7, 14000), ("6302", 15, 42, 13, 11.4, 12000),
]
NEEDLE = [("NA4904", 20, 37, 17, 22.0), ("NA4905", 25, 42, 17, 26.0),
          ("NA4906", 30, 47, 17, 30.0), ("NK20/16", 20, 28, 16, 12.0),
          ("NK25/20", 25, 33, 20, 15.0)]
# 密封/精度递进: 开式-P0 → ZZ-P6 → 2RS-P6 → 2RS-P5(允许映射向上兼容)
SEAL_PREC = [("开式", "P0"), ("ZZ", "P6"), ("2RS", "P6"), ("2RS", "P5")]


def gen_bearings():
    for model, bore, od, w, load, rpm in BEARINGS:
        for seal, prec in SEAL_PREC:
            srpm = {"开式": 1.0, "ZZ": 0.8, "2RS": 0.6}[seal]
            code = f"BRG-{model}-{seal}-{prec}"
            attrs = {"bore_mm": bore, "od_mm": od, "width_mm": w,
                     "dynamic_load_kn": load, "speed_limit_rpm": int(rpm * srpm),
                     "seal": seal, "precision": prec}
            foreign = rng.random() < 0.5
            sup = rng.choice(["NSK", "SKF"]) if foreign else rng.choice(SUP_DOMESTIC)
            lead = rng.choice([20, 30, 45]) if foreign else rng.choice([3, 5, 7])
            price = round((4 + load * 0.8) * (2.0 if foreign else 1.0) *
                          (1.3 if seal == "2RS" else 1.0), 2)
            MATERIALS.append(material(
                "CAT_BRG_DGBB", code, f"深沟球轴承 {model}-{seal} {prec}",
                attrs, price, lead, 1, sup, failure_ppm=25))
    for model, bore, od, w, load in NEEDLE:
        code = f"BRG-{model}"
        attrs = {"bore_mm": bore, "od_mm": od, "width_mm": w, "dynamic_load_kn": load}
        MATERIALS.append(material(
            "CAT_BRG_NEEDLE", code, f"滚针轴承 {model}", attrs,
            round(5 + load * 1.5, 2), rng.choice([20, 30, 45]), 1,
            rng.choice(SUP_FOREIGN[:4]), failure_ppm=20))


LENS_BY_SIZE = {"M3": [8, 12], "M4": [10, 16], "M5": [12, 20],
                "M6": [16, 25], "M8": [20, 30], "M10": [20, 30]}


def gen_fasteners():
    # 螺栓: 规格×长度×强度等级(8.8/10.9)×表面(镀锌/达克罗), 形成强度/表面升级链
    for s in ["M3", "M4", "M5", "M6", "M8", "M10"]:
        for l in LENS_BY_SIZE[s]:
            for g in ["8.8", "10.9"]:
                for sf in ["镀锌", "达克罗"]:
                    code = f"BLT-{s}-{l}-{g}-{'DAC' if sf == '达克罗' else 'ZN'}"
                    attrs = {"size": s, "length_mm": l, "strength_grade": g, "surface": sf}
                    price = round(0.03 + int(s[1:]) * 0.02 + l * 0.004 +
                                  {"8.8": 0.05, "10.9": 0.12}[g] +
                                  {"镀锌": 0, "达克罗": 0.15}[sf], 4)
                    MATERIALS.append(material(
                        "CAT_BOLT", code, f"六角螺栓 {s}×{l} {g}级 {sf}", attrs, price,
                        rng.choice([2, 3, 5]), 100, failure_ppm=5))
    # 螺母: 规格×强度×表面
    for s in ["M3", "M4", "M5", "M6", "M8", "M10"]:
        for g in ["8.8", "10.9"]:
            for sf in ["镀锌", "达克罗"]:
                code = f"NUT-{s}-{g}-{'DAC' if sf == '达克罗' else 'ZN'}"
                attrs = {"size": s, "strength_grade": g, "surface": sf}
                MATERIALS.append(material(
                    "CAT_NUT", code, f"六角螺母 {s} {g}级 {sf}", attrs,
                    round(0.02 + int(s[1:]) * 0.01, 4), rng.choice([2, 3, 5]), 100,
                    failure_ppm=3))
    # 垫圈: 规格×材料
    for s in ["M3", "M4", "M5", "M6", "M8", "M10"]:
        for m in ["碳钢", "不锈钢"]:
            code = f"WSH-{s}-{'SS' if m == '不锈钢' else 'CS'}"
            attrs = {"size": s, "material": m}
            MATERIALS.append(material(
                "CAT_WASHER", code, f"平垫圈 {s} {m}", attrs,
                round(0.01 + int(s[1:]) * 0.008 + (0.1 if m == "不锈钢" else 0), 4),
                rng.choice([2, 3, 5]), 200, failure_ppm=2))


def gen_seals():
    # O型圈: 内径×线径×材料(NBR/FKM), NBR→FKM 升级链(耐温覆盖)
    temp_map = {"NBR": 100, "FKM": 200, "SILICONE": 230}
    for inner in [10, 12, 15, 18, 20, 25, 30, 40, 50]:
        for wire in [1.8, 2.65, 3.1]:
            for mat in ["NBR", "FKM"]:
                code = f"ORG-{inner}-{_fmt_num(wire)}-{mat}"
                attrs = {"inner_dia_mm": inner, "wire_dia_mm": wire, "material": mat,
                         "temp_max_c": temp_map[mat]}
                price = round(0.3 + inner * 0.03 + {"NBR": 0, "FKM": 1.5}[mat], 2)
                MATERIALS.append(material(
                    "CAT_SEAL_ORING", code, f"O型密封圈 {inner}×{_fmt_num(wire)} {mat}",
                    attrs, price, rng.choice([3, 5, 7]), 10, failure_ppm=15))


# ---------- 电机/继电器/电源/风机 ----------
def gen_motors():
    for flange, torques, cur in [(42, [0.4, 0.6, 0.8], 1.5), (57, [1.2, 1.8, 2.4], 3.0),
                                 (86, [4.5, 6.5, 8.5, 12], 5.0)]:
        for t in torques:
            code = f"MOT-STEP-{flange}-{_fmt_num(t)}NM"
            attrs = {"step_angle_deg": 1.8, "holding_torque_nm": t,
                     "current_a": cur, "flange_mm": flange}
            price = round(20 + flange * 0.8 + t * 12, 2)
            MATERIALS.append(material(
                "CAT_MOTOR_STEP", code, f"步进电机 {flange}法兰 {_fmt_num(t)}N·m",
                attrs, price, rng.choice([5, 7, 15]), 1, failure_ppm=300))
    for v, pw, tq, rpm, dia in [(12, 5, 0.016, 3000, 25), (12, 20, 0.064, 3000, 36),
                                (24, 40, 0.13, 3000, 42), (24, 80, 0.25, 3000, 56),
                                (24, 120, 0.38, 5000, 56)]:
        code = f"MOT-DC-{v}V-{pw}W"
        attrs = {"voltage_v": v, "power_w": pw, "torque_nm": tq,
                 "speed_rpm": rpm, "diameter_mm": dia}
        MATERIALS.append(material(
            "CAT_MOTOR_DC", code, f"直流电机 {v}V {pw}W",
            attrs, round(15 + pw * 1.2, 2), rng.choice([5, 7, 15]), 1,
            failure_ppm=200))
    for pw, tq, flange in [(200, 0.64, 60), (400, 1.27, 80), (750, 2.39, 90),
                           (1000, 3.18, 110)]:
        code = f"MOT-SERVO-{pw}W"
        attrs = {"voltage_v": 220, "power_w": pw, "torque_nm": tq,
                 "speed_rpm": 3000, "flange_mm": flange}
        MATERIALS.append(material(
            "CAT_MOTOR_SERVO", code, f"伺服电机 {pw}W 220V",
            attrs, round(pw * 2.8, 2), rng.choice([15, 30, 45]), 1,
            rng.choice(SUP_FOREIGN), failure_ppm=150))


def gen_electromech():
    for coil in [5, 12, 24]:
        for cur in [5, 8, 10, 16]:
            cfg = rng.choice(["SPDT", "DPDT"])
            code = f"RLY-{coil}V-{cur}A-{cfg}"
            attrs = {"coil_voltage_v": coil, "contact_current_a": cur,
                     "contact_voltage_v": 250, "config": cfg}
            MATERIALS.append(material(
                "CAT_RELAY_EM", code, f"电磁继电器 {coil}V {cur}A {cfg}",
                attrs, round(1.5 + cur * 0.2, 2), rng.choice([3, 5, 15]), 10,
                failure_ppm=60))
    # 开关电源: 同输出电压电流×2 变体(覆盖链)
    for v, a, pw in [(5, 2, 10), (5, 6, 30), (12, 2, 24), (12, 5, 60), (24, 2, 48),
                     (24, 5, 120), (24, 10, 240), (24, 20, 480)]:
        for variant in range(2):
            code = f"PSU-{v}V-{a}A-{pw}W{'-B' if variant else ''}"
            attrs = {"output_v": v, "output_a": a, "power_w": pw}
            MATERIALS.append(material(
                "CAT_PSU_ACDC", code, f"AC-DC导轨电源 {v}V {a}A {pw}W",
                attrs, round(pw * 0.45 * (1 - variant * 0.1), 2),
                rng.choice([5, 7, 15]), 1, failure_ppm=120))
    # 轴流风机: 尺寸×电压×轴承×风量两档(风量覆盖链, 噪音固定)
    for size, airflow, noise in [(4010, 6, 25), (6025, 15, 28), (8025, 30, 32),
                                 (9225, 45, 38), (12025, 80, 45)]:
        for v in [12, 24]:
            for brg in ["含油", "滚珠"]:
                for mult in [1.0, 1.25]:
                    code = f"FAN-{size}-{v}V-{'BALL' if brg == '滚珠' else 'SLV'}-{mult}"
                    attrs = {"size_mm": size, "voltage_v": v,
                             "airflow_cfm": int(airflow * mult), "noise_db": noise,
                             "bearing": brg}
                    price = round(6 + airflow * mult * 0.4 + (5 if brg == "滚珠" else 0), 2)
                    MATERIALS.append(material(
                        "CAT_FAN_AXIAL", code,
                        f"轴流风机 {size} {v}V {brg} {int(airflow * mult)}CFM",
                        attrs, price, rng.choice([3, 5, 7]), 5, failure_ppm=80))


# ---------- 结构件 ----------
def gen_structures():
    for prod in ["PSM100", "VFD2000", "AGVDRV", "GW3100", "SRVCTL", "PLCEXT", "TC800", "STPDRV"]:
        # BOM 中引用的机箱件固定 1.0mm 板厚(BOM 树按确定编码引用)
        th = 1.0 if prod in {"PSM100", "VFD2000", "GW3100", "SRVCTL", "PLCEXT", "TC800"} \
            else rng.choice([1.0, 1.2, 1.5])
        mat_s = rng.choice(["冷轧板", "镀锌板"])
        code = f"SHT-CASE-{prod}-{_fmt_num(th)}MM"
        attrs = {"material": mat_s, "thickness_mm": th}
        MATERIALS.append(material(
            "CAT_SHEET_CASE", code, f"机箱钣金件({prod}用) {mat_s} {_fmt_num(th)}mm",
            attrs, round(12 + th * 8, 2), rng.choice([5, 10, 15]), 1,
            failure_ppm=10))
    for prod in ["PSM100", "VFD2000", "AGVDRV", "GW3100", "SRVCTL", "STPDRV", "TC800"]:
        # BOM 中引用的机加件固定 6061
        mat_a = "6061" if prod in {"AGVDRV", "STPDRV"} else rng.choice(["6061", "7075"])
        code = f"MAC-ALU-{mat_a}-{prod}"
        attrs = {"material": mat_a}
        MATERIALS.append(material(
            "CAT_MACH_ALU", code, f"铝合金机加件({prod}用) {mat_a}",
            attrs, round(6 + (12 if mat_a == "7075" else 0), 2),
            rng.choice([5, 10]), 1, failure_ppm=8))
    for prod in ["PSM100", "VFD2000", "AGVDRV", "GW3100", "SRVCTL", "PLCEXT", "TC800", "STPDRV"]:
        mat_p = rng.choice(["ABS", "PC+ABS"])
        fr = rng.choice(["V0", "V2"])
        code = f"PLS-SHELL-{mat_p}-{fr}-{prod}"
        attrs = {"material": mat_p, "flame_rating": fr}
        MATERIALS.append(material(
            "CAT_PLASTIC_SHELL", code, f"注塑外壳({prod}用) {mat_p} {fr}",
            attrs, round(2 + (4 if mat_p != "ABS" else 0) + (1 if fr == "V0" else 0), 2),
            rng.choice([5, 10]), 1, failure_ppm=12))


# ---------- 组件与模块(中间层, 不参与物料级替代) ----------
def gen_modules():
    for prod in ["PSM100", "VFD2000", "AGVDRV", "GW3100", "SRVCTL", "PLCEXT", "TC800", "STPDRV"]:
        boards = ["MAIN", "PWR", "IO"]
        if prod in {"VFD2000", "AGVDRV", "SRVCTL"}:   # 驱动子板(三级 BOM 用)
            boards.append("DRV")
        for board in boards:
            code = f"ASM-PCBA-{prod}-{board}"
            MATERIALS.append(material(
                "CAT_MOD_PCBA", code, f"PCBA组件({prod}-{board})",
                {}, round(60 + rng.random() * 240, 2), rng.choice([10, 15, 20]),
                1, rng.choice(SUP_DOMESTIC), failure_ppm=100))
        code = f"ASM-CABLE-{prod}"
        MATERIALS.append(material(
            "CAT_MOD_CABLE", code, f"线束组件({prod})", {},
            round(8 + rng.random() * 20, 2), rng.choice([5, 7]), 1,
            rng.choice(SUP_DOMESTIC), failure_ppm=40))


def assign_status():
    """后处理: 植入停产/即将停产/缺货风险物料(保证有同类 active 替代者)"""
    from collections import defaultdict
    by_cat = defaultdict(list)
    for m in MATERIALS:
        if m["category_id"] in {"CAT_MOD_PCBA", "CAT_MOD_CABLE"}:
            continue
        by_cat[m["category_id"]].append(m)

    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))  # backend/
    from scripts.generate_cases import check_coverage
    ont = json.loads(ONTOLOGY_FILE.read_text(encoding="utf-8"))
    schema = ont["property_schema"]

    def alt_count(m):
        n = 0
        for c in by_cat[m["category_id"]]:
            if c["code"] != m["code"] and c["lifecycle_status"] == "active" \
                    and not check_coverage(m["attrs"], c["attrs"],
                                           schema[m["category_id"]])[1]:
                n += 1
        return n

    eol_count = phaseout_count = stockout_count = 0
    for cat_id, items in by_cat.items():
        n = len(items)
        # 停产/即将停产: 优先挑"有替代候选"的物料(避免顶配死端物料成为风险物料)
        items = sorted(items, key=lambda m: -alt_count(m))
        n_eol = min(max(1, int(n * 0.12)), n - 3) if n >= 5 else 0
        n_ph = min(max(1, int(n * 0.08)), n - 3 - n_eol) if n >= 6 else 0
        for m in items[:n_eol]:
            m["lifecycle_status"] = "EOL"
            m["lead_time_days"] = rng.choice([30, 45, 60, 90])
            eol_count += 1
        for m in items[n_eol:n_eol + n_ph]:
            m["lifecycle_status"] = "phaseout"
            m["lead_time_days"] = rng.choice([15, 21, 30])
            phaseout_count += 1

    # 缺货: 库存低于安全库存(只作用于 active 物料); 按类别确定性植入,
    # 保证每个可替代小类至少 1 个缺货物料且其有合规替代候选
    for m in MATERIALS:
        if m["category_id"] in {"CAT_MOD_PCBA", "CAT_MOD_CABLE"}:
            m["stock_qty"] = 50
            m["safety_stock"] = 20
            continue
        m["safety_stock"] = max(1, int(m["moq"] * rng.choice([0.5, 1, 2])))
        if m["lifecycle_status"] == "active" and rng.random() < 0.12:
            m["stock_qty"] = max(0, int(m["safety_stock"] * rng.uniform(0.1, 0.9)))
            stockout_count += 1
        else:
            m["stock_qty"] = int(m["safety_stock"] * rng.uniform(1.2, 3.5))
    # 每类兜底: 若无缺货物料, 强制植入 1 个(优先有替代候选者)
    for cat_id in schema:
        items = [m for m in by_cat[cat_id]
                 if m["lifecycle_status"] == "active"]
        if not any(m["stock_qty"] < m["safety_stock"] for m in items):
            cands = sorted(items, key=lambda m: -alt_count(m))
            if cands:
                m = cands[0]
                m["stock_qty"] = max(0, int(m["safety_stock"] * 0.5))
                stockout_count += 1
    print(f"风险植入: EOL {eol_count} 种, phaseout {phaseout_count} 种, 缺货 {stockout_count} 种")


def main():
    load_ontology()
    gen_resistors()
    gen_capacitors()
    gen_passives()
    gen_connectors()
    gen_bearings()
    gen_fasteners()
    gen_seals()
    gen_motors()
    gen_electromech()
    gen_structures()
    gen_modules()
    assign_status()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {"source": "仿真数据(scripts 生成, seed=42)",
                 "disclaimer": "非企业真实数据; 件号体系与参数范围参考公开物料数据(Octopart CPL 等)"},
        "materials": MATERIALS,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成 {OUT}: {len(MATERIALS)} 种物料")


if __name__ == "__main__":
    main()
